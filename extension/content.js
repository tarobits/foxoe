(() => {
  if (globalThis.__foxoeBridge && globalThis.__foxoeBridge.build === globalThis.__foxoeBuild) return;
  globalThis.__foxoeBridge?.dispose?.();
  const publish = message => window.postMessage({ ...message, source: 'foxoe:bridge' }, location.origin);
  const onPageMessage = event => {
    if (event.source !== window || event.origin !== location.origin || event.data?.source !== 'foxoe:app') return;
    if (!['hello', 'layout'].includes(event.data.type)) return;
    chrome.runtime.sendMessage(event.data).then(reply => publish({ ...reply, request: event.data.request }))
      .catch(() => publish({ type: 'connection', connected: false }));
  };
  window.addEventListener('message', onPageMessage);
  const onBridgeMessage = message => {
    publish(message);
    if (message.type === 'connection') home.textContent = chrome.i18n.getMessage('home');
  };
  chrome.runtime.onMessage.addListener(onBridgeMessage);
  // The toolbar survives app layout changes in an isolated shadow tree. Only
  // configured, explicitly permission-granted pages receive this script.
  const host = document.createElement('foxoe-home');
  const shadow = host.attachShadow({ mode: 'closed' });
  const style = document.createElement('style');
  style.textContent = ':host{all:initial;position:fixed;bottom:16px;right:0;z-index:2147483647;display:block;max-width:100vw}.toolbar{display:flex;align-items:stretch;background:#4f46e5;border:1px solid #818cf8;border-right:0;border-radius:8px 0 0 8px;transform:translateX(calc(100% - 24px));transition:transform 180ms cubic-bezier(.2,.8,.2,1)}.toolbar.open{transform:translateX(0)}button{box-sizing:border-box;font:600 16px system-ui;color:#fff;background:transparent;border:0;min-height:56px;padding:10px 16px;cursor:pointer;transition:background 140ms}button:active{background:#4338ca}button:focus-visible{outline:2px solid #fff;outline-offset:-4px}.toggle{width:24px;flex:0 0 24px;padding:4px}.toggle svg{display:block;width:16px;height:20px;transition:transform 180ms cubic-bezier(.2,.8,.2,1)}.open .toggle svg{transform:rotate(180deg)}.home{min-width:88px}.toolbar:not(.open) .home{visibility:hidden;pointer-events:none}@media(prefers-reduced-motion:reduce){.toolbar,button,.toggle svg{transition:none}}';
  const toolbar = document.createElement('div');
  // Clip the translated panel without intercepting taps on the page beneath it.
  style.textContent += ':host{overflow:clip;pointer-events:none}.toolbar{pointer-events:auto}.home{transition:visibility 0s 180ms,background 140ms}.open .home{transition-delay:0s}@media(prefers-reduced-motion:reduce){.home{transition:none}}';
  toolbar.className = 'toolbar';
  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'toggle';
  const arrow = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  arrow.setAttribute('viewBox', '0 0 24 24');
  arrow.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', 'M15.75 19.5 8.25 12l7.5-7.5');
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', 'currentColor');
  path.setAttribute('stroke-width', '2');
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  arrow.append(path);
  toggle.append(arrow);
  const home = document.createElement('button');
  home.type = 'button';
  home.className = 'home';
  home.id = 'foxoe-home-action';
  home.textContent = chrome.i18n.getMessage('home');
  toggle.setAttribute('aria-controls', home.id);
  let expanded = false;
  const setExpanded = value => {
    expanded = value;
    toolbar.className = value ? 'toolbar open' : 'toolbar';
    toggle.setAttribute('aria-expanded', String(value));
    toggle.setAttribute('aria-label', chrome.i18n.getMessage(value ? 'hideHome' : 'showHome'));
    home.tabIndex = value ? 0 : -1;
    home.setAttribute('aria-hidden', String(!value));
  };
  toggle.addEventListener('click', () => setExpanded(!expanded));
  home.addEventListener('click', () => {
    setExpanded(false);
    void chrome.runtime.sendMessage({ type: 'home' }).catch(() => {});
  });
  const onPointerDown = event => { if (expanded && !event.composedPath().includes(host)) setExpanded(false); };
  const onKeyDown = event => {
    if (expanded && event.key === 'Escape') { setExpanded(false); toggle.focus(); }
  };
  document.addEventListener('pointerdown', onPointerDown, true);
  document.addEventListener('keydown', onKeyDown);
  setExpanded(false);
  toolbar.append(toggle, home);
  shadow.append(style, toolbar);
  if (location.href !== 'http://127.0.0.1:8765/') document.documentElement.append(host);
  globalThis.__foxoeBridge = { build: globalThis.__foxoeBuild, dispose() {
    window.removeEventListener('message', onPageMessage);
    try { chrome.runtime.onMessage.removeListener(onBridgeMessage); } catch { /* Retired extension context. */ }
    document.removeEventListener('pointerdown', onPointerDown, true);
    document.removeEventListener('keydown', onKeyDown);
    host.remove();
    publish({ type: 'connection', connected: false });
  } };
})();
