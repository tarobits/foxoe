<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import Icon from './Icon.vue';
import IconPicker from './IconPicker.vue';
import DeckKey from './DeckKey.vue';
import SourcePreview from './SourcePreview.vue';
import WidgetEditor from './WidgetEditor.vue';
import WidgetContent from './WidgetContent.vue';
import Demo from './Demo.vue';
import { t, locale } from './i18n';
import { firstSpace, fits, itemFits, appearance, contentStyle, usesSource } from './model.js';
import { useDashboardViewport, dashboardDragDelta } from './dashboardViewport';
import { parseFormula } from './formula.js';
import type { Config, Widget, Source, DeckState, DataEntry } from './types';

defineProps<{ remote?: boolean }>();
const emit = defineEmits<{ expired: []; logout: [] }>();

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
const viewport = ref<HTMLElement>();
const closingDialog = ref(false);
const preview = ref<Widget | null>(null);
const active = computed(() => (editing.value || screen.value === 'settings') && draft.value ? draft.value : config.value);
const rows = computed(() => Math.max(2, ...((active.value?.widgets || []).map(widget => widget.y + widget.h))));
const canvas = useDashboardViewport(viewport, rows);
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
  if (response.status === 401) emit('expired');
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
  draft.value.apps.push({ id: id('app'), name: t('defaultApp'), url: '', icon: 'window', textSize: 14 });
}
function addSource() {
  if (!draft.value || draft.value.sources.length >= 12) return;
  draft.value.sources.push({ id: id('source'), name: t('defaultSource'), url: '', interval: 15, authEnv: '' });
}
function removeSource(source: Source) {
  if (!draft.value) return;
  if (draft.value.widgets.some(widget => usesSource(widget, source.id))) { error.value = t('sourceInUse'); return; }
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
    const candidate = firstSpace({ id: id('widget'), kind: 'value', title: '', text: '', source: 'system', path: 'load1', itemPath: '', unit: '', x: 0, y: 0, w: 8, h: 4, padding: 24, gap: 8, columns: [1, 1], rows: [1], items: [], rules: [], align: 'left', icon: 'window' }, draft.value.widgets);
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
  try { for (const item of [selected.value, ...selected.value.items]) if (item.formula?.trim()) parseFormula(item.formula.trim()); }
  catch { widgetError.value = t('invalidFormula'); return; }
  if (!fits(selected.value, draft.value.widgets)) { widgetError.value = t('overlap'); return; }
  if (selected.value.items.some(item => !itemFits(item, selected.value))) { widgetError.value = t(selected.value.allowOverlap ? 'itemBounds' : 'itemOverlap'); return; }
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
  const width = grid.value.clientWidth;
  const scale = grid.value.getBoundingClientRect().width / width;
  const startX = event.clientX; const startY = event.clientY;
  const original = clone(widget);
  const move = (pointer: PointerEvent) => {
    const { x: dx, y: dy } = dashboardDragDelta(pointer.clientX - startX, pointer.clientY - startY, scale, width);
    preview.value = { ...original, ...(resize ? { w: Math.max(2, Math.min(24 - original.x, original.w + dx)), h: Math.max(1, Math.min(24, 48 - original.y, original.h + dy)) } : { x: Math.max(0, Math.min(24 - original.w, original.x + dx)), y: Math.max(0, Math.min(48 - original.h, original.y + dy)) }) };
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
  <div v-else-if="!config" class="loading-screen"><img class="loading-mark" src="/foxoe.svg" alt="" width="96" height="96"><h1>FoxOE</h1><p :role="error ? 'alert' : 'status'">{{ error || t('loading') }}</p><button v-if="error" class="secondary" @click="load">{{ t('retry') }}</button></div>
  <div v-else class="shell">
    <header class="shell-header">
      <div class="brand"><img class="brand-mark" src="/foxoe.svg" alt=""><h1>{{ screen === 'settings' ? t('settings') : active?.title }}</h1></div>
      <div class="header-actions">
        <button v-if="remote" class="secondary" @click="emit('logout')">{{ t('signOut') }}</button>
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
        <div v-else ref="viewport" class="widget-viewport">
        <div ref="grid" class="widget-grid" :style="{ width: `${canvas.width}px`, height: `${canvas.height}px`, transform: `translateX(-50%) scale(${canvas.scale})`, gridTemplateRows: `repeat(${rows}, 48px)` }">
          <TransitionGroup name="surface">
          <article v-for="widget in active?.widgets" v-show="editing || appearance(widget, data).visible" :key="widget.id" class="widget-panel" :class="{ moving: preview?.id === widget.id, invalid: preview?.id === widget.id && !fits(preview, active!.widgets), 'rule-hidden': editing && !appearance(widget, data).visible }" :style="{ ...placement(widget), ...contentStyle(widget, data), padding: `${widget.padding}px` }">
            <Transition name="notice"><div v-if="editing" class="widget-tools"><button class="icon-button drag-handle" :aria-label="t('moveWidget')" @pointerdown="startDrag($event, widget)" @keydown="keyMove($event, widget)"><Icon name="move" /></button><button class="icon-button" :aria-label="t('editWidget')" @click="editWidget(widget)"><Icon name="edit" /></button></div></Transition>
            <WidgetContent :widget="widget" :data="data" :now="now" :editing="editing" />
            <Transition name="notice"><button v-if="editing" class="icon-button resize-handle" :aria-label="t('resizeWidget')" @pointerdown="startDrag($event, widget, true)" @keydown="keyMove($event, widget, true)"><Icon name="resize" /></button></Transition>
          </article>
          </TransitionGroup>
        </div>
        </div>
      </main>
      <main v-else-if="draft" key="settings" class="settings-view">
        <nav class="settings-tabs" :aria-label="t('settings')"><button v-for="tab in (['applications', 'sources', 'system'] as const)" :key="tab" :class="{ selected: settingsTab === tab }" @click="settingsTab = tab">{{ t(tab) }}</button></nav>
        <Transition name="surface" mode="out-in">
          <section v-if="settingsTab === 'applications'" key="apps" class="settings-section">
            <div class="section-header"><h2>{{ t('applications') }}</h2><button class="secondary" :disabled="draft.apps.length >= 14" @click="addApp"><Icon name="plus" />{{ t('addApp') }}</button></div>
            <p v-if="draft.apps.length >= 14" class="muted">{{ t('appLimit') }}</p>
            <div v-for="app in draft.apps" :key="app.id" class="app-form">
              <div class="form-row">
              <label>{{ t('name') }}<input v-model="app.name" maxlength="60" required></label>
              <label class="grow">{{ t('url') }}<input v-model="app.url" type="text" spellcheck="false" required></label>
              <button class="icon-button danger-text" :aria-label="t('remove') + ' ' + app.name" @click="draft.apps = draft.apps.filter(item => item.id !== app.id)"><Icon name="remove" /></button>
              </div>
              <div class="form-row app-key-style"><IconPicker v-model="app.icon" /><label>{{ t('keyTextSize') }}<input v-model.number="app.textSize" type="number" min="8" max="32" step="1" required></label></div>
              <div class="key-colors"><label v-for="field in (['iconColor', 'textColor', 'backgroundColor'] as const)" :key="field">{{ t(field) }}<input type="color" :value="app[field] || (field === 'backgroundColor' ? '#1f2937' : field === 'iconColor' ? '#f8fafc' : '#ffffff')" @input="app[field] = ($event.target as HTMLInputElement).value"></label><button class="secondary" @click="app.iconColor = app.textColor = app.backgroundColor = null">{{ t('resetColors') }}</button><DeckKey :button="{ ...app, label: app.name, image: app.image ? app.images?.[app.image] : null }" /></div>
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
              <SourcePreview :source="source" @expired="emit('expired')" />
            </div>
          </section>
          <section v-else key="system" class="settings-section system-settings">
            <div class="form-row"><label class="grow">{{ t('title') }}<input v-model="draft.title" maxlength="60" required></label><label>{{ t('language') }}<select v-model="draft.locale"><option value="en">{{ t('english') }}</option><option value="de">{{ t('german') }}</option></select></label></div>
            <label>{{ t('brightness') }}<div class="range-row"><input v-model.number="draft.brightness" type="range" min="0" max="100"><output>{{ draft.brightness }}%</output></div></label>
            <section v-if="!remote" class="connection-section"><h2>{{ t('pairing') }}</h2><dl class="connection-details"><div><dt>{{ t('browser') }}</dt><dd>{{ t(state?.connected ? 'connected' : 'disconnected') }}</dd></div><div><dt>{{ t('device') }}</dt><dd>{{ t(state?.device || 'disconnected') }}</dd></div></dl><button class="secondary" @click="showToken">{{ t(token ? 'hideToken' : 'showToken') }}</button><Transition name="notice"><div v-if="token" class="pairing-token"><p class="muted">{{ t('tokenHelp') }}</p><input :value="token" readonly :aria-label="t('pairing')" autocomplete="off" @focus="($event.target as HTMLInputElement).select()"></div></Transition></section>
            <section v-if="!remote"><h2>{{ t('registration') }}</h2><p class="muted help">{{ t('registrationHelp') }}</p><button class="secondary" @click="showRegistrationToken">{{ t(registrationToken ? 'hideToken' : 'showRegistrationToken') }}</button><Transition name="notice"><div v-if="registrationToken" class="pairing-token"><input :value="registrationToken" readonly :aria-label="t('registration')" autocomplete="off" @focus="($event.target as HTMLInputElement).select()"></div></Transition></section>
            <section><h2>{{ t('preview') }}</h2><div class="deck-preview"><DeckKey v-for="(button, index) in state?.buttons" :key="index" :button="button" :home="index === 14" /></div></section>
          </section>
        </Transition>
      </main>
    </Transition>
    <Transition name="notice"><footer v-if="screen === 'home'" class="app-dock">
      <nav class="dock-apps" :aria-label="t('applications')"><a v-for="app in config.apps" :key="app.id" :href="app.url" class="dock-app" :class="{ 'text-only': !app.icon && !(app.image && app.images?.[app.image]) }" :aria-disabled="editing || remote" @click="(editing || remote) && $event.preventDefault()"><span v-if="app.icon || (app.image && app.images?.[app.image])" class="app-symbol"><img v-if="app.image && app.images?.[app.image]" :src="`/api/images/${app.images[app.image]}`" alt=""><Icon v-else :name="app.icon" /></span><span>{{ app.name }}</span></a><button v-if="!editing" class="dock-add" :aria-label="t('addApp')" @click="openSettings(); addApp()"><Icon name="plus" /></button></nav>
      <div class="dock-status"><span>{{ t('device') }}</span><span :class="{ success: state?.device === 'connected' }">{{ t(state?.device || 'disconnected') }}</span></div>
    </footer></Transition>
    <dialog ref="dialog" class="widget-dialog" aria-labelledby="widget-dialog-title" :class="{ closing: closingDialog }" @cancel.prevent="closeWidget">
      <form v-if="selected" @submit.prevent="applyWidget">
        <header class="dialog-header"><h2 id="widget-dialog-title">{{ t('editWidget') }}</h2><button type="button" class="icon-button" :aria-label="t('close')" @click="closeWidget"><Icon name="close" /></button></header>
        <div class="dialog-body form-stack">
          <WidgetEditor :widget="selected" :sources="draft?.sources || []" :data="data" :now="now" />
          <fieldset><legend>{{ t('placement') }}</legend><div class="position-fields"><label>{{ t('x') }}<input :value="selected.x + 1" type="number" min="1" max="24" @input="selected.x = Number(($event.target as HTMLInputElement).value) - 1"></label><label>{{ t('y') }}<input :value="selected.y + 1" type="number" min="1" max="48" @input="selected.y = Number(($event.target as HTMLInputElement).value) - 1"></label><label>{{ t('width') }}<input v-model.number="selected.w" type="number" min="2" max="24"></label><label>{{ t('height') }}<input v-model.number="selected.h" type="number" min="1" max="24"></label></div></fieldset>
          <p v-if="widgetError" class="alert error" role="alert">{{ widgetError }}</p>
        </div>
        <footer class="dialog-actions"><button type="button" class="text-button danger-text" @click="removeWidget">{{ t('deleteWidget') }}</button><div class="header-actions"><button type="button" class="secondary" @click="closeWidget">{{ t('cancel') }}</button><button type="submit" class="primary">{{ t('done') }}</button></div></footer>
      </form>
    </dialog>
  </div>
</template>
