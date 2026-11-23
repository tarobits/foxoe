import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import * as heroicons from '@heroicons/vue/24/outline';
import { createServer } from 'vite';
import { createSSRApp } from 'vue';
import { renderToString } from 'vue/server-renderer';

test('catalog covers the complete installed outline library and generated sprite', async () => {
  const catalog = JSON.parse(await readFile(new URL('../foxoe/icon_catalog.json', import.meta.url)));
  assert.deepEqual([...new Set(Object.values(catalog))].sort(), Object.keys(heroicons).sort());
  const sprite = await readFile(new URL('../public/heroicons.svg', import.meta.url), 'utf8');
  for (const name of Object.keys(catalog)) {
    assert.match(name, /^[a-z][a-z0-9-]*$/);
    assert.ok(sprite.includes(`<symbol id="${name}"`), name);
  }
  assert.equal(catalog.keypad, 'Squares2X2Icon');
  assert.equal(catalog.back, 'ArrowLeftIcon');
});

test('icon rendering handles null, full library, and hostile identifiers; picker searches safely', async () => {
  const server = await createServer({ server: { middlewareMode: true, watch: null }, optimizeDeps: { noDiscovery: true, entries: [] }, appType: 'custom' });
  try {
    const { default: Icon } = await server.ssrLoadModule('/frontend/Icon.vue');
    const render = name => renderToString(createSSRApp(Icon, { name }));
    assert.doesNotMatch(await render(null), /<(svg|img)/);
    assert.match(await render('user'), /heroicons.svg#user/);
    assert.match(await render('academic-cap'), /heroicons.svg#academic-cap/);
    const fox = await render('foxoe');
    assert.match(fox, /<img/);
    assert.ok(fox.includes('foxoe.svg') || decodeURIComponent(fox).includes('fox-orange'));
    for (const name of ['__proto__', 'constructor', '../../secret', 'bad" onload="evil']) {
      assert.match(await render(name), /heroicons.svg#window/);
      assert.doesNotMatch(await render(name), /onload|secret/);
    }
    const { matchingIcons, iconNames } = await server.ssrLoadModule('/frontend/icons.ts');
    assert.ok(matchingIcons(' USER ').includes('user-circle'));
    assert.ok(matchingIcons('arrow down').includes('arrow-down-tray'));
    assert.deepEqual(matchingIcons('<script>'), []);
    assert.equal(matchingIcons('').length, iconNames.length);
    const { default: Picker } = await server.ssrLoadModule('/frontend/IconPicker.vue');
    const markup = await renderToString(createSSRApp(Picker, { modelValue: null }));
    assert.match(markup, /No icon/);
    assert.match(markup, /Search icons/);
  } finally {
    await server.close();
  }
});
