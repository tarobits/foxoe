import test from 'node:test';
import assert from 'node:assert/strict';
import { ruleMatches, appearance, itemFits, firstItemSpace, usesSource } from '../frontend/model.js';
import { createServer } from 'vite';
import { createSSRApp } from 'vue';
import { renderToString } from 'vue/server-renderer';

const data = { system: { value: { count: 0, text: 'ready', flag: false, nil: null, items: ['a', 'b'] }, error: null } };
const rule = (operator, path, value) => ({ source: 'system', operator, path, value });
test('rules compare types explicitly and distinguish zero, false, null, and missing', () => {
  for (const [op, path, value, expected] of [
    ['eq','count',0,true], ['eq','count','0',false], ['ne','count','0',true],
    ['gt','count',-1,true], ['gte','count',0,true], ['lt','count',1,true], ['lte','count',0,true],
    ['gt','text',0,false], ['gt','count','-1',false], ['eq','flag',false,true],
    ['exists','count',null,true], ['exists','flag',null,true], ['exists','nil',null,false],
    ['missing','absent',null,true], ['eq','absent',null,false], ['ne','absent',0,false],
    ['truthy','text',null,true], ['falsy','count',null,true], ['falsy','flag',null,true],
    ['contains','text','ead',true], ['contains','items','a',true], ['contains','items',0,false],
  ]) assert.equal(ruleMatches(rule(op, path, value), data), expected, `${op} ${path}`);
  for (const operator of ['eq','ne','missing','exists','falsy']) {
    assert.equal(ruleMatches(rule(operator, 'absent', null), {}), false);
    assert.equal(ruleMatches(rule(operator, 'absent', null), { system: {...data.system, error:'offline'} }), false);
  }
  assert.equal(ruleMatches(rule('eval', 'constructor', 'alert(1)'), data), false);
  assert.equal(ruleMatches(rule('eq', '__proto__.constructor', null), data), false);
});
test('matching rules apply in order without mutating configuration or stale data', () => {
  const widget = { textColor: '#ffffff', rules: [
    {...rule('eq','count',0), target:'textColor', color:'#ff0000'},
    {...rule('eq','flag',false), target:'textColor', color:'#00ff00'},
    {...rule('eq','count',0), target:'visible', visible:false},
  ] };
  const original = structuredClone(widget);
  assert.deepEqual(appearance(widget, data), { textColor:'#00ff00', backgroundColor:undefined, iconColor:undefined, visible:false });
  assert.equal(appearance(widget, {}).textColor, '#ffffff');
  assert.equal(appearance(widget, {}).visible, true);
  assert.deepEqual(widget, original);
});
test('item spans reject overlaps and retain references used in rules and child items', () => {
  const child = {id:'child', kind:'value', source:'queue', row:0, column:0, rowSpan:1, columnSpan:1, rules:[]};
  const widget = {kind:'layout', columns:[2,1], rows:[1], items:[child], rules:[{source:'status'}]};
  assert.ok(itemFits({...child, id:'other', column:1}, widget));
  assert.ok(!itemFits({...child, id:'other'}, widget));
  assert.ok(!itemFits({...child, column:1, columnSpan:2}, widget));
  assert.ok(!itemFits({...child, row:.5}, widget));
  assert.ok(usesSource(widget, 'queue')); assert.ok(usesSource(widget, 'status'));
  assert.ok(!usesSource(widget, 'unrelated'));
});

test('item overlap opt-in permits shared cells while retaining bounds', () => {
  const first = {id:'first', row:0, column:0, rowSpan:1, columnSpan:1};
  const widget = {rows:[1], columns:[1,1], items:[first], allowOverlap:true};
  assert.ok(itemFits({...first, id:'second'}, widget));
  assert.ok(!itemFits({...first, id:'second'}, {...widget, allowOverlap:false}));
  assert.ok(!itemFits({...first, id:'second'}, {...widget, allowOverlap:'true'}));
  const second = {...first, id:'second'};
  assert.equal(firstItemSpace(second, widget).column, 1);
  const full = {...widget, columns:[1]};
  assert.equal(firstItemSpace(second, full).column, 0);
  assert.equal(firstItemSpace(second, {...full, allowOverlap:false}), null);
  assert.equal(firstItemSpace({...second, columnSpan:3}, full), null);
  for (const change of [{row:1}, {column:2}, {rowSpan:2}, {columnSpan:3}, {column:.5}, {rowSpan:0}]) {
    assert.ok(!itemFits({...first, id:'second', ...change}, widget));
  }
});

test('composed widgets render live values, escape content, and reveal hidden items only in editing', async () => {
  const server = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, optimizeDeps: { noDiscovery: true, entries: [] }, appType: 'custom' });
  try {
    const { default: WidgetContent } = await server.ssrLoadModule('/frontend/WidgetContent.vue');
    const common = { title:'', text:'', source:'system', path:'count', itemPath:'', unit:'', rules:[], row:0, column:0, rowSpan:1, columnSpan:1 };
    const widget = { kind:'layout', title:'Station', columns:[2,1], rows:[1,1], gap:8, rules:[], items:[
      {...common, id:'value', kind:'value', textColor:'#123456', fontSize:24},
      {...common, id:'text', kind:'text', column:1, text:'<script>alert(1)</script>'},
      {...common, id:'icon', kind:'icon', row:1, icon:'user', rules:[{...rule('eq','count',0), target:'visible', visible:false}]},
    ] };
    const render = editing => renderToString(createSSRApp(WidgetContent, {widget, data, now:new Date('2026-11-23T12:00:00Z'), editing}));
    const display = await render(false), editor = await render(true);
    assert.match(display, /minmax\(0, 2fr\)/);
    assert.match(display, /--widget-font-size:24px/);
    assert.match(display, /#123456/);
    assert.match(display, /<span>0<\/span>/);
    assert.ok(display.includes('&lt;script&gt;'));
    assert.ok(!display.includes('<script>'));
    assert.match(display, /display:none/);
    assert.ok(!editor.includes('display:none'));
    assert.match(editor, /rule-hidden/);
    const { default: WidgetEditor } = await server.ssrLoadModule('/frontend/WidgetEditor.vue');
    const full = {...widget, columns:[1], rows:[1], items:[widget.items[0]], allowOverlap:false};
    const renderEditor = widget => renderToString(createSSRApp(WidgetEditor, {widget, sources:[], data, now:new Date()}));
    const blocked = await renderEditor(full);
    assert.match(blocked, /<button[^>]*disabled[^>]*>[\s\S]*?Add item/);
    const allowed = await renderEditor({...full, allowOverlap:true});
    assert.match(allowed.match(/<input[^>]*type="checkbox"[^>]*>/)[0], /\bchecked\b/);
    const addButton = allowed.match(/<button[^>]*>[\s\S]*?Add item<\/button>/)[0];
    assert.ok(!addButton.includes('disabled'));
    const capped = await renderEditor({...full, allowOverlap:true, items:Array.from({length:24}, (_, n) => ({...full.items[0], id:`item-${n}`}))});
    assert.match(capped, /<button[^>]*disabled[^>]*>[\s\S]*?Add item/);
  } finally { await server.close(); }
});
