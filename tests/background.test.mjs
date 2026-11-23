import test from 'node:test';
import assert from 'node:assert/strict';

const event = () => ({ handlers: [], addListener(fn) { this.handlers.push(fn); } });
const sockets = [];
const posts = [];
const local = { token: 'synthetic-test-credential' };
const session = { kioskTab: 7 };
let tab = { id: 7, active: true, windowId: 3, status: 'complete', url: 'https://printer.example/app' };
let documentId = 'doc-1';
const storage = data => ({ async get() { return { ...data }; }, async set(value) { Object.assign(data, value); }, async remove(key) { delete data[key]; } });
const chromeMock = {
  storage: { local: storage(local), session: storage(session) },
  runtime: { onMessage: event(), onStartup: event(), getURL: path => `chrome-extension://foxoe/${path}`, async openOptionsPage() {} },
  tabs: { onActivated: event(), onUpdated: event(), onRemoved: event(), async get() { return { ...tab }; }, async query() { return [{ ...tab }]; }, async sendMessage(id, message, target) { posts.push({ id, message, target }); }, async update(id, update) { tab = { ...tab, ...update }; }, async goBack() {}, async reload() {} },
  windows: { onFocusChanged: event(), async get() { return { focused: true }; } },
  scripting: { async executeScript(options) { return options.func ? [{ documentId, result: tab.url }] : []; } },
  action: { onClicked: event() }, alarms: { onAlarm: event(), async create() {} },
};
class Socket {
  static CONNECTING = 0; static OPEN = 1;
  readyState = 0; sent = [];
  constructor() { sockets.push(this); }
  send(value) { this.sent.push(JSON.parse(value)); }
  close() { this.readyState = 3; this.onclose?.(); }
}
globalThis.chrome = chromeMock;
globalThis.WebSocket = Socket;
const originalInterval = globalThis.setInterval;
globalThis.setInterval = () => 0;
await import('../extension/background.js');
const settle = () => new Promise(resolve => setImmediate(resolve));
await settle();

test('browser routing authenticates, scopes documents, and releases controls on tab changes', async () => {
  const socket = sockets[0];
  assert.ok(socket);
  socket.readyState = 1; socket.onopen();
  assert.deepEqual(socket.sent[0], { token: local.token });
  await socket.onmessage({ data: JSON.stringify({ type: 'configuration', config: { locale: 'en', apps: [{ id: 'printer', url: tab.url }] } }) });
  const context = socket.sent.findLast(message => message.type === 'context');
  assert.equal(context.document, 'doc-1');
  await socket.onmessage({ data: JSON.stringify({ type: 'ack', request: context.request, generation: 2 }) });
  await settle();
  assert.ok(posts.some(post => post.message.type === 'connection' && post.message.connected));
  const listener = chromeMock.runtime.onMessage.handlers[0];
  const sender = { frameId: 0, tab, documentId, url: tab.url };
  let response;
  listener({ type: 'layout', operation: 'screen', layout: 'main' }, { ...sender, frameId: 1 }, result => { response = result; });
  assert.equal(response.error, 'inactive_document');
  listener({ type: 'layout', operation: 'screen', layout: 'main' }, sender, result => { response = result; });
  const layout = socket.sent.at(-1);
  assert.equal(layout.type, 'layout');
  await socket.onmessage({ data: JSON.stringify({ type: 'ack', request: layout.request, generation: 3 }) });
  assert.equal(response.type, 'ack');
  await socket.onmessage({ data: JSON.stringify({ type: 'action', document: 'doc-1', generation: 3, id: 'print', layout: 'main' }) });
  assert.equal(posts.at(-1).message.id, 'print');
  const count = posts.filter(post => post.message.type === 'action').length;
  await socket.onmessage({ data: JSON.stringify({ type: 'action', document: 'old-document', generation: 3, id: 'print' }) });
  assert.equal(posts.filter(post => post.message.type === 'action').length, count);
  tab.active = false;
  chromeMock.tabs.onActivated.handlers[0]();
  await settle();
  assert.equal(socket.sent.at(-1).type, 'inactive');
  listener({ type: 'layout', operation: 'screen', layout: 'main' }, sender, result => { response = result; });
  assert.equal(response.error, 'inactive_document');
  tab.active = true;
  documentId = 'doc-2';
  chromeMock.tabs.onActivated.handlers[0]();
  await settle();
  const next = socket.sent.at(-1);
  assert.equal(next.document, 'doc-2');
  await socket.onmessage({ data: JSON.stringify({ type: 'ack', request: next.request, generation: 5 }) });
  await settle();
  socket.close();
  assert.equal(posts.at(-1).message.connected, false);
  globalThis.setInterval = originalInterval;
});
