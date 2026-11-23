<script setup lang="ts">
import { onMounted, ref } from 'vue';
import App from './App.vue';
import { t, locale } from './i18n';
const ready = ref(false), remote = ref(false), authenticated = ref(false), busy = ref(false);
const password = ref(''), error = ref('');
async function check() {
  try {
    const response = await fetch('/api/access');
    if (!response.ok) throw new Error();
    const value = await response.json();
    remote.value = value.remote; authenticated.value = value.authenticated;
    if (value.locale === 'en' || value.locale === 'de') locale.value = value.locale;
    ready.value = true; error.value = '';
  } catch { error.value = t('serviceOffline'); }
}
async function login() {
  if (busy.value) return;
  busy.value = true; error.value = '';
  try {
    const response = await fetch('/api/admin/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: password.value }) });
    password.value = '';
    if (!response.ok) { const result = await response.json(); error.value = t(result.error || 'admin_invalid_login'); return; }
    authenticated.value = true;
  } catch { error.value = t('serviceOffline'); }
  finally { busy.value = false; }
}
async function logout() {
  try {
    const response = await fetch('/api/admin/logout', { method: 'POST' });
    if (!response.ok) throw new Error();
    authenticated.value = false;
  } catch { error.value = t('serviceOffline'); }
}
onMounted(check);
</script>
<template>
  <App v-if="ready && authenticated" :remote="remote" @expired="authenticated = false" @logout="logout" />
  <main v-else class="access-screen">
    <form v-if="ready" class="access-form" @submit.prevent="login">
      <h1>FoxOE</h1><h2>{{ t('administration') }}</h2>
      <label>{{ t('adminPassword') }}<input v-model="password" type="password" autocomplete="current-password" maxlength="1024" required></label>
      <Transition name="notice"><p v-if="error" role="alert">{{ error }}</p></Transition>
      <button class="primary" :disabled="busy">{{ t('signIn') }}</button>
    </form>
    <div v-else><h1>FoxOE</h1><p role="status">{{ error || t('loading') }}</p><button v-if="error" class="secondary" @click="check">{{ t('retry') }}</button></div>
  </main>
  <p v-if="error && authenticated" class="alert" role="alert">{{ error }}</p>
</template>
