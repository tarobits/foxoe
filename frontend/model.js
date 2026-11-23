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
  if (![widget.x, widget.y, widget.w, widget.h].every(Number.isInteger) || widget.x < 0 || widget.y < 0 || widget.w < 2 || widget.w > 24 || widget.h < 1 || widget.h > 24 || widget.x + widget.w > 24 || widget.y + widget.h > 48) return false;
  return widgets.every(other => other.id === widget.id || widget.x + widget.w <= other.x || widget.x >= other.x + other.w || widget.y + widget.h <= other.y || widget.y >= other.y + other.h);
}

export function firstSpace(widget, widgets) {
  for (let y = 0; y < 48; y++) for (let x = 0; x < 24; x++) {
    const next = { ...widget, x, y };
    if (fits(next, widgets)) return next;
  }
  return null;
}

export function formatValue(value, locale) {
  if (typeof value === 'boolean') return String(value);
  if (typeof value === 'number' && Number.isFinite(value)) return new Intl.NumberFormat(locale, { maximumFractionDigits: 2 }).format(value);
  if (typeof value === 'string') return value;
  return null;
}

export function ruleMatches(rule, data) {
  const entry = data[rule.source];
  if (!entry || entry.error) return false;
  const actual = readPath(entry.value, rule.path), expected = rule.value;
  if (rule.operator === 'exists') return actual !== undefined && actual !== null;
  if (rule.operator === 'missing') return actual === undefined || actual === null;
  if (actual === undefined) return false;
  switch (rule.operator) {
    case 'eq': return actual === expected;
    case 'ne': return actual !== expected;
    case 'gt': case 'gte': case 'lt': case 'lte':
      if (typeof actual !== 'number' || typeof expected !== 'number' || !Number.isFinite(actual) || !Number.isFinite(expected)) return false;
      return rule.operator === 'gt' ? actual > expected : rule.operator === 'gte' ? actual >= expected : rule.operator === 'lt' ? actual < expected : actual <= expected;
    case 'contains': return typeof actual === 'string' && typeof expected === 'string' ? actual.includes(expected) : Array.isArray(actual) && actual.includes(expected);
    case 'truthy': return actual === true || (typeof actual === 'number' && Number.isFinite(actual) && actual !== 0) || (typeof actual === 'string' && actual.length > 0);
    case 'falsy': return actual === false || actual === 0 || actual === '' || actual === null;
    default: return false;
  }
}

export function appearance(item, data) {
  const result = { textColor: item.textColor, backgroundColor: item.backgroundColor, iconColor: item.iconColor, visible: true };
  for (const rule of item.rules || []) if (ruleMatches(rule, data)) {
    if (rule.target === 'visible') result.visible = rule.visible;
    else if (['textColor', 'backgroundColor', 'iconColor'].includes(rule.target)) result[rule.target] = rule.color;
  }
  return result;
}

export function contentStyle(item, data) {
  const colors = appearance(item, data);
  return { color: colors.textColor || undefined, backgroundColor: colors.backgroundColor || undefined,
    '--widget-text-color': colors.textColor || undefined, '--widget-icon-color': colors.iconColor || undefined,
    '--widget-font-size': item.fontSize ? `${item.fontSize}px` : undefined, textAlign: item.align || 'left',
    '--widget-justify': item.align === 'center' ? 'center' : item.align === 'right' ? 'flex-end' : 'flex-start',
    '--widget-icon-margin': item.align === 'center' ? 'auto' : item.align === 'right' ? 'auto 0' : '0 auto' };
}

export function itemFits(item, widget) {
  if (![item.row, item.column, item.rowSpan, item.columnSpan].every(Number.isInteger) || item.row < 0 || item.column < 0 || item.rowSpan < 1 || item.columnSpan < 1 || item.row + item.rowSpan > widget.rows.length || item.column + item.columnSpan > widget.columns.length) return false;
  return widget.allowOverlap === true || widget.items.every(other => other.id === item.id || item.column + item.columnSpan <= other.column || item.column >= other.column + other.columnSpan || item.row + item.rowSpan <= other.row || item.row >= other.row + other.rowSpan);
}

export function firstItemSpace(item, widget) {
  for (let row = 0; row < widget.rows.length; row++) for (let column = 0; column < widget.columns.length; column++) {
    const candidate = { ...item, row, column };
    if (itemFits(candidate, { ...widget, allowOverlap: false })) return candidate;
  }
  const candidate = { ...item, row: 0, column: 0 };
  return widget.allowOverlap === true && itemFits(candidate, widget) ? candidate : null;
}

export function usesSource(widget, source) {
  return [widget, ...(widget.items || [])].some(item => (['value', 'list'].includes(item.kind) && item.source === source) || item.rules?.some(rule => rule.source === source));
}

export function listPage(value) {
  return { rows: Array.isArray(value) ? value.slice(0, 100) : [], truncated: Array.isArray(value) && value.length > 100 };
}
