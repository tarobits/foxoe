<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import WidgetContent from './WidgetContent.vue';
import { contentStyle } from './model.js';
import { widgetDimensions } from './dashboardViewport';
import type { Widget, DataEntry } from './types';
const props = defineProps<{ widget: Widget; data: Record<string, DataEntry>; now: Date }>();
const viewport = ref<HTMLElement>();
const size = computed(() => widgetDimensions(props.widget.w, props.widget.h));
const width = ref(0);
watch(viewport, (target, _, cleanup) => {
  if (!target) return;
  const observer = new ResizeObserver(([entry]) => { if (entry) width.value = entry.contentRect.width; });
  observer.observe(target); cleanup(() => observer.disconnect());
}, { flush: 'post' });
const scale = computed(() => Math.min(1, width.value / size.value.width));
</script>
<template>
  <div ref="viewport" class="widget-preview-viewport" :style="{ height: `${size.height * scale}px` }">
    <div class="widget-panel widget-preview-panel" :style="{ ...contentStyle(widget, data), padding: `${widget.padding}px`, width: `${size.width}px`, height: `${size.height}px`, transform: `scale(${scale})` }"><WidgetContent :widget="widget" :data="data" :now="now" /></div>
  </div>
</template>
