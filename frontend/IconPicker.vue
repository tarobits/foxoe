<script setup lang="ts">
import { computed, ref } from 'vue';
import Icon from './Icon.vue';
import { matchingIcons, type IconName } from './icons';
import { t } from './i18n';

const value = defineModel<IconName | null>({ required: true });
const query = ref('');
const matches = computed(() => matchingIcons(query.value));
// Keep the current value selectable when a search excludes it.
const choices = computed(() => value.value && !matches.value.includes(value.value) ? [value.value, ...matches.value] : matches.value);
</script>
<template>
  <div class="icon-picker">
    <input v-model="query" type="search" :aria-label="t('searchIcons')" :placeholder="t('searchIcons')">
    <label>{{ t('icon') }}<div class="icon-choice"><Icon :name="value" /><select v-model="value"><option :value="null">{{ t('noIcon') }}</option><option v-for="name in choices" :key="name" :value="name">{{ name === 'foxoe' ? 'FoxOE' : name }}</option></select></div></label>
    <Transition name="notice"><span v-if="!matches.length" role="status">{{ t('noIconsFound') }}</span></Transition>
  </div>
</template>
