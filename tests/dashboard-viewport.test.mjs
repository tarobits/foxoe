import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { effectScope, ref, nextTick } from 'vue';

test('dashboard fitting preserves the complete canvas and scaled drag distances', async () => {
  const server = await createServer({server:{middlewareMode:true,watch:null,ws:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom'});
  try {
    const {dashboardFit, dashboardDragDelta} = await server.ssrLoadModule('/frontend/dashboardViewport.ts');
    for (const [width,height,rows] of [[968,360,8],[968,240,48],[358,600,8],[1920,1080,4]]) {
      const result = dashboardFit(width,height,rows);
      assert.ok(result.width * result.scale <= width + .001);
      assert.ok(result.height * result.scale <= height + .001);
      assert.ok(result.scale > 0 && result.scale <= 1);
      assert.equal(result.height, rows * 48 + (rows - 1) * 8 + 8);
      assert.deepEqual(dashboardDragDelta(result.width / 24 * result.scale * 3, -56 * result.scale * 2, result.scale, result.width), {x:3,y:-2});
    }
    for (const [width,height] of [[0,360],[-1,300],[NaN,300],[500,Infinity],[500,0]]) {
      const result = dashboardFit(width,height,8);
      assert.equal(result.scale, 0);
      assert.ok(Number.isFinite(result.width) && Number.isFinite(result.height));
    }
    assert.deepEqual(dashboardDragDelta(1,1,0,968), {x:0,y:0});
    assert.deepEqual(dashboardDragDelta(Infinity,1,1,968), {x:0,y:0});
    assert.equal(dashboardFit(968,360,NaN).height, 112);
  } finally { await server.close(); }
});

test('viewport observes resizes, ignores retired callbacks, and disconnects on teardown', async () => {
  const server = await createServer({server:{middlewareMode:true,watch:null,ws:false},optimizeDeps:{noDiscovery:true,entries:[]},appType:'custom'});
  const original = globalThis.ResizeObserver, observers = [], scope = effectScope();
  globalThis.ResizeObserver = class {
    constructor(callback) { this.callback = callback; observers.push(this); }
    observe(target) { this.target = target; }
    disconnect() { this.disconnected = true; }
    resize(width,height) { this.callback([{target:this.target,contentRect:{width,height}}]); }
  };
  try {
    const {useDashboardViewport} = await server.ssrLoadModule('/frontend/dashboardViewport.ts');
    const target = ref(), rows = ref(8);
    const fit = scope.run(() => useDashboardViewport(target, rows));
    assert.equal(fit.value.scale, 0);
    target.value = {}; await nextTick();
    observers[0].resize(968,336);
    assert.equal(fit.value.scale, .75);
    observers[0].resize(968,224); assert.equal(fit.value.scale, .5);
    rows.value = 4; assert.equal(fit.value.scale, 1);
    target.value = undefined; await nextTick();
    assert.ok(observers[0].disconnected);
    observers[0].resize(968,999); assert.equal(fit.value.scale, 0);
    target.value = {}; await nextTick(); observers[1].resize(484,300);
    assert.equal(fit.value.scale, .5);
    scope.stop(); assert.ok(observers[1].disconnected);
    observers[1].resize(968,300); assert.equal(fit.value.scale, .5);
  } finally { scope.stop(); globalThis.ResizeObserver = original; await server.close(); }
});
