import { onMounted, onScopeDispose, watch, type Ref } from 'vue';

/** Find the largest fitting size, with bounded measurement work per update. */
export function fitTextSize(maximum: number, fits: (size: number) => boolean) {
  let low = 0.25, high = maximum;
  if (fits(high)) return high;
  for (let step = 0; step < 10; step++) {
    const middle = (low + high) / 2;
    if (fits(middle)) low = middle; else high = middle;
  }
  return Math.floor(low * 100) / 100;
}

export function useTextFit(root: Ref<HTMLElement | undefined>, content: Ref<HTMLElement | undefined>, maximum: () => number, enabled: () => boolean) {
  let pending = false, active = true;
  const measure = () => {
    pending = false;
    const box = root.value, text = content.value;
    if (!active || !box || !text || !enabled() || box.clientWidth <= 0 || box.clientHeight <= 0) return;
    const fits = (size: number) => {
      text.style.setProperty('--fit-font-size', `${size}px`);
      return text.scrollHeight <= box.clientHeight && text.scrollWidth <= box.clientWidth;
    };
    const size = fitTextSize(maximum(), fits);
    text.style.setProperty('--fit-font-size', `${size}px`);
  };
  // Animation frames can be suspended for off-screen previews. Batch within
  // the current update instead so mounted content never waits for scrolling.
  const schedule = () => { if (active && !pending) { pending = true; queueMicrotask(measure); } };
  watch([maximum, enabled], schedule, { flush: 'post' });
  onMounted(() => {
    const resize = new ResizeObserver(schedule), mutation = new MutationObserver(schedule);
    if (root.value) resize.observe(root.value);
    // Observe content and markup, excluding our own sizing style writes.
    if (content.value) mutation.observe(content.value, { childList: true, characterData: true, subtree: true });
    schedule(); void document.fonts.ready.then(schedule);
    document.fonts.addEventListener('loadingdone', schedule);
    onCleanup = () => { resize.disconnect(); mutation.disconnect(); document.fonts.removeEventListener('loadingdone', schedule); };
  });
  let onCleanup = () => {};
  onScopeDispose(() => { active = false; onCleanup(); });
  return schedule;
}
