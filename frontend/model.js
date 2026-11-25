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

/** @param {number | null} [decimals] */
export function formatValue(value, locale, decimals = null) {
  if (typeof value === 'boolean') return String(value);
  if (typeof value === 'number' && Number.isFinite(value)) return new Intl.NumberFormat(locale, decimals == null ? { maximumFractionDigits: 2 } : { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);
  if (typeof value === 'string') return value;
  return null;
}

export function widgetTitle(widget, data) {
  const title = data ? appearance(widget, data).title ?? widget.title : widget.title;
  return widget.showTitle === false ? '' : (title || '').trim();
}

function compare(rule, data) {
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

/** Bounded, non-executable boolean trees. null means unavailable/invalid, never NOT true. */
export function conditionResult(condition, data) {
  let count = 0;
  function visit(node, depth) {
    if (!node || typeof node !== 'object' || ++count > 32 || depth > 4 || (node.negate !== undefined && typeof node.negate !== 'boolean')) return null;
    let result;
    if (node.kind === 'comparison') {
      if (typeof node.source !== 'string' || typeof node.path !== 'string' || !['eq','ne','gt','gte','lt','lte','contains','exists','missing','truthy','falsy'].includes(node.operator)) return null;
      if (node.value !== null && !['string','number','boolean'].includes(typeof node.value) || typeof node.value === 'number' && !Number.isFinite(node.value)) return null;
      const entry = Object.hasOwn(data, node.source) ? data[node.source] : null;
      if (!entry || entry.error) return null;
      result = compare(node, data);
    } else if (node.kind === 'and' || node.kind === 'or') {
      if (!Array.isArray(node.children) || !node.children.length || node.children.length > 16) return null;
      const values = node.children.map(child => visit(child, depth + 1));
      if (values.includes(null)) return null;
      result = node.kind === 'and' ? values.every(Boolean) : values.some(Boolean);
    } else return null;
    return node.negate ? !result : result;
  }
  return visit(condition, 0);
}

export function ruleMatches(rule, data) {
  return rule.condition != null ? conditionResult(rule.condition, data) === true : compare(rule, data);
}

export function appearance(item, data) {
  /** @type {{ textColor?: string | null, backgroundColor?: string | null, iconColor?: string | null, visible: boolean, text?: string, title?: string, icon?: import('./icons').IconName | null }} */
  const result = { textColor: item.textColor, backgroundColor: item.backgroundColor, iconColor: item.iconColor, visible: true };
  for (const rule of item.rules || []) if (ruleMatches(rule, data)) {
    for (const action of rule.actions ?? [rule]) {
      if (action.target === 'visible') result.visible = action.visible;
      else if (['textColor', 'backgroundColor', 'iconColor'].includes(action.target)) result[action.target] = action.color;
      else if (['text', 'title'].includes(action.target) && typeof action.text === 'string') result[action.target] = action.text;
      else if (action.target === 'icon') result.icon = action.icon;
    }
  }
  return result;
}

export function contentStyle(item, data) {
  const colors = appearance(item, data);
  return { color: colors.textColor || undefined, backgroundColor: colors.backgroundColor || undefined,
    '--widget-text-color': colors.textColor || undefined, '--widget-icon-color': colors.iconColor || undefined,
    '--widget-font-size': item.fontSize ? `${item.fontSize}px` : undefined,
    '--widget-font-weight': item.fontWeight ?? undefined, '--widget-font-style': item.italic ? 'italic' : 'normal',
    '--widget-vertical-align': item.verticalAlign === 'top' ? 'flex-start' : item.verticalAlign === 'bottom' ? 'flex-end' : item.verticalAlign === 'middle' ? 'center' : undefined,
    textAlign: item.align || 'left',
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
  const references = node => node.kind === 'and' || node.kind === 'or' ? node.children.some(references) : node.source === source;
  return [widget, ...(widget.items || [])].some(item => (['value', 'list'].includes(item.kind) && item.source === source) || item.rules?.some(rule => references(rule.condition || rule)));
}

export function listPage(value) {
  return { rows: Array.isArray(value) ? value.slice(0, 100) : [], truncated: Array.isArray(value) && value.length > 100 };
}
