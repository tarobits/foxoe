import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

test('content script updates remove retired listeners and Home overlays without reloading the page', async () => {
  const code = await readFile(new URL('../extension/content.js', import.meta.url), 'utf8');
  const pageListeners = new Set(), bridgeListeners = new Set(), hosts = new Set(), posts = [];
  const window = { addEventListener(_, fn) { pageListeners.add(fn); }, removeEventListener(_, fn) { pageListeners.delete(fn); }, postMessage(value) { posts.push(value); } };
  const document = { createElement() { return { attachShadow() { return { append() {} }; }, addEventListener() {}, remove() { hosts.delete(this); } }; }, documentElement: { append(host) { hosts.add(host); } } };
  const chrome = { i18n: { getMessage: () => 'Home' }, runtime: { onMessage: { addListener(fn) { bridgeListeners.add(fn); }, removeListener(fn) { bridgeListeners.delete(fn); } }, async sendMessage() { return { type: 'ack' }; } } };
  const context = vm.createContext({ window, document, chrome, location: { href: 'https://app.test/', origin: 'https://app.test' }, __foxoeBuild: 'first' });
  vm.runInContext(code, context);
  vm.runInContext(code, context);
  assert.equal(pageListeners.size, 1);
  assert.equal(bridgeListeners.size, 1);
  assert.equal(hosts.size, 1);
  const oldHandler = [...pageListeners][0];
  context.__foxoeBuild = 'second';
  vm.runInContext(code, context);
  assert.equal(pageListeners.size, 1);
  assert.ok(!pageListeners.has(oldHandler));
  assert.equal(bridgeListeners.size, 1);
  assert.equal(hosts.size, 1);
  assert.equal(posts.at(-1).connected, false);
});
