<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { Widget, WidgetItem, Source, DataEntry } from './types';
import { t } from './i18n';
import Icon from './Icon.vue';
import IconPicker from './IconPicker.vue';
import WidgetPreview from './WidgetPreview.vue';
import FieldPicker from './FieldPicker.vue';
import { evaluateFormula, parseFormula } from './formula.js';
import ConditionEditor from './ConditionEditor.vue';
import RuleActionsEditor from './RuleActionsEditor.vue';
import { ruleCondition, conditionCount } from './conditions';
import { itemFits, firstItemSpace, appearance, readPath } from './model.js';
const props = defineProps<{ widget: Widget; sources: Source[]; data: Record<string, DataEntry>; now: Date }>();
const selected = ref(''), tab = ref<'content' | 'appearance' | 'rules'>('content');
const item = computed(() => props.widget.items.find(item => item.id === selected.value));
const target = computed(() => item.value || props.widget);
const requiresTextContent = computed(() => target.value.rules.some(rule => rule.actions?.some(action => action.target === 'text')));
const requiresIconContent = computed(() => target.value.rules.some(rule => rule.actions?.some(action => action.target === 'icon')));
const formulaError = computed(() => target.value.formula?.trim() ? evaluateFormula(target.value.formula.trim(), readPath(props.data[target.value.source]?.value, target.value.path), props.data[target.value.source]?.value).error : null);
function changeFormula(event: Event) {
  const input = event.target as HTMLInputElement;
  target.value.formula = input.value;
  try { if (input.value.trim()) parseFormula(input.value.trim()); input.setCustomValidity(''); }
  catch { input.setCustomValidity(t('invalidFormula')); }
}
function addItem() {
  if (props.widget.items.length >= 24) return;
  const item: WidgetItem = { id: `item-${crypto.randomUUID().slice(0, 8)}`, kind: 'text', title: '', text: '', source: 'system', path: '', itemPath: '', unit: '', icon: 'window', row: 0, column: 0, rowSpan: 1, columnSpan: 1, rules: [], align: 'left' };
  const candidate = firstItemSpace(item, props.widget);
  if (candidate) { props.widget.items.push(candidate); selected.value = candidate.id; tab.value = 'content'; }
}
const hasSpace = computed(() => props.widget.items.length < 24 && firstItemSpace({ id: '', rowSpan: 1, columnSpan: 1 }, props.widget) !== null);
function removeItem() {
  props.widget.items = props.widget.items.filter(item => item.id !== selected.value); selected.value = '';
}
function canRemoveTrack(axis: 'rows' | 'columns') {
  const count = props.widget[axis].length;
  return count > 1 && props.widget.items.every(item => axis === 'rows' ? item.row + item.rowSpan < count : item.column + item.columnSpan < count);
}
function addRule() {
  target.value.rules.push({ source: target.value.source, path: target.value.path, operator: 'eq', value: '', target: 'textColor', color: '#4ade80', visible: true });
}
watch(() => props.widget.kind, () => { selected.value = ''; });
</script>
<template>
  <div class="widget-editor form-stack">
    <div v-if="widget.kind === 'layout'" class="form-row">
      <label class="grow">{{ t('editTarget') }}<select v-model="selected"><option value="">{{ t('wholeWidget') }}</option><option v-for="(entry, index) in widget.items" :key="entry.id" :value="entry.id">{{ entry.title || `${t('item')} ${index + 1}` }}</option></select></label>
      <button type="button" class="secondary" :disabled="!hasSpace" @click="addItem"><Icon name="plus" />{{ t('addItem') }}</button>
      <button v-if="item" type="button" class="icon-button danger-text" :aria-label="t('removeItem')" @click="removeItem"><Icon name="remove" /></button>
    </div>
    <nav class="editor-tabs" :aria-label="t('widgetOptions')"><button v-for="section in (['content', 'appearance', 'rules'] as const)" :key="section" type="button" :class="{ selected: tab === section }" :aria-pressed="tab === section" @click="tab = section">{{ t(section) }}</button></nav>
    <Transition name="notice" mode="out-in">
      <div v-if="tab === 'content'" key="content" class="form-stack">
        <div class="form-row"><label class="grow">{{ t('title') }}<input v-model="target.title" maxlength="60"></label><label>{{ t('kind') }}<select v-model="target.kind"><option v-for="kind in ['clock','value','list','text','icon', ...(!item ? ['layout'] : [])]" :key="kind" :value="kind" :disabled="(requiresTextContent && !['text', 'value'].includes(kind)) || (requiresIconContent && kind !== 'icon')">{{ t(kind) }}</option></select></label></div>
        <label class="checkbox-row title-toggle"><input type="checkbox" :checked="target.showTitle !== false" @change="target.showTitle = ($event.target as HTMLInputElement).checked">{{ t('showTitle') }}</label>
        <template v-if="target.kind === 'layout'">
          <label class="checkbox-row"><input v-model="widget.allowOverlap" type="checkbox">{{ t('allowItemOverlap') }}</label>
          <div v-for="axis in (['columns', 'rows'] as const)" :key="axis" class="track-editor">
            <div class="section-header"><h3>{{ t(axis) }}</h3><div class="header-actions"><button type="button" class="icon-button" :aria-label="t(axis === 'rows' ? 'addRow' : 'addColumn')" :disabled="widget[axis].length >= 6" @click="widget[axis].push(1)"><Icon name="plus" /></button><button type="button" class="icon-button" :aria-label="t(axis === 'rows' ? 'removeRow' : 'removeColumn')" :disabled="!canRemoveTrack(axis)" @click="widget[axis].pop()"><Icon name="remove" /></button></div></div>
            <div class="track-weights"><label v-for="(_, index) in widget[axis]" :key="index">{{ t(axis === 'rows' ? 'y' : 'x') }} {{ index + 1 }}<input v-model.number="widget[axis][index]" type="number" min="1" max="12" required></label></div>
          </div>
          <p class="muted help">{{ t('trackWeights') }}</p>
          <p v-if="!widget.items.length" class="muted">{{ t('noWidgetItems') }}</p>
        </template>
        <label v-if="target.kind === 'text'">{{ t('content') }}<textarea v-model="target.text" rows="3" maxlength="1000"></textarea></label>
        <IconPicker v-if="target.kind === 'icon'" :model-value="target.icon ?? null" @update:model-value="target.icon = $event" />
        <template v-if="['value', 'list'].includes(target.kind)">
          <label>{{ t('source') }}<select v-model="target.source"><option value="system">{{ t('system') }}</option><option v-for="source in sources" :key="source.id" :value="source.id">{{ source.name }}</option></select></label>
          <FieldPicker v-model="target.path" :source="target.source" :value="data[target.source]?.value" />
          <div class="form-row"><label v-if="target.kind === 'value'">{{ t('unit') }}<input v-model="target.unit" maxlength="12"></label><label v-else>{{ t('itemPath') }}<input v-model="target.itemPath" maxlength="200" spellcheck="false"></label><label>{{ t('decimalPlaces') }}<input :value="target.decimals ?? ''" type="number" min="0" max="10" :placeholder="t('automatic')" @input="target.decimals = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)"></label></div>
          <template v-if="target.kind === 'value'"><label>{{ t('formula') }}<input :value="target.formula || ''" maxlength="512" spellcheck="false" :placeholder="t('formulaPlaceholder')" :aria-invalid="formulaError === 'invalidFormula'" @input="changeFormula"></label><p class="muted help">{{ t('formulaHelp') }}</p><Transition name="notice"><p v-if="formulaError" class="data-warning" role="status">{{ t(formulaError) }}</p></Transition></template>
        </template>
        <fieldset v-if="item"><legend>{{ t('itemPlacement') }}</legend><div class="position-fields">
          <label>{{ t('x') }}<input :value="item.column + 1" type="number" min="1" :max="widget.columns.length" @input="item.column = Number(($event.target as HTMLInputElement).value) - 1"></label>
          <label>{{ t('y') }}<input :value="item.row + 1" type="number" min="1" :max="widget.rows.length" @input="item.row = Number(($event.target as HTMLInputElement).value) - 1"></label>
          <label>{{ t('columnSpan') }}<input v-model.number="item.columnSpan" type="number" min="1" :max="widget.columns.length"></label>
          <label>{{ t('rowSpan') }}<input v-model.number="item.rowSpan" type="number" min="1" :max="widget.rows.length"></label>
        </div><p v-if="!itemFits(item, widget)" class="data-warning" role="alert">{{ t(widget.allowOverlap ? 'itemBounds' : 'itemOverlap') }}</p></fieldset>
      </div>
      <div v-else-if="tab === 'appearance'" key="appearance" class="form-stack">
        <div class="widget-color-fields"><label v-for="field in (['textColor', 'backgroundColor', 'iconColor'] as const)" :key="field">{{ t(field) }}<input type="color" :value="target[field] || (field === 'backgroundColor' ? '#1f2937' : '#ffffff')" @input="target[field] = ($event.target as HTMLInputElement).value"></label><button type="button" class="secondary" @click="target.textColor = target.backgroundColor = target.iconColor = null">{{ t('resetColors') }}</button></div>
        <div class="form-row"><label>{{ t('fontSize') }}<input :value="target.fontSize ?? ''" type="number" min="8" max="96" :placeholder="t('automatic')" @input="target.fontSize = ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value)"></label><label>{{ t('alignment') }}<select v-model="target.align"><option v-for="align in ['left','center','right']" :key="align" :value="align">{{ t(align) }}</option></select></label></div>
        <div class="form-row"><label>{{ t('fontWeight') }}<select :value="target.fontWeight ?? ''" @change="target.fontWeight = ($event.target as HTMLSelectElement).value === '' ? null : Number(($event.target as HTMLSelectElement).value)"><option value="">{{ t('automatic') }}</option><option v-for="weight in [300,400,500,600,700,800,900]" :key="weight" :value="weight">{{ t(`weight${weight}`) }}</option></select></label><label>{{ t('verticalAlignment') }}<select :value="target.verticalAlign ?? ''" @change="target.verticalAlign = (($event.target as HTMLSelectElement).value || null) as Widget['verticalAlign']"><option value="">{{ t('automatic') }}</option><option v-for="align in ['top','middle','bottom']" :key="align" :value="align">{{ t(align) }}</option></select></label><label class="checkbox-row"><input v-model="target.italic" type="checkbox">{{ t('italic') }}</label></div>
        <div v-if="!item" class="form-row"><label>{{ t('padding') }}<input v-model.number="widget.padding" type="number" min="0" max="48" required></label><label v-if="widget.kind === 'layout'">{{ t('gap') }}<input v-model.number="widget.gap" type="number" min="0" max="32" required></label></div>
      </div>
      <div v-else key="rules" class="form-stack">
        <div class="section-header"><h3>{{ t('rules') }}</h3><button type="button" class="secondary" :disabled="target.rules.length >= 16" @click="addRule"><Icon name="plus" />{{ t('addRule') }}</button></div>
        <p class="muted help">{{ t('ruleOrder') }}</p>
        <div v-for="(rule, index) in target.rules" :key="index" class="rule-editor form-stack">
          <div class="section-header"><h3>{{ t('condition') }}</h3><button type="button" class="icon-button danger-text" :aria-label="t('removeRule')" @click="target.rules.splice(index, 1)"><Icon name="remove" /></button></div>
          <ConditionEditor :model-value="ruleCondition(rule)" :sources="sources" :data="data" :remaining="32 - conditionCount(ruleCondition(rule))" @update:model-value="rule.condition = $event" />
          <RuleActionsEditor :rule="rule" :kind="target.kind" />
          <div class="header-actions"><button type="button" class="icon-button" :disabled="index === 0" :aria-label="t('moveRuleUp')" @click="target.rules.splice(index - 1, 0, target.rules.splice(index, 1)[0]!)"><Icon name="arrow-up" /></button><button type="button" class="icon-button" :disabled="index === target.rules.length - 1" :aria-label="t('moveRuleDown')" @click="target.rules.splice(index + 1, 0, target.rules.splice(index, 1)[0]!)"><Icon name="arrow-down" /></button></div>
        </div>
      </div>
    </Transition>
    <section class="widget-editor-preview" :aria-label="t('widgetPreview')">
      <h3>{{ t('widgetPreview') }}</h3>
      <p v-if="!appearance(widget, data).visible" class="muted">{{ t('hiddenByRule') }}</p>
      <WidgetPreview v-else :widget="widget" :data="data" :now="now" />
    </section>
  </div>
</template>
