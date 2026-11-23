// Rasterize trusted vector assets at build time. The Pi runtime only needs Pillow.
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { createVNode } from 'vue';
import { renderToString } from 'vue/server-renderer';
import { Resvg, initWasm } from '@resvg/resvg-wasm';
import { HomeIcon, PrinterIcon, WindowIcon, Squares2X2Icon, PlayIcon, BackspaceIcon, CheckIcon, XMarkIcon, ArrowLeftIcon, ArrowPathIcon } from '@heroicons/vue/24/outline';

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
const actions = { home: HomeIcon, printer: PrinterIcon, window: WindowIcon, keypad: Squares2X2Icon,
  play: PlayIcon, backspace: BackspaceIcon, check: CheckIcon, close: XMarkIcon, back: ArrowLeftIcon, reload: ArrowPathIcon };
for (const [name, component] of Object.entries(actions)) {
  const svg = (await renderToString(createVNode(component))).replaceAll('currentColor', '#F8FAFC');
  await png(svg, 96, `foxoe/assets/icons/${name}.png`);
}
console.log(`Built FoxOE and Stream Deck icons in ${fileURLToPath(root)}`);
