/** Small, non-executable JSON paths: queue.items[0].name or $.queue.items. */
export function readPath(value, path) {
  if (!path || path === '$') return value;
  const normalized = path.replace(/^\$\.?/, '').replace(/\[(\d+)\]/g, '.$1');
  if (!/^[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*$/.test(normalized)) return undefined;
  for (const key of normalized.split('.')) {
    if (['__proto__', 'prototype', 'constructor'].includes(key) || value === null || typeof value !== 'object' || !Object.hasOwn(value, key)) return undefined;
    value = value[key];
  }
  return value;
}

export function fits(widget, widgets) {
  if (![widget.x, widget.y, widget.w, widget.h].every(Number.isInteger) || widget.x < 0 || widget.y < 0 || widget.w < 2 || widget.w > 12 || widget.h < 1 || widget.h > 12 || widget.x + widget.w > 12 || widget.y + widget.h > 24) return false;
  return widgets.every(other => other.id === widget.id || widget.x + widget.w <= other.x || widget.x >= other.x + other.w || widget.y + widget.h <= other.y || widget.y >= other.y + other.h);
}

export function firstSpace(widget, widgets) {
  for (let y = 0; y < 24; y++) for (let x = 0; x < 12; x++) {
    const next = { ...widget, x, y };
    if (fits(next, widgets)) return next;
  }
  return null;
}

export function formatValue(value, locale) {
  if (typeof value === 'number' && Number.isFinite(value)) return new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value);
  if (typeof value === 'string') return value;
  return null;
}

export function listPage(value) {
  return { rows: Array.isArray(value) ? value.slice(0, 100) : [], truncated: Array.isArray(value) && value.length > 100 };
}
