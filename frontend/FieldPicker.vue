<script setup lang="ts">
import { computed, useId } from 'vue';
import { systemPaths, dataPaths } from './dataPaths';
import { t } from './i18n';
const props = defineProps<{ modelValue: string; source: string; value?: unknown }>();
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const id = useId();
const choices = computed(() => props.source === 'system' ? systemPaths : dataPaths(props.value));
</script>
<template>
  <div class="field-picker form-stack">
    <label>{{ t('availableFields') }}<select :value="choices.includes(modelValue) ? modelValue : ''" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"><option value="">{{ t('chooseField') }}</option><option v-for="path in choices" :key="path" :value="path">{{ source === 'system' ? `${t(path)} · ${path}` : path }}</option></select></label>
    <label :for="id">{{ t('path') }}<input :id="id" :value="modelValue" maxlength="200" spellcheck="false" @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"></label>
  </div>
</template>
