// Rasterize trusted vector assets at build time. The Pi runtime only needs Pillow.
import { mkdir, readFile, writeFile, readdir } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createVNode } from 'vue';
import { renderToString } from 'vue/server-renderer';
import { Resvg, initWasm } from '@resvg/resvg-wasm';
import * as icons from '@heroicons/vue/24/outline';

const require = createRequire(import.meta.url);
const root = new URL('../', import.meta.url);
await initWasm(await readFile(require.resolve('@resvg/resvg-wasm/index_bg.wasm')));
const directory = async path => mkdir(new URL(path, root), { recursive: true });
async function png(svg, size, destination) {
  const renderer = new Resvg(svg, { fitTo: { mode: 'width', value: size }, font: { loadSystemFonts: false } });
  const image = renderer.render();
  try { await writeFile(new URL(destination, root), image.asPng()); }
  finally { image.free(); renderer.free(); }
}

await directory('extension/icons/');
await directory('foxoe/assets/icons/');
const fox = await readFile(new URL('public/foxoe.svg', root), 'utf8');
for (const size of [16, 32, 48, 128]) await png(fox, size, `extension/icons/foxoe-${size}.png`);
await png(fox, 96, 'foxoe/assets/icons/foxoe.png');
const catalog = JSON.parse(await readFile(new URL('foxoe/icon_catalog.json', root), 'utf8'));
const symbols = [];
for (const [name, componentName] of Object.entries(catalog)) {
  const component = icons[componentName];
  if (!component || !/^[a-z][a-z0-9-]*$/.test(name)) throw new Error(`Invalid icon catalog entry: ${name}`);
  const svg = await renderToString(createVNode(component));
  symbols.push(`<symbol id="${name}" viewBox="0 0 24 24">${svg.replace(/^<svg[^>]*>/, '').replace(/<\/svg>$/, '')}</symbol>`);
  await png(svg.replaceAll('currentColor', '#F8FAFC'), 96, `foxoe/assets/icons/${name}.png`);
}
await writeFile(new URL('public/heroicons.svg', root), `<svg xmlns="http://www.w3.org/2000/svg">${symbols.join('')}</svg>`);
// Fingerprint all packaged extension files, not only the display version.
const hash = createHash('sha256');
async function fingerprint(path = '') {
  for (const entry of (await readdir(new URL(`extension/${path}`, root), { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
    const name = path + entry.name;
    if (['build.js', 'build.json', 'build-content.js'].includes(name)) continue;
    if (entry.isDirectory()) await fingerprint(name + '/');
    else if (entry.isFile()) { hash.update(name + '\0'); hash.update(await readFile(new URL(`extension/${name}`, root))); }
  }
}
await fingerprint();
const build = hash.digest('hex');
await writeFile(new URL('extension/build.js', root), `export const BUILD = ${JSON.stringify(build)};\n`);
await writeFile(new URL('extension/build.json', root), JSON.stringify({ build }));
await writeFile(new URL('extension/build-content.js', root), `globalThis.__foxoeBuild = ${JSON.stringify(build)};\n`);
console.log(`Built FoxOE and Stream Deck icons in ${fileURLToPath(root)}`);
