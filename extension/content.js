(() => {
  if (globalThis.__foxoeBridge) return;
  globalThis.__foxoeBridge = true;
  const publish = message => window.postMessage({ ...message, source: 'foxoe:bridge' }, location.origin);
  window.addEventListener('message', event => {
    if (event.source !== window || event.origin !== location.origin || event.data?.source !== 'foxoe:app') return;
    if (!['hello', 'layout'].includes(event.data.type)) return;
    chrome.runtime.sendMessage(event.data).then(reply => publish({ ...reply, request: event.data.request }))
      .catch(() => publish({ type: 'connection', connected: false }));
  });
  chrome.runtime.onMessage.addListener(message => {
    publish(message);
    if (message.type === 'connection') home.textContent = chrome.i18n.getMessage('home');
  });
  // The toolbar survives app layout changes in an isolated shadow tree. Only
  // configured, explicitly permission-granted pages receive this script.
  const host = document.createElement('foxoe-home');
  const shadow = host.attachShadow({ mode: 'closed' });
  const style = document.createElement('style');
  style.textContent = ':host{position:fixed;bottom:16px;right:16px;z-index:2147483647}button{font:600 16px system-ui;color:#fff;background:#4f46e5;border:1px solid #818cf8;border-radius:6px;min-height:48px;padding:10px 20px;cursor:pointer;transition:transform 100ms,color 140ms}button:active{transform:scale(.98)}button:focus-visible{outline:3px solid #818cf8;outline-offset:3px}@media(prefers-reduced-motion:reduce){button{transition:none}}';
  const home = document.createElement('button');
  home.type = 'button';
  home.textContent = chrome.i18n.getMessage('home');
  home.addEventListener('click', () => void chrome.runtime.sendMessage({ type: 'home' }));
  shadow.append(style, home);
  if (location.href !== 'http://127.0.0.1:8765/') document.documentElement.append(host);
})();
