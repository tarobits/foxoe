// Generate a browser regression fixture from the real Vue renderer and CSS.
// Run: node tests/widget-sizing.mjs /tmp/foxoe-widget-sizing.html
import { createServer } from 'vite';
import { createSSRApp } from 'vue';
import { renderToString } from 'vue/server-renderer';
import { readFile, writeFile } from 'node:fs/promises';
if (!process.argv[2]) throw new Error('Pass the output HTML path');
const server = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, optimizeDeps: { noDiscovery: true, entries: [] }, appType: 'custom' });
try {
  const { default: WidgetContent } = await server.ssrLoadModule('/frontend/WidgetContent.vue');
  const widget = { kind:'layout', title:'', columns:[1], rows:[1], gap:8, rules:[], items:[
    {id:'icon', kind:'icon', icon:'foxoe', title:'', fontSize:null, rules:[], row:0, column:0, rowSpan:1, columnSpan:1},
  ] };
  const markup = await renderToString(createSSRApp(WidgetContent, {widget, data:{}, now:new Date()}));
  const css = await readFile(new URL('../frontend/style.css', import.meta.url), 'utf8');
  const fox = await readFile(new URL('../public/foxoe.svg', import.meta.url));
  const verify = async () => {
    const output = document.querySelector('output');
    const grid = document.querySelector('.widget-layout');
    const cell = document.querySelector('.widget-cell');
    const icon = cell.querySelector('.icon');
    const wait = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const check = label => {
      const a = icon.getBoundingClientRect(), b = cell.getBoundingClientRect();
      if (a.width <= 0 || a.height <= 0 || a.left < b.left - 1 || a.top < b.top - 1 || a.right > b.right + 1 || a.bottom > b.bottom + 1 || cell.scrollHeight > cell.clientHeight + 1) throw new Error(label + ': icon overflows cell');
    };
    try {
      await wait(); check('One row');
      grid.style.gridTemplateRows = 'repeat(6, minmax(0, 1fr))';
      await wait(); check('Six rows');
      grid.style.gridTemplateColumns = '20px';
      await wait(); check('Narrow cell');
      cell.style.setProperty('--widget-font-size', '96px');
      await wait(); check('Large explicit size');
      cell.style.removeProperty('--widget-font-size');
      grid.style.gridTemplateColumns = '1fr';
      grid.style.gridTemplateRows = '1fr';
      await wait(); check('Expanded again');
      if (Math.abs(icon.getBoundingClientRect().height - 40) > 1) throw new Error('Automatic size did not recover');
      grid.style.gridTemplateRows = 'repeat(6, minmax(0, 1fr))';
      output.textContent = 'PASS: rows, narrow cells, explicit sizes, and recovery';
    } catch (error) { output.textContent = 'FAIL: ' + error.message; }
  };
  await writeFile(process.argv[2], `<!doctype html><html><meta charset="utf-8"><title>Widget sizing regression</title><style>${css}</style><body style="padding:32px"><h1>Widget sizing regression</h1><output role="status">Checking…</output><div style="width:240px;height:180px;margin-top:24px;background:#1f2937">${markup.replaceAll('/foxoe.svg', 'data:image/svg+xml;base64,' + fox.toString('base64'))}</div><script>(${verify.toString()})()</script></body></html>`);
} finally { await server.close(); }
