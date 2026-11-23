<script setup lang="ts">
import Icon from './Icon.vue';
import type { DeckButton } from './types';
defineProps<{ button?: DeckButton | null; home?: boolean }>();
</script>
<template>
  <div class="deck-key" :class="{ disabled: button?.disabled, 'home-key': home }" :style="{ backgroundColor: home ? '#4f46e5' : button?.backgroundColor || undefined }">
    <img v-if="button?.image" :src="`/api/images/${button.image}`" alt="">
    <span v-else-if="button?.icon === 'foxoe' && button.iconColor && !home" class="icon tinted-fox" :style="{ backgroundColor: button.iconColor }" />
    <Icon v-else-if="button" :name="home ? 'home' : button.icon" :style="{ color: home ? undefined : button.iconColor || undefined }" />
    <span :style="{ fontSize: `${button?.textSize ?? 14}px`, color: home ? undefined : button?.textColor || undefined }">{{ button?.label }}</span>
  </div>
</template>
