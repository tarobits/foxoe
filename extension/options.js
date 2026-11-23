const t = key => chrome.i18n.getMessage(key);
document.documentElement.lang = chrome.i18n.getUILanguage();
document.querySelectorAll('[data-i18n]').forEach(node => { node.textContent = t(node.dataset.i18n); });
const status = document.querySelector('#status');
const token = document.querySelector('#token');

async function refresh() {
  const stored = await chrome.storage.local.get(['token', 'config']);
  token.value = stored.token || '';
  const apps = stored.config?.apps || [];
  const list = document.querySelector('#apps');
  list.replaceChildren();
  for (const app of apps) {
    const item = document.createElement('li'); item.textContent = app.name; list.append(item);
  }
}
document.querySelector('#connection').addEventListener('submit', async event => {
  event.preventDefault();
  await chrome.storage.local.set({ token: token.value.trim() });
  await chrome.runtime.sendMessage({ type: 'reconnect' });
  status.textContent = t('connectionSaved');
});
chrome.storage.onChanged.addListener(changes => { if (changes.config) void refresh(); });
void refresh();
