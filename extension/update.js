/** Reload only verified on-disk files. Persist the attempt before reloading so
 * a browser holding an old directory cannot enter an endless reload loop. */
export function extensionUpdater(chrome, fetch, currentBuild, beforeReload = async () => {}) {
  let pending;
  return function check(build) {
    if (!/^[a-f0-9]{64}$/.test(build || '') || build === currentBuild) return Promise.resolve(false);
    if (pending) return pending;
    pending = (async () => {
      const stored = await chrome.storage.local.get('extensionReloadAttempt');
      if (stored.extensionReloadAttempt === `${currentBuild}:${build}`) return false;
      const response = await fetch(chrome.runtime.getURL('build.json'), { cache: 'no-store' });
      if (!response.ok || (await response.json()).build !== build) return false;
      await beforeReload(build);
      await chrome.storage.local.set({ extensionReloadAttempt: `${currentBuild}:${build}` });
      chrome.runtime.reload();
      return true;
    })().catch(() => false).finally(() => { pending = undefined; });
    return pending;
  };
}
