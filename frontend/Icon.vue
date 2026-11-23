<script setup lang="ts">
import { computed } from 'vue';
import catalog from '../foxoe/icon_catalog.json';
const props = defineProps<{ name: string | null }>();
const icon = computed(() => props.name && Object.hasOwn(catalog, props.name) ? props.name : 'window');
</script>
<template><img v-if="name === 'foxoe'" class="icon" src="/foxoe.svg" alt=""><svg v-else-if="name !== null" class="icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><use :href="`/heroicons.svg#${icon}`" /></svg></template>
