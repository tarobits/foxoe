import { HOME, allowedApp, validSender } from './protocol.js';

let socket;
let heartbeat;
let connecting;
let connectionAttempt = 0;
let authenticated = false;
let contextRetry;
let tabId;
let documentId;
let generation = -1;
let contextSequence = 0;
let config = { apps: [], locale: 'en' };
const requests = new Map();

async function selectHomeTab() {
  if (tabId != null) return;
  const tabs = (await chrome.tabs.query({})).filter(tab => tab.url === HOME);
  if (tabs.length === 1 && tabId == null) {
    tabId = tabs[0].id;
    await chrome.storage.session.set({ kioskTab: tabId });
  }
}

const send = message => {
  if (socket?.readyState !== WebSocket.OPEN) return false;
  socket.send(JSON.stringify(message));
  return true;
};
const post = async message => {
  if (tabId == null || !documentId) return false;
  try { await chrome.tabs.sendMessage(tabId, message, { documentId }); return true; } catch { return false; }
};

function invalidate() {
  clearTimeout(contextRetry);
  contextSequence++;
  void post({ type: 'connection', connected: false });
  documentId = undefined;
  generation = -1;
  send({ type: 'inactive' });
  for (const entry of requests.values()) entry.reply({ type: 'error', error: 'inactive_document' });
  requests.clear();
}

function retryContext(sequence) {
  clearTimeout(contextRetry);
  const current = socket;
  contextRetry = setTimeout(() => {
    if (sequence === contextSequence && socket === current && authenticated) void refreshContext();
  }, 1000);
}

async function refreshContext() {
  invalidate();
  const sequence = contextSequence;
  if (tabId == null || socket?.readyState !== WebSocket.OPEN || !authenticated) return;
  try {
    const tab = await chrome.tabs.get(tabId);
    const win = await chrome.windows.get(tab.windowId);
    if (!tab.active || !win.focused || sequence !== contextSequence) return;
    if (!/^https?:\/\//.test(tab.url || '')) return;
    if (tab.status === 'loading') { retryContext(sequence); return; }
    const frames = await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, func: () => location.href });
    const frame = frames[0];
    if (sequence !== contextSequence) return;
    if (!frame?.documentId) { retryContext(sequence); return; }
    documentId = frame.documentId;
    const request = crypto.randomUUID();
    requests.set(request, { document: documentId, reply: response => {
      if (response.type !== 'ack' || sequence !== contextSequence) return;
      void chrome.scripting.executeScript({ target: { tabId, documentIds: [documentId] }, files: ['content.js'] }).then(async () => {
        if (sequence !== contextSequence) return;
        const delivered = await post({ type: 'connection', connected: Boolean(allowedApp(tab.url, config.apps)), locale: config.locale });
        if (sequence === contextSequence && delivered) clearTimeout(contextRetry);
      }).catch(() => { /* The scheduled retry handles documents not ready yet. */ });
    } });
    send({ type: 'context', url: frame.result, document: documentId, request });
    retryContext(sequence);
  } catch {
    if (sequence === contextSequence) retryContext(sequence);
  }
}

function connect() {
  if (connecting) return connecting;
  if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) return;
  const attempt = connectionAttempt;
  const task = openSocket(attempt).catch(() => {
    if (attempt === connectionAttempt) void chrome.alarms.create('reconnect', { delayInMinutes: 0.5 });
  }).finally(() => { if (connecting === task) connecting = undefined; });
  connecting = task;
  return task;
}

