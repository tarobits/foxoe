/** Browser-side API. Credentials stay in the extension, never in this page. */
export function createDeck(target = window) {
  const pending = new Map();
  const handlers = new Set();
  const connections = new Set();
  let connected = false;
  let disposed = false;

  function receive(event) {
    if (event.source !== target || event.origin !== target.location.origin || event.data?.source !== 'foxoe:bridge') return;
    const message = event.data;
    if (message.type === 'connection') {
      connected = Boolean(message.connected);
      for (const fn of connections) fn(connected);
    } else if (message.type === 'action') {
      for (const fn of handlers) fn({ id: message.id, layout: message.layout });
    } else if (message.request && pending.has(message.request)) {
      const { resolve, reject, timer } = pending.get(message.request);
      pending.delete(message.request);
      clearTimeout(timer);
      if (message.type === 'error') reject(new Error(message.error || 'request_failed'));
      else resolve();
    }
  }
  target.addEventListener('message', receive);

  function request(operation, layout) {
    if (disposed) return Promise.reject(new Error('deck_disposed'));
    if (!connected) return Promise.reject(new Error('deck_disconnected'));
    if (pending.size >= 32) return Promise.reject(new Error('too_many_requests'));
    const id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error('deck_timeout'));
      }, 5000);
      pending.set(id, { resolve, reject, timer });
      target.postMessage({ source: 'foxoe:app', type: 'layout', request: id, operation, layout }, target.location.origin);
    });
  }

  target.postMessage({ source: 'foxoe:app', type: 'hello' }, target.location.origin);
  return {
    get connected() { return connected; },
    show: (layout) => request('show', layout),
    push: (layout) => request('push', layout),
    showScreen: (id) => request('screen', id),
    pushScreen: (id) => request('pushScreen', id),
    updateButton: (id, changes) => request('update', { id, changes }),
    pop: () => request('pop'),
    onAction(fn) { handlers.add(fn); return () => handlers.delete(fn); },
    onConnection(fn) { connections.add(fn); fn(connected); return () => connections.delete(fn); },
    dispose() {
      disposed = true;
      connected = false;
      target.removeEventListener('message', receive);
      for (const entry of pending.values()) { clearTimeout(entry.timer); entry.reject(new Error('deck_disposed')); }
      pending.clear(); handlers.clear(); connections.clear();
    },
  };
}

export function keypadLayout(labels, id = 'keypad') {
  return { id, buttons: [
    ...['7', '8', '9'].map(d => ({ id: `digit.${d}`, label: d, icon: 'keypad' })),
    { id: 'backspace', label: labels.backspace, icon: 'backspace' },
    { id: 'cancel', label: labels.cancel, icon: 'close' },
    ...['4', '5', '6'].map(d => ({ id: `digit.${d}`, label: d, icon: 'keypad' })),
    { id: 'digit.0', label: '0', icon: 'keypad' },
    { id: 'confirm', label: labels.confirm, icon: 'check' },
    ...['1', '2', '3'].map(d => ({ id: `digit.${d}`, label: d, icon: 'keypad' })),
    null,
  ] };
}
