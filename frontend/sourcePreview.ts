import { onScopeDispose, ref, watch } from 'vue';
import type { DataEntry, Source } from './types';

export function useSourcePreview(source: () => Source, expired: () => void, request = fetch) {
  const open = ref(false), busy = ref(false), error = ref('');
  const result = ref<DataEntry>();
  let active: AbortController | undefined;
  function close() {
    active?.abort(); active = undefined;
    open.value = false; busy.value = false; error.value = ''; result.value = undefined;
  }
  async function refresh() {
    if (busy.value) return;
    const controller = new AbortController();
    active = controller;
    open.value = true; busy.value = true; error.value = ''; result.value = undefined;
    try {
      const response = await request('/api/data/preview', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(source()), signal: controller.signal,
      });
      if (active !== controller) return;
      if (response.status === 401) { close(); expired(); return; }
      const value = await response.json();
      if (active !== controller) return;
      if (!response.ok) {
        error.value = response.status === 422 ? 'invalid_configuration' : 'sourcePreviewFailed';
      } else result.value = value;
    } catch {
      if (active === controller) error.value = 'sourcePreviewFailed';
    } finally {
      if (active === controller) { active = undefined; busy.value = false; }
    }
  }
  watch(() => JSON.stringify(source()), close, { flush: 'sync' });
  onScopeDispose(close);
  return { open, busy, error, result, refresh, close };
}
