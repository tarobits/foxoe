<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import Icon from './Icon.vue';
import WidgetContent from './WidgetContent.vue';
import Demo from './Demo.vue';
import { t, locale } from './i18n';
import { firstSpace, fits } from './model.js';
import type { Config, Widget, Source, DeckState, DataEntry } from './types';

const config = ref<Config>();
const draft = ref<Config>();
const state = ref<DeckState>();
const data = ref<Record<string, DataEntry>>({});
const now = ref(new Date());
const screen = ref<'home' | 'settings'>('home');
const settingsTab = ref<'applications' | 'sources' | 'system'>('applications');
const editing = ref(false);
const saving = ref(false);
const error = ref('');
const notice = ref('');
const offline = ref(false);
const token = ref('');
const registrationToken = ref('');
const selected = ref<Widget>();
const widgetError = ref('');
const dialog = ref<HTMLDialogElement>();
const grid = ref<HTMLElement>();
const closingDialog = ref(false);
const preview = ref<Widget | null>(null);
const active = computed(() => (editing.value || screen.value === 'settings') && draft.value ? draft.value : config.value);
const rows = computed(() => Math.max(2, ...((active.value?.widgets || []).map(widget => widget.y + widget.h))));
const isDemo = location.pathname === '/demo';
const abort = new AbortController();
let pollTimer: ReturnType<typeof setTimeout>;
let clockTimer: ReturnType<typeof setInterval>;
let noticeTimer: ReturnType<typeof setTimeout>;
let dialogTimer: ReturnType<typeof setTimeout>;
let removeDrag: (() => void) | undefined;
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));
const id = (prefix: string) => `${prefix}-${crypto.randomUUID().slice(0, 8)}`;

