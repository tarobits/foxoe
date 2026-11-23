<script setup lang="ts">
import { computed } from 'vue';
import { t, locale } from './i18n';
import type { Source } from './types';
import { useSourcePreview } from './sourcePreview';
const props = defineProps<{ source: Source }>();
const emit = defineEmits<{ expired: [] }>();
const { open, busy, error, result, refresh, close } = useSourcePreview(() => props.source, () => emit('expired'));
const timestamp = computed(() => result.value?.updatedAt == null ? '' : new Date(result.value.updatedAt * 1000).toLocaleString(locale.value));
</script>
<template>
  <div class="source-preview">
    <div class="header-actions">
      <button type="button" class="secondary" :disabled="busy || !source.url.trim()" :aria-expanded="open" @click="refresh">{{ t(busy ? 'loading' : open ? 'refreshJson' : 'previewJson') }}</button>
      <button v-if="open" type="button" class="text-button" @click="close">{{ t('close') }}</button>
    </div>
    <Transition name="notice">
      <section v-if="open" class="source-snapshot" :aria-label="t('previewJson')" :aria-busy="busy">
        <p v-if="busy" class="muted" role="status">{{ t('loading') }}</p>
        <p v-else-if="error" class="data-warning" role="alert">{{ t(error) }}</p>
        <template v-else-if="result">
          <p class="muted" role="status">{{ t('fetchedAt') }} <time :datetime="new Date(result.updatedAt! * 1000).toISOString()">{{ timestamp }}</time></p>
          <pre tabindex="0" :aria-label="t('jsonResponse')"><code>{{ JSON.stringify(result.value, null, 2) }}</code></pre>
          <p class="muted help">{{ t('previewRedaction') }}</p>
        </template>
      </section>
    </Transition>
  </div>
</template>