async function openSocket(attempt) {
  const stored = await chrome.storage.local.get(['token']);
  if (!stored.token) return;
  if (tabId == null) {
    const saved = await chrome.storage.session.get('kioskTab');
    if (tabId == null) tabId = saved.kioskTab;
  }
  if (attempt !== connectionAttempt) return;
  await selectHomeTab();
  if (attempt !== connectionAttempt) return;
  const current = new WebSocket('ws://127.0.0.1:8765/bridge');
  socket = current;
  authenticated = false;
  current.onopen = () => {
    if (socket !== current) { current.close(); return; }
    current.send(JSON.stringify({ token: stored.token }));
    heartbeat = setInterval(() => send({ type: 'ping' }), 20000);
  };
  current.onclose = () => {
    if (socket !== current) return;
    clearInterval(heartbeat);
    authenticated = false;
    invalidate();
    socket = undefined;
    void chrome.alarms.create('reconnect', { delayInMinutes: 0.5 });
  };
  current.onmessage = async event => {
    if (socket !== current) return;
    const message = JSON.parse(event.data);
    if (message.type === 'configuration') {
      authenticated = true;
      config = message.config;
      await chrome.storage.local.set({ config });
      if (socket !== current) return;
      await refreshContext();
    } else if (message.type === 'ack' || message.type === 'error') {
      const request = requests.get(message.request);
      requests.delete(message.request);
      if (request && request.document === documentId) {
        if (message.generation != null) generation = message.generation;
        request.reply(message);
      }
    } else if (['launch', 'browser', 'action'].includes(message.type)) {
      const tab = await chrome.tabs.get(tabId).catch(() => null);
      const win = tab ? await chrome.windows.get(tab.windowId).catch(() => null) : null;
      if (!tab?.active || !win?.focused || message.document !== documentId || message.generation !== generation) return;
      if (message.type === 'action') await post(message);
      else if (message.type === 'launch') {
        const app = config.apps.find(item => item.id === message.id);
        if (app) { invalidate(); await chrome.tabs.update(tabId, { url: new URL(app.url, HOME).href }); }
      } else if (message.id === 'home') {
        invalidate(); await chrome.tabs.update(tabId, { url: HOME });
      } else if (message.id === 'back') await chrome.tabs.goBack(tabId).catch(() => {});
      else if (message.id === 'reload') await chrome.tabs.reload(tabId);
    }
  };
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.type === 'reconnect' && sender.url === chrome.runtime.getURL('options.html')) {
    const previous = socket;
    invalidate();
    socket = undefined;
    authenticated = false;
    connectionAttempt++;
    connecting = undefined;
    clearInterval(heartbeat);
    previous?.close();
    void connect();
    reply({ ok: true });
    return;
  }
  if (message?.type === 'home' && sender.frameId === 0 && sender.tab?.id === tabId && sender.documentId === documentId) {
    invalidate(); void chrome.tabs.update(tabId, { url: HOME }); reply({ ok: true }); return;
  }
  if (!validSender(sender, tabId, documentId, config.apps)) { reply({ type: 'error', error: 'inactive_document' }); return; }
  if (message.type === 'hello') { reply({ type: 'connection', connected: socket?.readyState === WebSocket.OPEN, locale: config.locale }); return; }
  if (message.type !== 'layout' || JSON.stringify(message).length > 12000 || requests.size >= 32) {
    reply({ type: 'error', error: 'invalid_message' }); return;
  }
  const request = crypto.randomUUID();
  requests.set(request, { document: documentId, reply });
  if (!send({ type: 'layout', document: documentId, operation: message.operation, layout: message.layout, request })) {
    requests.delete(request); reply({ type: 'error', error: 'deck_disconnected' }); return;
  }
  return true;
});

chrome.action.onClicked.addListener(async tab => {
  const { token } = await chrome.storage.local.get('token');
  if (!token) { await chrome.runtime.openOptionsPage(); return; }
  invalidate(); tabId = tab.id;
  await chrome.storage.session.set({ kioskTab: tabId });
  await connect(); await refreshContext();
});
chrome.tabs.onActivated.addListener(() => void refreshContext());
chrome.windows.onFocusChanged.addListener(() => void refreshContext());
chrome.tabs.onUpdated.addListener((id, change) => {
  if (id === tabId && (change.status || change.url)) void refreshContext();
  else if (tabId == null && change.status === 'complete') void selectHomeTab().then(refreshContext);
});
chrome.tabs.onRemoved.addListener(id => { if (id === tabId) { invalidate(); tabId = undefined; void chrome.storage.session.remove('kioskTab'); } });
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === 'reconnect') void connect(); });
chrome.runtime.onStartup.addListener(() => void connect());
void connect();
