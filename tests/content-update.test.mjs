import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';

test('content script updates remove retired listeners and Home overlays without reloading the page', async () => {
  const code = await readFile(new URL('../extension/content.js', import.meta.url), 'utf8');
  const pageListeners = new Set(), bridgeListeners = new Set(), hosts = new Set(), posts = [], sent = [];
  const documentListeners = new Map();
  function element(tag) {
    return { tag, children: [], attributes: {}, listeners: {},
      append(...children) { this.children.push(...children); },
      attachShadow() { this.shadow = element('shadow'); return this.shadow; },
      addEventListener(name, fn) { this.listeners[name] = fn; },
      setAttribute(name, value) { this.attributes[name] = value; },
      focus() { this.focused = true; }, remove() { hosts.delete(this); },
    };
  }
  const window = { addEventListener(_, fn) { pageListeners.add(fn); }, removeEventListener(_, fn) { pageListeners.delete(fn); }, postMessage(value) { posts.push(value); } };
  const document = { createElement: element, createElementNS: (_, tag) => element(tag),
    addEventListener(name, fn) { if (!documentListeners.has(name)) documentListeners.set(name, new Set()); documentListeners.get(name).add(fn); },
    removeEventListener(name, fn) { documentListeners.get(name)?.delete(fn); },
    documentElement: { append(host) { hosts.add(host); } } };
  const chrome = { i18n: { getMessage: key => key }, runtime: { onMessage: { addListener(fn) { bridgeListeners.add(fn); }, removeListener(fn) { bridgeListeners.delete(fn); } }, async sendMessage(message) { sent.push(message); return { type: 'ack' }; } } };
  const context = vm.createContext({ window, document, chrome, location: { href: 'https://app.test/', origin: 'https://app.test' }, __foxoeBuild: 'first' });
  vm.runInContext(code, context);
  vm.runInContext(code, context);
  assert.equal(pageListeners.size, 1);
  assert.equal(bridgeListeners.size, 1);
  assert.equal(hosts.size, 1);
  const host = [...hosts][0], toolbar = host.shadow.children[1], [toggle, home] = toolbar.children;
  assert.equal(toggle.attributes['aria-expanded'], 'false');
  assert.equal(home.tabIndex, -1);
  toggle.listeners.click();
  assert.equal(toggle.attributes['aria-expanded'], 'true');
  assert.equal(home.tabIndex, 0);
  assert.equal(sent.length, 0); // Revealing the control must not navigate.
  const pointer = [...documentListeners.get('pointerdown')][0];
  pointer({composedPath: () => [host]});
  assert.equal(toggle.attributes['aria-expanded'], 'true');
  pointer({composedPath: () => []});
  assert.equal(toggle.attributes['aria-expanded'], 'false');
  toggle.listeners.click();
  [...documentListeners.get('keydown')][0]({key:'Escape'});
  assert.equal(toggle.attributes['aria-expanded'], 'false');
  assert.equal(toggle.focused, true);
  toggle.listeners.click();
  toggle.listeners.click();
  assert.equal(home.tabIndex, -1);
  toggle.listeners.click();
  home.listeners.click();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].type, 'home');
  assert.equal(toggle.attributes['aria-expanded'], 'false');
  const oldHandler = [...pageListeners][0];
  context.__foxoeBuild = 'second';
  vm.runInContext(code, context);
  assert.equal(pageListeners.size, 1);
  assert.ok(!pageListeners.has(oldHandler));
  assert.equal(bridgeListeners.size, 1);
  assert.equal(hosts.size, 1);
  assert.equal(posts.at(-1).connected, false);
  assert.equal(documentListeners.get('pointerdown').size, 1);
  assert.equal(documentListeners.get('keydown').size, 1);
  context.__foxoeBridge.dispose();
  assert.equal(hosts.size, 0);
  assert.equal(documentListeners.get('pointerdown').size, 0);
  assert.equal(documentListeners.get('keydown').size, 0);
});
