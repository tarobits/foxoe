import { HOME, allowedApp, validSender } from './protocol.js';

let socket;
let heartbeat;
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
  if (tabId == null || !documentId) return;
  try { await chrome.tabs.sendMessage(tabId, message, { documentId }); } catch { /* A navigation can remove the document between checks. */ }
};

function invalidate() {
  contextSequence++;
  void post({ type: 'connection', connected: false });
  documentId = undefined;
  generation = -1;
  send({ type: 'inactive' });
  for (const entry of requests.values()) entry.reply({ type: 'error', error: 'inactive_document' });
  requests.clear();
}

async function refreshContext() {
  invalidate();
  const sequence = contextSequence;
  if (tabId == null || socket?.readyState !== WebSocket.OPEN) return;
  try {
    const tab = await chrome.tabs.get(tabId);
    const win = await chrome.windows.get(tab.windowId);
    if (!tab.active || !win.focused || sequence !== contextSequence || tab.status === 'loading') return;
    const frames = await chrome.scripting.executeScript({ target: { tabId, frameIds: [0] }, func: () => location.href });
    const frame = frames[0];
    if (!frame?.documentId || sequence !== contextSequence) return;
    documentId = frame.documentId;
    const request = crypto.randomUUID();
    requests.set(request, { document: documentId, reply: response => {
      if (response.type !== 'ack') return;
      void chrome.scripting.executeScript({ target: { tabId, documentIds: [documentId] }, files: ['content.js'] }).then(() => {
        if (sequence === contextSequence) void post({ type: 'connection', connected: Boolean(allowedApp(tab.url, config.apps)), locale: config.locale });
      }).catch(() => {});
    } });
    send({ type: 'context', url: frame.result, document: documentId, request });
  } catch { /* No host permission, closed tab, or browser page: controls stay inactive. */ }
}

async function connect() {
  if (socket && [WebSocket.CONNECTING, WebSocket.OPEN].includes(socket.readyState)) return;
  const stored = await chrome.storage.local.get(['token']);
  if (!stored.token) return;
  tabId = (await chrome.storage.session.get('kioskTab')).kioskTab;
  await selectHomeTab();
  const current = new WebSocket('ws://127.0.0.1:8765/bridge');
  socket = current;
  current.onopen = () => {
    current.send(JSON.stringify({ token: stored.token }));
    heartbeat = setInterval(() => send({ type: 'ping' }), 20000);
  };
  current.onclose = () => {
    if (socket !== current) return;
    clearInterval(heartbeat);
    invalidate();
    socket = undefined;
    void chrome.alarms.create('reconnect', { delayInMinutes: 0.5 });
  };
  current.onmessage = async event => {
    const message = JSON.parse(event.data);
    if (message.type === 'configuration') {
      config = message.config;
      await chrome.storage.local.set({ config });
      await refreshContext();
    } else if (message.type === 'ack' || message.type === 'error') {
      if (message.generation != null) generation = message.generation;
      const request = requests.get(message.request);
      requests.delete(message.request);
      if (request && request.document === documentId) request.reply(message);
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
    socket?.close();
    socket = undefined;
    clearInterval(heartbeat);
    invalidate();
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
