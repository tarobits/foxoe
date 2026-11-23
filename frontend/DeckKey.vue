<script setup lang="ts">
import { computed } from 'vue';
import type { DeckButton } from './types';
const props = defineProps<{ button?: DeckButton | null; home?: boolean }>();
const source = computed(() => '/api/deck/preview?key=' + encodeURIComponent(JSON.stringify({
  label: props.button?.label ?? '', icon: props.button?.icon ?? null,
  textSize: props.button?.textSize ?? 14, image: props.button?.image ?? null,
  disabled: props.button?.disabled ?? false, home: props.home ?? false,
  textColor: props.button?.textColor ?? null, iconColor: props.button?.iconColor ?? null,
  backgroundColor: props.button?.backgroundColor ?? null,
})));
</script>
<template>
  <div class="deck-key"><img :src="source" :alt="button?.label ?? ''" width="72" height="72"></div>
</template>
