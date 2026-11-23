import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { effectScope, reactive } from 'vue';

test('preview snapshots use current drafts, ignore stale requests, and recover after errors', async () => {
  const server = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, optimizeDeps: { noDiscovery: true, entries: [] }, appType: 'custom' });
  const scope = effectScope();
  try {
    const { useSourcePreview } = await server.ssrLoadModule('/frontend/sourcePreview.ts');
    const source = reactive({ id: 'new', name: 'New', url: 'https://example.test/one', interval: 15, authEnv: '' });
    const pending = [];
    let expired = 0;
    const request = (url, options) => new Promise((resolve, reject) => pending.push({ url, options, resolve, reject }));
    const state = scope.run(() => useSourcePreview(() => source, () => expired++, request));
    const respond = (index, value, status = 200) => pending[index].resolve({ ok: status === 200, status, async json() { return value; } });
    const first = state.refresh();
    await state.refresh();
    assert.equal(pending.length, 1, 'Repeated clicks must not start concurrent requests');
    assert.equal(JSON.parse(pending[0].options.body).url, source.url);
    source.url = 'https://example.test/two';
    assert.equal(pending[0].options.signal.aborted, true);
    assert.equal(state.open.value, false);
    const second = state.refresh();
    respond(1, { value: false, updatedAt: 123, error: null }); await second;
    respond(0, { value: 'stale', updatedAt: 1, error: null }); await first;
    assert.equal(state.result.value.value, false);
    assert.equal(state.result.value.updatedAt, 123);
    assert.equal(pending.length, 2, 'Snapshots do not poll automatically');
    const failed = state.refresh();
    assert.equal(state.result.value, undefined, 'Do not present the old result as fresh');
    respond(2, { error: 'upstream-private-message' }, 502); await failed;
    assert.equal(state.error.value, 'sourcePreviewFailed');
    const retry = state.refresh(); respond(3, { value: null, updatedAt: 124, error: null }); await retry;
    assert.equal(state.result.value.value, null);
    const closing = state.refresh(); state.close(); respond(4, { value: 'late' }); await closing;
    assert.equal(state.open.value, false); assert.equal(state.result.value, undefined);
    const unauthorized = state.refresh(); respond(5, {}, 401); await unauthorized;
    assert.equal(expired, 1); assert.equal(state.open.value, false);
    const disposed = state.refresh(); scope.stop(); respond(6, { value: 'disposed' }); await disposed;
    assert.equal(pending[6].options.signal.aborted, true); assert.equal(state.result.value, undefined);
  } finally { scope.stop(); await server.close(); }
});
