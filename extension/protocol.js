export const HOME = 'http://127.0.0.1:8765/';

export function allowedApp(url, apps) {
  try {
    const current = new URL(url);
    if (current.username || current.password) return null;
    return apps.find(app => {
      const target = new URL(app.url, HOME);
      const path = target.pathname.replace(/\/$/, '');
      return current.origin === target.origin && (!path || current.pathname === path || current.pathname.startsWith(`${path}/`));
    }) || null;
  } catch { return null; }
}

export function validSender(sender, tab, document, apps) {
  return sender.frameId === 0 && sender.tab?.id === tab && sender.documentId === document && Boolean(allowedApp(sender.url, apps));
}
