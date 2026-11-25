<script setup lang="ts">
import { computed } from 'vue';
import type { Condition, ComparisonFields, Source, DataEntry } from './types';
import { t } from './i18n';
import Icon from './Icon.vue';
import FieldPicker from './FieldPicker.vue';
const props = withDefaults(defineProps<{ modelValue: Condition; sources: Source[]; data?: Record<string, DataEntry>; depth?: number; remaining: number; removable?: boolean }>(), { depth: 0 });
const emit = defineEmits<{ 'update:modelValue': [value: Condition]; remove: [] }>();
const node = computed(() => props.modelValue);
const operators: ComparisonFields['operator'][] = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'exists', 'missing', 'truthy', 'falsy'];
const unary = ['exists', 'missing', 'truthy', 'falsy'];
function update(change: object) { emit('update:modelValue', { ...node.value, ...change } as Condition); }
function blank(): Condition { return { kind: 'comparison', source: 'system', path: '', operator: 'eq', value: '' }; }
function wrap() {
  if (node.value.kind !== 'comparison' || props.depth >= 4 || props.remaining < 2) return;
  emit('update:modelValue', { kind: 'and', children: [node.value, blank()] });
}
function add(group = false) {
  if (node.value.kind === 'comparison' || props.depth >= (group ? 3 : 4) || props.remaining < (group ? 2 : 1) || node.value.children.length >= 16) return;
  update({ children: [...node.value.children, group ? { kind: 'and', children: [blank()] } : blank()] });
}
function replace(index: number, value?: Condition) {
  if (node.value.kind === 'comparison') return;
  const children = [...node.value.children];
  if (value) children[index] = value;
  else { if (children.length === 1) return; children.splice(index, 1); }
  update({ children });
}
function ungroup() {
  if (node.value.kind === 'comparison' || node.value.children.length !== 1) return;
  const child = node.value.children[0]!;
  emit('update:modelValue', { ...child, negate: !!node.value.negate !== !!child.negate });
}
function setType(event: Event) {
  const type = (event.target as HTMLSelectElement).value;
  update({ value: type === 'number' ? 0 : type === 'boolean' ? true : type === 'null' ? null : '' });
}
</script>
<template>
  <div class="condition-editor form-stack">
    <div class="condition-toolbar">
      <label v-if="node.kind !== 'comparison'">{{ t('combineConditions') }}<select :value="node.kind" @change="update({ kind: ($event.target as HTMLSelectElement).value })"><option value="and">{{ t('conditionAnd') }}</option><option value="or">{{ t('conditionOr') }}</option></select></label>
      <label class="checkbox-row"><input type="checkbox" :checked="node.negate === true" @change="update({ negate: ($event.target as HTMLInputElement).checked })">{{ t('conditionNot') }}</label>
      <button v-if="node.kind === 'comparison'" type="button" class="secondary" :disabled="depth >= 4 || remaining < 2" @click="wrap">{{ t('groupCondition') }}</button>
      <button v-else-if="node.children.length === 1" type="button" class="secondary" @click="ungroup">{{ t('ungroupCondition') }}</button>
      <button v-if="removable" type="button" class="icon-button danger-text" :aria-label="t('removeCondition')" @click="emit('remove')"><Icon name="remove" /></button>
    </div>
    <Transition name="notice" mode="out-in">
      <div v-if="node.kind === 'comparison'" key="comparison" class="form-stack">
        <div class="form-row"><label>{{ t('source') }}<select :value="node.source" @change="update({ source: ($event.target as HTMLSelectElement).value })"><option value="system">{{ t('system') }}</option><option v-for="source in sources" :key="source.id" :value="source.id">{{ source.name }}</option></select></label><FieldPicker :model-value="node.path" :source="node.source" :value="data?.[node.source]?.value" @update:model-value="update({ path: $event })" /></div>
        <div class="form-row"><label>{{ t('comparison') }}<select :value="node.operator" @change="update({ operator: ($event.target as HTMLSelectElement).value })"><option v-for="operator in operators" :key="operator" :value="operator">{{ t(`op_${operator}`) }}</option></select></label><template v-if="!unary.includes(node.operator)"><label>{{ t('valueType') }}<select :value="node.value === null ? 'null' : typeof node.value" @change="setType"><option v-for="type in ['string','number','boolean','null']" :key="type" :value="type">{{ t(`type_${type}`) }}</option></select></label><label v-if="node.value !== null">{{ t('value') }}<input v-if="typeof node.value === 'number'" :value="node.value" type="number" step="any" required @input="update({ value: ($event.target as HTMLInputElement).valueAsNumber })"><select v-else-if="typeof node.value === 'boolean'" :value="String(node.value)" @change="update({ value: ($event.target as HTMLSelectElement).value === 'true' })"><option value="true">{{ t('yes') }}</option><option value="false">{{ t('no') }}</option></select><input v-else :value="node.value" maxlength="1000" @input="update({ value: ($event.target as HTMLInputElement).value })"></label></template></div>
      </div>
      <div v-else key="group" class="form-stack">
        <TransitionGroup name="surface" tag="div" class="condition-children form-stack">
          <ConditionEditor v-for="(child, index) in node.children" :key="index" :model-value="child" :sources="sources" :data="data" :depth="depth + 1" :remaining="remaining" :removable="node.children.length > 1" @update:model-value="replace(index, $event)" @remove="replace(index)" />
        </TransitionGroup>
        <div class="condition-toolbar"><button type="button" class="secondary" :disabled="depth >= 4 || remaining < 1 || node.children.length >= 16" @click="add()"><Icon name="plus" />{{ t('addCondition') }}</button><button type="button" class="secondary" :disabled="depth >= 3 || remaining < 2 || node.children.length >= 16" @click="add(true)">{{ t('addConditionGroup') }}</button></div>
      </div>
    </Transition>
  </div>
</template>
