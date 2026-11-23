import test from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';
import { createSSRApp } from 'vue';
import { renderToString } from 'vue/server-renderer';

test('key previews request the device renderer with current labels, styles and artwork', async () => {
  const server = await createServer({ server: { middlewareMode: true, watch: null, ws: false }, optimizeDeps: { noDiscovery: true, entries: [] }, appType: 'custom' });
  try {
    const { default: DeckKey } = await server.ssrLoadModule('/frontend/DeckKey.vue');
    const button = { label: 'Label Station <&>', icon: 'printer', textSize: 32, disabled: true,
      textColor: '#abcdef', iconColor: '#fedcba', backgroundColor: '#123456', image: 'a'.repeat(64) };
    const render = props => renderToString(createSSRApp(DeckKey, props));
    const decode = html => JSON.parse(decodeURIComponent(html.match(/src="\/api\/deck\/preview\?key=([^"]+)"/)[1]));
    const html = await render({button});
    assert.deepEqual(decode(html), {...button, home:false});
    assert.ok(html.includes('alt="Label Station &lt;&amp;&gt;"'));
    assert.ok(!html.includes('<span'));
    assert.equal(decode(await render({button:{...button, label:'Changed', image:null}, home:true})).label, 'Changed');
    assert.equal(decode(await render({button, home:true})).home, true);
    const empty = decode(await render({button:null}));
    assert.equal(empty.icon, null);
    assert.equal(empty.label, '');
    assert.equal(empty.disabled, false);
  } finally { await server.close(); }
});
