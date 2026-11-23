import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { createSSRApp } from 'vue';
import { renderToString } from 'vue/server-renderer';

test('condition editor preserves legacy rules, escapes values, and enforces editing bounds', async () => {
  const server = await createServer({server:{middlewareMode:true,watch:null,ws:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom'});
  try {
    const {default:Editor} = await server.ssrLoadModule('/frontend/ConditionEditor.vue');
    const {ruleCondition,conditionCount} = await server.ssrLoadModule('/frontend/conditions.ts');
    const legacy = {source:'system',path:'flag',operator:'eq',value:false};
    const leaf = ruleCondition(legacy);
    assert.deepEqual(leaf,{...legacy,kind:'comparison'});
    assert.equal(legacy.condition,undefined);
    const group = {kind:'or',children:[leaf,{kind:'and',children:[leaf]}]};
    assert.equal(ruleCondition({condition:group}),group);
    assert.equal(conditionCount(group),4);
    const render = (modelValue, extra={}) => renderToString(createSSRApp(Editor,{modelValue,sources:[],remaining:32-conditionCount(modelValue),...extra}));
    const atDepthLimit = await render(leaf,{depth:4});
    assert.match(atDepthLimit, /<button[^>]*disabled[^>]*>Combine<\/button>/);
    const atNodeLimit = await render(group,{remaining:0});
    assert.match(atNodeLimit, /<button[^>]*disabled[^>]*>Add group<\/button>/);
    assert.match(atNodeLimit, /<button[^>]*disabled[^>]*>[\s\S]*?Add condition<\/button>/);
    const atChildLimit = await render({kind:'and',children:Array(16).fill(leaf)});
    assert.match(atChildLimit, /<button[^>]*disabled[^>]*>Add group<\/button>/);
    const single = await render({kind:'and',children:[leaf]});
    assert.ok(!single.includes('aria-label="Remove condition"'));
    assert.ok(single.includes('Ungroup'));
    const hostile = await render({...leaf,value:'<script>alert(1)</script>'});
    assert.ok(!hostile.includes('<script>'));
    assert.ok(hostile.includes('&lt;script&gt;'));
  } finally { await server.close(); }
});
