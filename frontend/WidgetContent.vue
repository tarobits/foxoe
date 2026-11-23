<script setup lang="ts">
import WidgetValue from './WidgetValue.vue';
import type { Widget, DataEntry } from './types';
import { appearance, contentStyle, widgetTitle } from './model.js';
defineProps<{ widget: Widget; data: Record<string, DataEntry>; now: Date; editing?: boolean }>();
</script>
<template>
  <div class="widget-body" :style="contentStyle(widget, data)">
    <template v-if="widget.kind === 'layout'">
      <Transition name="notice"><h2 v-if="widgetTitle(widget)" class="layout-heading">{{ widgetTitle(widget) }}</h2></Transition>
      <div class="widget-layout" :style="{ gridTemplateColumns: widget.columns.map(n => `minmax(0, ${n}fr)`).join(' '), gridTemplateRows: widget.rows.map(n => `minmax(0, ${n}fr)`).join(' '), gap: `${widget.gap}px` }">
        <div v-for="item in widget.items" v-show="editing || appearance(item, data).visible" :key="item.id" class="widget-cell" :class="{ 'rule-hidden': editing && !appearance(item, data).visible }" :style="{ ...contentStyle(item, data), gridColumn: `${item.column + 1} / span ${item.columnSpan}`, gridRow: `${item.row + 1} / span ${item.rowSpan}` }">
          <WidgetValue :widget="item" :entry="data[item.source]" :now="now" />
        </div>
      </div>
    </template>
    <WidgetValue v-else :widget="widget" :entry="data[widget.source]" :now="now" />
  </div>
</template>
