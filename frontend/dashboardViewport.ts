import { computed, onScopeDispose, ref, watch, type Ref } from 'vue';

export const DESIGN_WIDTH = 968; // 1024px kiosk minus dashboard side padding.
export const DESIGN_HEIGHT = 372; // 600px minus header, dock, and dashboard padding.
const ROW_STEP = 56; // 48px track + 8px gap; outer padding totals one gap.

export function dashboardFit(width: number, height: number, rows: number) {
  const valid = Number.isFinite(width) && Number.isFinite(height) && width > 0 && height > 0;
  const rowCount = Number.isInteger(rows) && rows >= 2 && rows <= 48 ? rows : 2;
  const canvasWidth = DESIGN_WIDTH;
  const canvasHeight = rowCount * ROW_STEP;
  return { width: canvasWidth, height: canvasHeight, scale: valid ? Math.min(1, width / canvasWidth, height / canvasHeight, DESIGN_HEIGHT / canvasHeight) : 0 };
}

export function widgetDimensions(columns: number, rows: number) {
  return { width: (DESIGN_WIDTH / 24) * columns - 8, height: ROW_STEP * rows - 8 };
}

export function dashboardDragDelta(x: number, y: number, scale: number, width: number) {
  if (![x, y, scale, width].every(Number.isFinite) || scale <= 0 || width <= 0) return { x: 0, y: 0 };
  return { x: Math.round(x / (width / 24 * scale)), y: Math.round(y / (ROW_STEP * scale)) };
}

export function useDashboardViewport(element: Ref<HTMLElement | undefined>, rows: Ref<number>) {
  const width = ref(0), height = ref(0);
  const stop = watch(element, (target, _, cleanup) => {
    width.value = height.value = 0;
    if (!target) return;
    let active = true;
    const observer = new ResizeObserver(entries => {
      if (!active) return;
      const entry = entries.find(entry => entry.target === target);
      if (entry) { width.value = entry.contentRect.width; height.value = entry.contentRect.height; }
    });
    observer.observe(target);
    cleanup(() => { active = false; observer.disconnect(); });
  }, { flush: 'post', immediate: true });
  onScopeDispose(stop);
  return computed(() => dashboardFit(width.value, height.value, rows.value));
}
