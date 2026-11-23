<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { createDeck, keypadLayout } from '../sdk/foxoe.js';
import { t, locale } from './i18n';
import Icon from './Icon.vue';
const quantity = ref(1);
const input = ref('1');
const entering = ref(false);
const connected = ref(false);
const error = ref('');
let deck: ReturnType<typeof createDeck>;
const layout = () => keypadLayout({ backspace: t('backspace'), cancel: t('cancel'), confirm: t('confirm') });
const base = () => ({ id: 'quantity', buttons: [{ id: 'quantity', label: t('quantity'), icon: 'keypad' }] });
async function publish() {
  if (!deck?.connected) return;
  try { await deck.show(entering.value ? layout() : base()); } catch { error.value = t('bridgeUnavailable'); }
}
async function open() {
  input.value = String(quantity.value); entering.value = true;
  if (deck.connected) try { await deck.push(layout()); } catch { error.value = t('bridgeUnavailable'); }
}
async function finish(confirm: boolean) {
  if (confirm) {
    const value = Number(input.value);
    if (!Number.isInteger(value) || value < 1 || value > 999999) return;
    quantity.value = value;
  }
  entering.value = false;
  if (deck.connected) try { await deck.pop(); } catch { error.value = t('bridgeUnavailable'); }
}
function action(id: string) {
  if (id === 'quantity') { void open(); return; }
  if (!entering.value) return;
  if (/^digit\.\d$/.test(id) && input.value.length < 6) input.value = input.value === '0' ? id.slice(-1) : input.value + id.slice(-1);
  else if (id === 'backspace') input.value = input.value.slice(0, -1);
  else if (id === 'cancel') void finish(false);
  else if (id === 'confirm') void finish(true);
}
onMounted(() => {
  deck = createDeck();
  deck.onAction((event: { id: string }) => action(event.id));
  deck.onConnection((value: boolean) => { connected.value = value; if (value) { error.value = ''; void publish(); } });
});
onUnmounted(() => deck?.dispose());
watch(locale, () => void publish());
</script>
<template>
  <main class="demo-view">
    <header class="page-header"><a href="/" class="secondary"><Icon name="home" />{{ t('home') }}</a><span class="connection-label">{{ t(connected ? 'connected' : 'disconnected') }}</span></header>
    <section class="demo-content" :class="{ 'keypad-open': entering }"><h1>{{ t('demo') }}</h1><p v-if="!entering" class="muted">{{ t('demoHelp') }}</p>
      <p v-if="error" class="alert" role="alert">{{ error }}</p>
      <Transition name="surface" mode="out-in">
        <div v-if="!entering" class="quantity-view"><span>{{ t('quantity') }}</span><strong>{{ quantity }}</strong><button class="primary" @click="open"><Icon name="keypad" />{{ t('enterQuantity') }}</button></div>
        <div v-else class="quantity-view"><label for="quantity">{{ t('quantity') }}</label><input id="quantity" v-model="input" type="text" inputmode="numeric" maxlength="6" pattern="[0-9]{1,6}" autocomplete="off"><div class="touch-keypad"><button v-for="digit in ['7','8','9','4','5','6','1','2','3']" :key="digit" class="secondary" @click="action(`digit.${digit}`)">{{ digit }}</button><button class="secondary" :aria-label="t('backspace')" @click="action('backspace')"><Icon name="backspace" /></button><button class="secondary" @click="action('digit.0')">0</button><button class="primary" :disabled="!/^[0-9]{1,6}$/.test(input) || Number(input) < 1" :aria-label="t('confirm')" @click="finish(true)"><Icon name="check" /></button></div><button class="text-button" @click="finish(false)">{{ t('cancel') }}</button></div>
      </Transition>
    </section>
  </main>
</template>
