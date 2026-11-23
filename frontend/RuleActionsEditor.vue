<script setup lang="ts">
import { computed } from 'vue';
import type { WidgetRule, RuleAction } from './types';
import { ruleActions } from './conditions';
import { t } from './i18n';
import Icon from './Icon.vue';
const props = defineProps<{ rule: WidgetRule; kind: string }>();
const actions = computed(() => ruleActions(props.rule));
const targets = computed(() => ['textColor', 'backgroundColor', 'iconColor', 'visible', 'title', ...(['text', 'value'].includes(props.kind) ? ['text'] : [])]);
function replace(index: number, action: RuleAction) { props.rule.actions = actions.value.map((old, n) => n === index ? action : old); }
function changeTarget(index: number, event: Event) {
  const target = (event.target as HTMLSelectElement).value as RuleAction['target'];
  replace(index, target === 'text' || target === 'title' ? { target, text: '' } : target === 'visible' ? { target, visible: true } : { target, color: '#4ade80' });
}
function add() { if (actions.value.length < 16) props.rule.actions = [...actions.value, { target: 'textColor', color: '#4ade80' }]; }
function remove(index: number) { if (actions.value.length > 1) props.rule.actions = actions.value.filter((_, n) => n !== index); }
</script>
<template>
  <div class="rule-actions form-stack">
    <div class="section-header"><h3>{{ t('ruleActions') }}</h3><button type="button" class="secondary" :disabled="actions.length >= 16" @click="add"><Icon name="plus" />{{ t('addRuleAction') }}</button></div>
    <TransitionGroup name="surface" tag="div" class="form-stack">
      <div v-for="(action, index) in actions" :key="index" class="rule-action form-row">
        <label>{{ t('change') }}<select :value="action.target" @change="changeTarget(index, $event)"><option v-for="field in targets" :key="field" :value="field">{{ t(field === 'text' ? 'replacementText' : field) }}</option></select></label>
        <label v-if="action.target === 'visible'">{{ t('result') }}<select :value="String(action.visible)" @change="replace(index, { target: 'visible', visible: ($event.target as HTMLSelectElement).value === 'true' })"><option value="true">{{ t('show') }}</option><option value="false">{{ t('hide') }}</option></select></label>
        <label v-else-if="action.target === 'text' || action.target === 'title'" class="grow">{{ t(action.target === 'title' ? 'title' : 'replacementText') }}<textarea :value="action.text" rows="2" :maxlength="action.target === 'title' ? 60 : 1000" @input="replace(index, { target: action.target, text: ($event.target as HTMLTextAreaElement).value })"></textarea></label>
        <label v-else-if="'color' in action">{{ t('color') }}<input type="color" :value="action.color || '#ffffff'" @input="replace(index, { target: action.target, color: ($event.target as HTMLInputElement).value })"></label>
        <button type="button" class="icon-button danger-text" :disabled="actions.length === 1" :aria-label="t('removeRuleAction')" @click="remove(index)"><Icon name="remove" /></button>
      </div>
    </TransitionGroup>
  </div>
</template>
