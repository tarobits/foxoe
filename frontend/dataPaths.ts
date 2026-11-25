export const systemPaths = ['load1','memoryPercent','memoryUsedMiB','memoryTotalMiB','temperatureC'];

/** Bounded discovery from the last JSON response, not arbitrary property access. */
export function dataPaths(value: unknown): string[] {
  const paths: string[] = [];
  function walk(node: unknown, path: string, depth: number) {
    if (paths.length >= 200 || depth > 8) return;
    if (path) paths.push(path);
    if (!node || typeof node !== 'object') return;
    for (const key of Object.keys(node).slice(0, 200)) {
      if (paths.length >= 200) break;
      if (!/^[a-zA-Z0-9_-]+$/.test(key) || ['__proto__','prototype','constructor'].includes(key)) continue;
      walk((node as Record<string, unknown>)[key], Array.isArray(node) ? `${path}[${key}]` : path ? `${path}.${key}` : key, depth + 1);
    }
  }
  walk(value, '', 0); return paths;
}