async function api(path: string, options?: RequestInit) {
  const response = await fetch(`/api/${path}`, { ...options, signal: abort.signal, headers: { 'Content-Type': 'application/json', ...options?.headers } });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'saveFailed');
  return result;
}
async function load() {
  try {
    config.value = await api('config');
    locale.value = config.value!.locale;
    error.value = ''; offline.value = false;
  } catch { if (!abort.signal.aborted) { error.value = t('serviceOffline'); offline.value = true; } }
}
async function poll() {
  try {
    const result = await Promise.all([api('state'), api('data')]);
    state.value = result[0]; data.value = result[1]; offline.value = false;
    if (config.value && state.value?.configRevision !== config.value.revision) {
      config.value = await api('config');
      if (!draft.value) locale.value = config.value!.locale;
    }
  } catch { if (!abort.signal.aborted) offline.value = true; }
  if (!abort.signal.aborted) pollTimer = setTimeout(poll, 3000);
}
function flash(message: string) {
  notice.value = message;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { notice.value = ''; }, 5000);
}
function beginEdit() {
  if (!config.value) return;
  draft.value = clone(config.value); editing.value = true; error.value = '';
}
function openSettings(tab: typeof settingsTab.value = 'applications') {
  if (!config.value) return;
  draft.value = clone(config.value); editing.value = false; settingsTab.value = tab; screen.value = 'settings'; error.value = '';
}
async function cancel() {
  editing.value = false; screen.value = 'home'; draft.value = undefined; token.value = ''; registrationToken.value = ''; error.value = '';
  await load();
}
async function save() {
  if (!draft.value || saving.value) return;
  saving.value = true; error.value = '';
  try {
    config.value = await api('config', { method: 'PUT', body: JSON.stringify(draft.value) });
    locale.value = config.value!.locale;
    editing.value = false; screen.value = 'home'; draft.value = undefined; token.value = ''; registrationToken.value = ''; flash(t('saved'));
  } catch (reason) { error.value = t(reason instanceof Error ? reason.message : 'saveFailed'); }
  finally { saving.value = false; }
}
function addApp() {
  if (!draft.value || draft.value.apps.length >= 14) return;
  draft.value.apps.push({ id: id('app'), name: t('defaultApp'), url: '', icon: 'window' });
}
function addSource() {
  if (!draft.value || draft.value.sources.length >= 12) return;
  draft.value.sources.push({ id: id('source'), name: t('defaultSource'), url: '', interval: 15, authEnv: '' });
}
function removeSource(source: Source) {
  if (!draft.value) return;
  if (draft.value.widgets.some(widget => ['value', 'list'].includes(widget.kind) && widget.source === source.id)) { error.value = t('sourceInUse'); return; }
  draft.value.sources = draft.value.sources.filter(item => item.id !== source.id);
}
async function showToken() {
  if (token.value) { token.value = ''; return; }
  try { token.value = (await api('pair', { method: 'POST' })).token; }
  catch { error.value = t('saveFailed'); }
}
async function showRegistrationToken() {
  if (registrationToken.value) { registrationToken.value = ''; return; }
  try { registrationToken.value = (await api('registration-token', { method: 'POST' })).token; }
  catch { error.value = t('saveFailed'); }
}
async function editWidget(widget?: Widget) {
  if (!draft.value) return;
  if (widget) selected.value = clone(widget);
  else {
    if (draft.value.widgets.length >= 24) { error.value = t('noSpace'); return; }
    const candidate = firstSpace({ id: id('widget'), kind: 'value', title: '', text: '', source: 'system', path: 'load1', itemPath: '', unit: '', x: 0, y: 0, w: 4, h: 2 }, draft.value.widgets);
    if (!candidate) { error.value = t('noSpace'); return; }
    selected.value = candidate as Widget;
  }
  widgetError.value = ''; closingDialog.value = false;
  await nextTick(); dialog.value?.showModal();
}
function closeWidget() {
  if (closingDialog.value) return;
  closingDialog.value = true;
  const delay = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 100;
  dialogTimer = setTimeout(() => { dialog.value?.close(); selected.value = undefined; closingDialog.value = false; }, delay);
}
function applyWidget() {
  if (!selected.value || !draft.value) return;
  if (!fits(selected.value, draft.value.widgets)) { widgetError.value = t('overlap'); return; }
  const index = draft.value.widgets.findIndex(widget => widget.id === selected.value!.id);
  if (index < 0) draft.value.widgets.push(clone(selected.value)); else draft.value.widgets[index] = clone(selected.value);
  closeWidget();
}
function removeWidget() {
  if (draft.value && selected.value) draft.value.widgets = draft.value.widgets.filter(widget => widget.id !== selected.value!.id);
  closeWidget();
}
function keyMove(event: KeyboardEvent, widget: Widget, resize = false) {
  const direction: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
  if (!direction[event.key] || !draft.value) return;
  event.preventDefault();
  const [dx, dy] = direction[event.key]!;
  const next = { ...widget, ...(resize ? { w: widget.w + dx, h: widget.h + dy } : { x: widget.x + dx, y: widget.y + dy }) };
  if (fits(next, draft.value.widgets)) Object.assign(widget, next); else flash(t('overlap'));
}
function startDrag(event: PointerEvent, widget: Widget, resize = false) {
  if (event.button !== 0 || !draft.value || !grid.value) return;
  event.preventDefault(); removeDrag?.();
  const width = (grid.value.getBoundingClientRect().width + 16) / 12;
  const startX = event.clientX; const startY = event.clientY;
  const original = clone(widget);
  const move = (pointer: PointerEvent) => {
    const dx = Math.round((pointer.clientX - startX) / width); const dy = Math.round((pointer.clientY - startY) / 112);
    preview.value = { ...original, ...(resize ? { w: Math.max(2, Math.min(12 - original.x, original.w + dx)), h: Math.max(1, Math.min(12, original.h + dy)) } : { x: Math.max(0, Math.min(12 - original.w, original.x + dx)), y: Math.max(0, Math.min(24 - original.h, original.y + dy)) }) };
  };
  const end = () => {
    if (preview.value && draft.value) {
      if (fits(preview.value, draft.value.widgets)) Object.assign(widget, preview.value); else flash(t('overlap'));
    }
    cleanup();
  };
  const escape = (key: KeyboardEvent) => { if (key.key === 'Escape') cleanup(); };
  const cleanup = () => { window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', end); window.removeEventListener('pointercancel', cleanup); window.removeEventListener('keydown', escape); preview.value = null; removeDrag = undefined; };
  removeDrag = cleanup;
  window.addEventListener('pointermove', move); window.addEventListener('pointerup', end, { once: true }); window.addEventListener('pointercancel', cleanup, { once: true }); window.addEventListener('keydown', escape);
}
function placement(widget: Widget) {
  const item = preview.value?.id === widget.id ? preview.value : widget;
  return { gridColumn: `${item.x + 1} / span ${item.w}`, gridRow: `${item.y + 1} / span ${item.h}` };
}
watch(locale, value => { document.documentElement.lang = value; });
onMounted(() => { void load(); void poll(); clockTimer = setInterval(() => { now.value = new Date(); }, 1000); });
onUnmounted(() => { abort.abort(); clearTimeout(pollTimer); clearInterval(clockTimer); clearTimeout(noticeTimer); clearTimeout(dialogTimer); removeDrag?.(); });
</script>

<template>
  <Demo v-if="isDemo" />
  <div v-else-if="!config" class="loading-screen"><h1>FoxOE</h1><p :role="error ? 'alert' : 'status'">{{ error || t('loading') }}</p><button v-if="error" class="secondary" @click="load">{{ t('retry') }}</button></div>
  <div v-else class="shell">
    <header class="shell-header">
      <div class="brand"><img class="brand-mark" src="/foxoe.svg" alt=""><h1>{{ screen === 'settings' ? t('settings') : active?.title }}</h1></div>
      <div class="header-actions">
        <template v-if="editing || screen === 'settings'"><button class="secondary" :disabled="saving" @click="cancel">{{ t('cancel') }}</button><button class="primary" :disabled="saving" @click="save"><Icon name="check" />{{ t('save') }}</button></template>
        <template v-else><button class="icon-button" :aria-label="t('editDashboard')" @click="beginEdit"><Icon name="edit" /></button><button class="icon-button" :aria-label="t('settings')" @click="openSettings()"><Icon name="settings" /></button></template>
      </div>
    </header>
    <Transition name="notice"><div v-if="error || offline" class="alert error" role="alert">{{ error || t('serviceOffline') }}</div></Transition>
    <Transition name="notice"><div v-if="notice" class="toast" role="status">{{ notice }}</div></Transition>
    <Transition name="surface" mode="out-in">
      <main v-if="screen === 'home'" key="home" class="dashboard" :class="{ editing }">
        <Transition name="notice"><div v-if="editing" class="edit-toolbar"><span>{{ t('editDashboard') }}</span><button class="secondary" @click="editWidget()"><Icon name="plus" />{{ t('addWidget') }}</button></div></Transition>
        <div v-if="!active?.widgets.length" class="empty-state"><Icon name="keypad" /><h2>{{ t('noWidgets') }}</h2><button class="primary" @click="beginEdit(); editWidget()">{{ t('addWidget') }}</button></div>
        <div v-else ref="grid" class="widget-grid" :style="{ gridTemplateRows: `repeat(${rows}, 96px)` }">
          <TransitionGroup name="surface">
          <article v-for="widget in active?.widgets" :key="widget.id" class="widget-panel" :class="{ moving: preview?.id === widget.id, invalid: preview?.id === widget.id && !fits(preview, active!.widgets) }" :style="placement(widget)">
            <Transition name="notice"><div v-if="editing" class="widget-tools"><button class="icon-button drag-handle" :aria-label="t('moveWidget')" @pointerdown="startDrag($event, widget)" @keydown="keyMove($event, widget)"><Icon name="move" /></button><button class="icon-button" :aria-label="t('editWidget')" @click="editWidget(widget)"><Icon name="edit" /></button></div></Transition>
            <WidgetContent :widget="widget" :entry="data[widget.source]" :now="now" />
            <Transition name="notice"><button v-if="editing" class="icon-button resize-handle" :aria-label="t('resizeWidget')" @pointerdown="startDrag($event, widget, true)" @keydown="keyMove($event, widget, true)"><Icon name="resize" /></button></Transition>
          </article>
          </TransitionGroup>
        </div>
      </main>
      <main v-else-if="draft" key="settings" class="settings-view">
        <nav class="settings-tabs" :aria-label="t('settings')"><button v-for="tab in (['applications', 'sources', 'system'] as const)" :key="tab" :class="{ selected: settingsTab === tab }" @click="settingsTab = tab">{{ t(tab) }}</button></nav>
        <Transition name="surface" mode="out-in">
          <section v-if="settingsTab === 'applications'" key="apps" class="settings-section">
            <div class="section-header"><h2>{{ t('applications') }}</h2><button class="secondary" :disabled="draft.apps.length >= 14" @click="addApp"><Icon name="plus" />{{ t('addApp') }}</button></div>
            <p v-if="draft.apps.length >= 14" class="muted">{{ t('appLimit') }}</p>
            <div v-for="app in draft.apps" :key="app.id" class="app-form form-row">
              <label>{{ t('name') }}<input v-model="app.name" maxlength="60" required></label>
              <label class="grow">{{ t('url') }}<input v-model="app.url" type="text" spellcheck="false" required></label>
              <label>{{ t('icon') }}<select v-model="app.icon"><option v-for="icon in ['window','printer','keypad','home','foxoe']" :key="icon" :value="icon">{{ icon === 'foxoe' ? 'FoxOE' : t(icon === 'window' ? 'applications' : icon === 'printer' ? 'printer' : icon === 'keypad' ? 'demo' : icon) }}</option></select></label>
              <button class="icon-button danger-text" :aria-label="t('remove') + ' ' + app.name" @click="draft.apps = draft.apps.filter(item => item.id !== app.id)"><Icon name="remove" /></button>
            </div>
            <p v-if="!draft.apps.length" class="muted">{{ t('noApps') }}</p>
          </section>
          <section v-else-if="settingsTab === 'sources'" key="sources" class="settings-section">
            <div class="section-header"><h2>{{ t('sources') }}</h2><button class="secondary" :disabled="draft.sources.length >= 12" @click="addSource"><Icon name="plus" />{{ t('addSource') }}</button></div>
            <p class="muted">{{ t('sourceHelp') }}</p>
            <div v-for="source in draft.sources" :key="source.id" class="source-form">
              <div class="form-row"><label>{{ t('name') }}<input v-model="source.name" maxlength="60" required></label><label class="grow">{{ t('url') }}<input v-model="source.url" type="url" spellcheck="false" required></label><button class="icon-button danger-text" :aria-label="t('remove') + ' ' + source.name" @click="removeSource(source)"><Icon name="remove" /></button></div>
              <div class="form-row"><label>{{ t('interval') }}<input v-model.number="source.interval" type="number" min="5" max="3600"></label><label class="grow">{{ t('authEnv') }}<input v-model="source.authEnv" spellcheck="false" pattern="(FOXOE_SECRET_[A-Z0-9_]+)?"></label></div>
              <p class="muted help">{{ t('credentialHelp') }}</p>
            </div>
          </section>
          <section v-else key="system" class="settings-section system-settings">
            <div class="form-row"><label class="grow">{{ t('title') }}<input v-model="draft.title" maxlength="60" required></label><label>{{ t('language') }}<select v-model="draft.locale"><option value="en">{{ t('english') }}</option><option value="de">{{ t('german') }}</option></select></label></div>
            <label>{{ t('brightness') }}<div class="range-row"><input v-model.number="draft.brightness" type="range" min="0" max="100"><output>{{ draft.brightness }}%</output></div></label>
            <section class="connection-section"><h2>{{ t('pairing') }}</h2><dl class="connection-details"><div><dt>{{ t('browser') }}</dt><dd>{{ t(state?.connected ? 'connected' : 'disconnected') }}</dd></div><div><dt>{{ t('device') }}</dt><dd>{{ t(state?.device || 'disconnected') }}</dd></div></dl><button class="secondary" @click="showToken">{{ t(token ? 'hideToken' : 'showToken') }}</button><Transition name="notice"><div v-if="token" class="pairing-token"><p class="muted">{{ t('tokenHelp') }}</p><input :value="token" readonly :aria-label="t('pairing')" autocomplete="off" @focus="($event.target as HTMLInputElement).select()"></div></Transition></section>
            <section><h2>{{ t('registration') }}</h2><p class="muted help">{{ t('registrationHelp') }}</p><button class="secondary" @click="showRegistrationToken">{{ t(registrationToken ? 'hideToken' : 'showRegistrationToken') }}</button><Transition name="notice"><div v-if="registrationToken" class="pairing-token"><input :value="registrationToken" readonly :aria-label="t('registration')" autocomplete="off" @focus="($event.target as HTMLInputElement).select()"></div></Transition></section>
            <section><h2>{{ t('preview') }}</h2><div class="deck-preview"><div v-for="(button, index) in state?.buttons" :key="index" class="deck-key" :class="{ disabled: button?.disabled, 'home-key': index === 14 }"><img v-if="button?.image" :src="`/api/images/${button.image}`" alt=""><Icon v-else-if="button" :name="button.icon" /><span>{{ button?.label }}</span></div></div></section>
          </section>
        </Transition>
      </main>
    </Transition>
    <Transition name="notice"><footer v-if="screen === 'home'" class="app-dock">
      <nav class="dock-apps" :aria-label="t('applications')"><a v-for="app in config.apps" :key="app.id" :href="app.url" class="dock-app" :aria-disabled="editing" @click="editing && $event.preventDefault()"><span class="app-symbol"><img v-if="app.image && app.images?.[app.image]" :src="`/api/images/${app.images[app.image]}`" alt=""><Icon v-else :name="app.icon" /></span><span>{{ app.name }}</span></a><button v-if="!editing" class="dock-add" :aria-label="t('addApp')" @click="openSettings(); addApp()"><Icon name="plus" /></button></nav>
      <div class="dock-status"><span>{{ t('device') }}</span><span :class="{ success: state?.device === 'connected' }">{{ t(state?.device || 'disconnected') }}</span></div>
    </footer></Transition>
    <dialog ref="dialog" class="widget-dialog" aria-labelledby="widget-dialog-title" :class="{ closing: closingDialog }" @cancel.prevent="closeWidget">
      <form v-if="selected" @submit.prevent="applyWidget">
        <header class="dialog-header"><h2 id="widget-dialog-title">{{ t('editWidget') }}</h2><button type="button" class="icon-button" :aria-label="t('close')" @click="closeWidget"><Icon name="close" /></button></header>
        <div class="dialog-body form-stack">
          <div class="form-row"><label class="grow">{{ t('title') }}<input v-model="selected.title" maxlength="60"></label><label>{{ t('kind') }}<select v-model="selected.kind"><option v-for="kind in ['clock','value','list','text']" :key="kind" :value="kind">{{ t(kind) }}</option></select></label></div>
          <label v-if="selected.kind === 'text'">{{ t('content') }}<textarea v-model="selected.text" rows="3" maxlength="1000"></textarea></label>
          <template v-if="['value','list'].includes(selected.kind)"><label>{{ t('source') }}<select v-model="selected.source"><option value="system">{{ t('system') }}</option><option v-for="source in draft?.sources" :key="source.id" :value="source.id">{{ source.name }}</option></select></label><div class="form-row"><label class="grow">{{ t('path') }}<select v-if="selected.source === 'system'" v-model="selected.path"><option v-for="path in ['load1','memoryPercent','memoryUsedMiB','memoryTotalMiB','temperatureC']" :key="path" :value="path">{{ t(path) }}</option></select><input v-else v-model="selected.path" spellcheck="false" maxlength="200"></label><label v-if="selected.kind === 'value'">{{ t('unit') }}<input v-model="selected.unit" maxlength="12"></label><label v-else>{{ t('itemPath') }}<input v-model="selected.itemPath" spellcheck="false" maxlength="200"></label></div></template>
          <fieldset><legend>{{ t('placement') }}</legend><div class="position-fields"><label>{{ t('x') }}<input :value="selected.x + 1" type="number" min="1" max="12" @input="selected.x = Number(($event.target as HTMLInputElement).value) - 1"></label><label>{{ t('y') }}<input :value="selected.y + 1" type="number" min="1" max="24" @input="selected.y = Number(($event.target as HTMLInputElement).value) - 1"></label><label>{{ t('width') }}<input v-model.number="selected.w" type="number" min="2" max="12"></label><label>{{ t('height') }}<input v-model.number="selected.h" type="number" min="1" max="12"></label></div></fieldset>
          <p v-if="widgetError" class="alert error" role="alert">{{ widgetError }}</p>
        </div>
        <footer class="dialog-actions"><button type="button" class="text-button danger-text" @click="removeWidget">{{ t('deleteWidget') }}</button><div class="header-actions"><button type="button" class="secondary" @click="closeWidget">{{ t('cancel') }}</button><button type="submit" class="primary">{{ t('done') }}</button></div></footer>
      </form>
    </dialog>
  </div>
</template>
