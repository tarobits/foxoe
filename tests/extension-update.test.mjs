import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { extensionUpdater } from '../extension/update.js';

test('extension policy permits reading its build fingerprint and only the local service', async () => {
  const manifest = JSON.parse(await readFile(new URL('../extension/manifest.json', import.meta.url)));
  const directive = manifest.content_security_policy.extension_pages.split(';').map(value => value.trim()).find(value => value.startsWith('connect-src '));
  assert.deepEqual(directive.split(/\s+/).slice(1).sort(), ["'self'", 'http://127.0.0.1:8765', 'ws://127.0.0.1:8765'].sort());
});

const old = 'a'.repeat(64), next = 'b'.repeat(64);
function harness() {
  const storage = {}; let reloads = 0, disk = next, fail = false;
  const chrome = { storage: { local: { async get() { return {...storage}; }, async set(value) { Object.assign(storage, value); } } }, runtime: { getURL: path => `chrome-extension://test/${path}`, reload() { reloads++; } } };
  const fetch = async url => { assert.equal(url, 'chrome-extension://test/build.json'); if (fail) throw new Error('disk unavailable'); return { ok: true, async json() { return {build: disk}; } }; };
  return { chrome, fetch, storage, get reloads() { return reloads; }, set disk(value) { disk = value; }, set fail(value) { fail = value; } };
}
test('updates serialize reloads, verify local files, and prevent loops across worker restarts', async () => {
  const h = harness(); const update = extensionUpdater(h.chrome, h.fetch, old);
  await Promise.all([update(next), update(next), update(next)]);
  assert.equal(h.reloads, 1);
  await extensionUpdater(h.chrome, h.fetch, old)(next);
  assert.equal(h.reloads, 1);
  await extensionUpdater(h.chrome, h.fetch, next)(next);
  assert.equal(h.reloads, 1);
  // A completed rollback must also be reloadable.
  h.disk = old;
  await extensionUpdater(h.chrome, h.fetch, next)(old);
  assert.equal(h.reloads, 2);
});
test('bad advertisements and stale or failed disk reads do not reload and can recover', async () => {
  const h = harness(); const update = extensionUpdater(h.chrome, h.fetch, old);
  for (const value of [undefined, null, '', 'https://evil.test/code.js', old]) assert.equal(await update(value), false);
  h.disk = old; assert.equal(await update(next), false);
  h.disk = next; h.fail = true; assert.equal(await update(next), false);
  assert.equal(h.reloads, 0);
  h.fail = false; assert.equal(await update(next), true);
  assert.equal(h.reloads, 1);
});
