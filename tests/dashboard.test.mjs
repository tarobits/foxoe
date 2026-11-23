import test from 'node:test';
import assert from 'node:assert/strict';
import { readPath, fits, firstSpace, formatValue, listPage } from '../frontend/model.js';
import { readFile } from 'node:fs/promises';
import ts from 'typescript';

test('JSON data selection preserves zero and rejects executable and prototype paths', () => {
  const value = { queue: { jobs: [{ name: 'Label', count: 0 }] } };
  assert.equal(readPath(value, '$.queue.jobs[0].count'), 0);
  assert.equal(readPath(value, 'queue.jobs[0].name'), 'Label');
  assert.equal(readPath(value, 'queue.jobs[9].name'), undefined);
  for (const path of ['__proto__', 'constructor.name', 'queue.jobs.map(x=>x)', 'queue.jobs[0];alert(1)', 'queue..jobs']) assert.equal(readPath(value, path), undefined);
});
test('moves and resizes reject overlaps, fractional coordinates and out-of-bounds placement', () => {
  const widgets = [{ id: 'a', x: 0, y: 0, w: 4, h: 2 }, { id: 'b', x: 4, y: 0, w: 4, h: 2 }];
  assert.ok(fits({ ...widgets[0], y: 2 }, widgets));
  assert.ok(!fits({ ...widgets[0], x: 1 }, widgets));
  assert.ok(!fits({ ...widgets[0], w: 5 }, widgets));
  assert.ok(!fits({ ...widgets[0], y: -1 }, widgets));
  assert.ok(!fits({ ...widgets[0], x: 8.5 }, widgets));
  assert.ok(!fits({ ...widgets[0], y: 47 }, widgets));
  assert.ok(!fits({ ...widgets[0], h: 25 }, [widgets[0]]));
  assert.ok(fits({ ...widgets[0], h: 24 }, [widgets[0]]));
  assert.ok(fits({ ...widgets[0], x: 20, y: 46 }, widgets));
  assert.deepEqual(widgets[0], { id: 'a', x: 0, y: 0, w: 4, h: 2 });
  const next = firstSpace({ id: 'c', x: 0, y: 0, w: 4, h: 2 }, widgets);
  assert.equal(next.x, 8);
  assert.equal(firstSpace({ id: 'c', w: 4, h: 2 }, [{ id: 'full', x: 0, y: 0, w: 24, h: 48 }]), null);
});
test('queue truncation is explicit at the display boundary', () => {
  assert.deepEqual(listPage(null), { rows: [], truncated: false });
  assert.equal(listPage(Array(100).fill('Job')).truncated, false);
  const page = listPage(Array(101).fill('Job'));
  assert.equal(page.rows.length, 100);
  assert.equal(page.truncated, true);
});
test('data formatting distinguishes missing values from zero', () => {
  assert.equal(formatValue(0, 'en'), '0');
  assert.equal(formatValue(1.5, 'de'), '1,5');
  assert.equal(formatValue({ value: 3 }, 'en'), null);
  assert.equal(formatValue(null, 'en'), null);
  assert.equal(formatValue(NaN, 'en'), null);
});
test('both dashboard locales cover literal UI translation keys', async () => {
  const raw = await readFile(new URL('../frontend/i18n.ts', import.meta.url), 'utf8');
  const module = ts.transpile(raw.replace("import { ref } from 'vue';", 'const ref = value => ({value});'), { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 });
  const { messages } = await import(`data:text/javascript;base64,${Buffer.from(module).toString('base64')}`);
  assert.deepEqual(Object.keys(messages.en).sort(), Object.keys(messages.de).sort());
  for (const file of ['App.vue', 'WidgetContent.vue', 'WidgetValue.vue', 'WidgetEditor.vue', 'Demo.vue', 'IconPicker.vue', 'Access.vue', 'DeckKey.vue', 'SourcePreview.vue']) {
    const source = await readFile(new URL(`../frontend/${file}`, import.meta.url), 'utf8');
    for (const match of source.matchAll(/\bt\('([^']+)'\)/g)) assert.ok(messages.en[match[1]], `Missing ${match[1]}`);
  }
});
