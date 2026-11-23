import test from 'node:test';
import assert from 'node:assert/strict';
import { allowedApp, validSender } from '../extension/protocol.js';
import { createDeck, keypadLayout } from '../sdk/foxoe.js';
import { readFile } from 'node:fs/promises';

const apps = [{ id: 'printer', url: 'https://printer.example/app' }];
test('app access matches origins and path boundaries', () => {
  assert.equal(allowedApp('https://printer.example/app/job', apps)?.id, 'printer');
  for (const url of ['https://printer.example/app-evil', 'https://printer.example.evil/app', 'http://printer.example/app', 'https://user@printer.example/app', 'javascript:alert(1)']) {
    assert.equal(allowedApp(url, apps), null);
  }
});
test('only the selected tab and top-level current document can supply actions', () => {
  const sender = { frameId: 0, tab: { id: 4 }, documentId: 'current', url: apps[0].url };
  assert.ok(validSender(sender, 4, 'current', apps));
  assert.ok(!validSender({ ...sender, frameId: 1 }, 4, 'current', apps));
  assert.ok(!validSender(sender, 5, 'current', apps));
  assert.ok(!validSender(sender, 4, 'old', apps));
});
test('keypad leaves the reserved Home slot free and labels every action', () => {
  const layout = keypadLayout({ backspace: 'Delete', cancel: 'Cancel', confirm: 'Done' });
  assert.equal(layout.buttons.length, 14);
  assert.equal(new Set(layout.buttons.filter(Boolean).map(button => button.id)).size, 13);
});

function fakeWindow() {
  let listener;
  const messages = [];
  const win = {
    location: { origin: 'https://printer.example' },
    addEventListener: (_, fn) => { listener = fn; },
    removeEventListener: () => { listener = null; },
    postMessage: message => messages.push(message),
    receive: (data, overrides = {}) => listener?.({ source: win, origin: win.location.origin, data: { source: 'foxoe:bridge', ...data }, ...overrides }),
  };
  return { win, messages };
}
test('SDK rejects disconnected requests and ignores messages from other frames', async () => {
  const { win } = fakeWindow();
  const deck = createDeck(win);
  await assert.rejects(deck.show({ id: 'main', buttons: [] }), /disconnected/);
  win.receive({ type: 'connection', connected: true }, { source: {} });
  assert.equal(deck.connected, false);
  win.receive({ type: 'connection', connected: true });
  assert.equal(deck.connected, true);
  deck.dispose();
});
test('SDK requests are acknowledged, and disposal releases pending requests', async () => {
  const { win, messages } = fakeWindow();
  const deck = createDeck(win);
  win.receive({ type: 'connection', connected: true });
  const request = deck.show({ id: 'main', buttons: [] });
  win.receive({ type: 'ack', request: messages.at(-1).request });
  await request;
  const pending = deck.pop();
  deck.dispose();
  await assert.rejects(pending, /disposed/);
  await assert.rejects(deck.pop(), /disposed/);
});
test('extension locale catalogs contain the same keys', async () => {
  const read = async lang => JSON.parse(await readFile(new URL(`../extension/_locales/${lang}/messages.json`, import.meta.url), 'utf8'));
  assert.deepEqual(Object.keys(await read('en')).sort(), Object.keys(await read('de')).sort());
});
