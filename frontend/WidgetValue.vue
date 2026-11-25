<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { WidgetElement, DataEntry } from './types';
import Icon from './Icon.vue';
import type { IconName } from './icons';
import { readPath, formatValue, listPage, widgetTitle } from './model.js';
import { t, locale } from './i18n';
import { evaluateFormula } from './formula.js';
import { useTextFit } from './textFit';
const props = defineProps<{ widget: WidgetElement; maxTextSize?: number | null; entry?: DataEntry; presentation?: { text?: string; title?: string; icon?: IconName | null }; now: Date }>();
const value = computed(() => readPath(props.entry?.value, props.widget.path));
const calculated = computed(() => props.widget.kind === 'value' && props.widget.formula?.trim() ? evaluateFormula(props.widget.formula.trim(), value.value, props.entry?.value) : { value: value.value, error: null });
const formatted = computed(() => props.presentation?.text ?? formatValue(calculated.value.value, locale.value, props.widget.decimals ?? null));
const page = computed(() => listPage(value.value));
const rows = computed(() => page.value.rows);
const heading = computed(() => widgetTitle({ ...props.widget, title: props.presentation?.title ?? props.widget.title }));
const box = ref<HTMLElement>(), content = ref<HTMLElement>();
const scheduleFit = useTextFit(box, content, () => props.widget.fontSize ?? props.maxTextSize ?? 96, () => props.widget.kind !== 'icon');
watch([() => props.widget, () => props.entry, () => props.presentation, () => props.widget.kind === 'clock' ? Math.floor(props.now.getTime() / 60000) : null, locale], scheduleFit, { deep: true, flush: 'post' });
</script>
<template>
  <div ref="box" class="widget-content" :class="`widget-${widget.kind}`">
    <div ref="content" class="widget-value-content">
    <Transition name="notice"><h2 v-if="heading">{{ heading }}</h2></Transition>
    <template v-if="widget.kind === 'clock'">
      <time class="clock-time" :datetime="now.toISOString()">{{ now.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) }}</time>
      <p class="clock-date">{{ now.toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' }) }}</p>
    </template>
    <p v-else-if="widget.kind === 'text'" class="text-content">{{ presentation?.text ?? widget.text }}</p>
    <div v-else-if="widget.kind === 'icon'" class="widget-icon-frame"><Icon :name="presentation?.icon !== undefined ? presentation.icon : widget.icon ?? null" /></div>
    <template v-else>
      <p v-if="entry?.error" class="data-warning" role="status">{{ t('stale') }}<span v-if="entry.updatedAt"> · {{ t('lastUpdated') }} {{ new Date(entry.updatedAt * 1000).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) }}</span></p>
      <p v-if="calculated.error && presentation?.text === undefined" class="data-warning" role="status">{{ t(calculated.error) }}</p>
      <p v-else-if="!entry && presentation?.text === undefined" class="muted">{{ t('waiting') }}</p>
      <template v-else-if="widget.kind === 'value'">
        <div v-if="formatted !== null" class="metric"><span>{{ formatted }}</span><small v-if="widget.unit && presentation?.text === undefined">{{ widget.unit }}</small></div>
        <p v-else class="muted">{{ t('noData') }}</p>
      </template>
      <template v-else-if="widget.kind === 'list'">
        <p v-if="value == null" class="muted">{{ t('noData') }}</p>
        <p v-else-if="!Array.isArray(value)" class="muted">{{ t('notAList') }}</p>
        <p v-else-if="!rows.length" class="muted">{{ t('emptyList') }}</p>
        <ul v-else class="queue-list"><li v-for="(row, index) in rows" :key="index">{{ formatValue(readPath(row, widget.itemPath), locale, widget.decimals ?? null) ?? t('noData') }}</li></ul>
        <p v-if="page.truncated" class="muted">{{ t('moreItems') }}</p>
      </template>
    </template>
    </div>
  </div>
</template>
