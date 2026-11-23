import test from 'node:test';
import assert from 'node:assert/strict';

const event = () => ({ handlers: [], addListener(fn) { this.handlers.push(fn); } });
const settle = () => new Promise(resolve => setImmediate(resolve));
let sequence = 0;
async function browser(t, { failFirstProbe = false, failFirstInjection = false, holdStorage = false } = {}) {
  const originals = Object.fromEntries(['chrome', 'WebSocket', 'setInterval', 'clearInterval', 'setTimeout', 'clearTimeout'].map(key => [key, globalThis[key]]));
  t.after(() => Object.assign(globalThis, originals));
  const sockets = [], retries = new Map(), posts = [];
  let releaseStorage;
  const storageReady = new Promise(resolve => { releaseStorage = resolve; });
  if (!holdStorage) releaseStorage();
  let timer = 0, probes = 0, injections = 0;
  const tab = { id: 7, active: true, windowId: 3, status: 'complete', url: 'http://127.0.0.1:8765/' };
  const storage = data => ({ async get() { await storageReady; return { ...data }; }, async set(value) { Object.assign(data, value); }, async remove(key) { delete data[key]; } });
  const chrome = {
    storage: { local: storage({ token: 'synthetic-test-credential' }), session: storage({ kioskTab: 7 }) },
    runtime: { onMessage: event(), onStartup: event(), getURL: path => `chrome-extension://foxoe/${path}` },
    tabs: { onActivated: event(), onUpdated: event(), onRemoved: event(), async get() { return { ...tab }; }, async query() { return [{ ...tab }]; }, async sendMessage(id, message) { posts.push(message); } },
    windows: { onFocusChanged: event(), async get() { return { focused: true }; } },
    scripting: { async executeScript(options) {
      if (!options.func) {
        if (++injections === 1 && failFirstInjection) throw new Error('Navigation interrupted injection');
        return [];
      }
      if (++probes === 1 && failFirstProbe) throw new Error('Document not ready');
      return [{ documentId: 'initial-document', result: tab.url }];
    } },
    action: { onClicked: event() }, alarms: { onAlarm: event(), async create() {} },
  };
  class Socket {
    static CONNECTING = 0; static OPEN = 1;
    readyState = 0; sent = [];
    constructor() { sockets.push(this); }
    send(value) { this.sent.push(JSON.parse(value)); }
    close() { this.readyState = 3; this.onclose?.(); }
  }
  Object.assign(globalThis, { chrome, WebSocket: Socket,
    setInterval: () => 0, clearInterval: () => {},
    setTimeout: fn => { retries.set(++timer, fn); return timer; }, clearTimeout: id => retries.delete(id),
  });
  await import(`../extension/background.js?startup-test=${++sequence}`);
  return { chrome, sockets, retries, posts, tab, releaseStorage, async authenticate(socket = sockets[0]) {
    socket.readyState = 1; socket.onopen();
    await socket.onmessage({ data: JSON.stringify({ type: 'configuration', config: { locale: 'en', apps: [] } }) });
    await settle();
  } };
}

test('concurrent startup events create only one authenticated browser connection', async t => {
  const b = await browser(t, { holdStorage: true });
  b.chrome.runtime.onStartup.handlers[0]();
  b.chrome.alarms.onAlarm.handlers[0]({ name: 'reconnect' });
  b.releaseStorage();
  await settle();
  assert.equal(b.sockets.length, 1);
  await b.authenticate();
  assert.ok(b.sockets[0].sent.some(message => message.type === 'context'));
});

test('initial document failure retries automatically without saving dashboard settings', async t => {
  const b = await browser(t, { failFirstProbe: true });
  await settle();
  await b.authenticate();
  assert.ok(b.retries.size > 0, 'A transient initial failure must schedule a retry');
  for (const [id, retry] of [...b.retries]) { b.retries.delete(id); retry(); }
  await settle();
  const socket = b.sockets[0];
  const context = socket.sent.findLast(message => message.type === 'context');
  assert.equal(context?.document, 'initial-document');
  await socket.onmessage({ data: JSON.stringify({ type: 'ack', request: context.request, generation: 3 }) });
  await settle();
  assert.equal(b.retries.size, 0);
});

test('stale retry cannot reactivate an unfocused tab after navigation invalidation', async t => {
  const b = await browser(t, { failFirstProbe: true });
  await settle(); await b.authenticate();
  const oldRetries = [...b.retries.values()];
  assert.ok(oldRetries.length);
  b.tab.active = false;
  b.chrome.tabs.onActivated.handlers[0]();
  await settle();
  for (const retry of oldRetries) retry();
  await settle();
  assert.equal(b.sockets[0].sent.filter(message => message.type === 'context').length, 0);
});

test('failed content injection retries and disconnect cancels pending page setup', async t => {
  const b = await browser(t, { failFirstInjection: true });
  await settle(); await b.authenticate();
  const socket = b.sockets[0];
  const context = socket.sent.findLast(message => message.type === 'context');
  await socket.onmessage({ data: JSON.stringify({ type: 'ack', request: context.request, generation: 3 }) });
  await settle();
  assert.ok(b.retries.size);
  const retry = [...b.retries.values()][0];
  retry(); await settle();
  assert.equal(socket.sent.filter(message => message.type === 'context').length, 2);
  socket.close();
  assert.equal(b.retries.size, 0);
  retry(); await settle();
  assert.equal(socket.sent.filter(message => message.type === 'context').length, 2);
});

test('options reconnect cancels pending startup and ignores retired socket messages', async t => {
  const b = await browser(t, { holdStorage: true });
  b.chrome.runtime.onMessage.handlers[0]({ type: 'reconnect' }, { url: b.chrome.runtime.getURL('options.html') }, () => {});
  b.releaseStorage(); await settle();
  assert.equal(b.sockets.length, 1);
  await b.authenticate();
  const retired = b.sockets[0];
  b.chrome.runtime.onMessage.handlers[0]({ type: 'reconnect' }, { url: b.chrome.runtime.getURL('options.html') }, () => {});
  await settle();
  assert.equal(b.sockets.length, 2);
  const current = b.sockets[1];
  await b.authenticate(current);
  const before = current.sent.length;
  await retired.onmessage({ data: JSON.stringify({ type: 'configuration', config: { apps: [], locale: 'de' } }) });
  assert.equal(current.sent.length, before);
});
