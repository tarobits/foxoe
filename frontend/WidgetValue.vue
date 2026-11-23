<script setup lang="ts">
import { computed } from 'vue';
import type { WidgetElement, DataEntry } from './types';
import Icon from './Icon.vue';
import { readPath, formatValue, listPage } from './model.js';
import { t, locale } from './i18n';
const props = defineProps<{ widget: WidgetElement; entry?: DataEntry; now: Date }>();
const value = computed(() => readPath(props.entry?.value, props.widget.path));
const formatted = computed(() => formatValue(value.value, locale.value));
const page = computed(() => listPage(value.value));
const rows = computed(() => page.value.rows);
const heading = computed(() => props.widget.title || (['value', 'list'].includes(props.widget.kind) && props.widget.source === 'system' && props.widget.path ? t(props.widget.path) : ['clock', 'icon'].includes(props.widget.kind) ? '' : t(props.widget.kind)));
</script>
<template>
  <div class="widget-content" :class="`widget-${widget.kind}`">
    <h2 v-if="heading">{{ heading }}</h2>
    <template v-if="widget.kind === 'clock'">
      <time class="clock-time" :datetime="now.toISOString()">{{ now.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) }}</time>
      <p class="clock-date">{{ now.toLocaleDateString(locale, { weekday: 'long', day: 'numeric', month: 'long' }) }}</p>
    </template>
    <p v-else-if="widget.kind === 'text'" class="text-content">{{ widget.text }}</p>
    <div v-else-if="widget.kind === 'icon'" class="widget-icon"><Icon :name="widget.icon ?? null" /></div>
    <template v-else>
      <p v-if="entry?.error" class="data-warning" role="status">{{ t('stale') }}<span v-if="entry.updatedAt"> · {{ t('lastUpdated') }} {{ new Date(entry.updatedAt * 1000).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) }}</span></p>
      <p v-if="!entry" class="muted">{{ t('waiting') }}</p>
      <template v-else-if="widget.kind === 'value'">
        <div v-if="formatted !== null" class="metric"><span>{{ formatted }}</span><small v-if="widget.unit">{{ widget.unit }}</small></div>
        <p v-else class="muted">{{ t('noData') }}</p>
      </template>
      <template v-else-if="widget.kind === 'list'">
        <p v-if="value == null" class="muted">{{ t('noData') }}</p>
        <p v-else-if="!Array.isArray(value)" class="muted">{{ t('notAList') }}</p>
        <p v-else-if="!rows.length" class="muted">{{ t('emptyList') }}</p>
        <ul v-else class="queue-list"><li v-for="(row, index) in rows" :key="index">{{ formatValue(readPath(row, widget.itemPath), locale) ?? t('noData') }}</li></ul>
        <p v-if="page.truncated" class="muted">{{ t('moreItems') }}</p>
      </template>
    </template>
  </div>
</template>
