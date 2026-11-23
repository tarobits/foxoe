<script setup lang="ts">
import { computed } from 'vue';
import { HomeIcon, PrinterIcon, WindowIcon, Squares2X2Icon, PlayIcon, BackspaceIcon, CheckIcon, XMarkIcon, ArrowLeftIcon, ArrowPathIcon, Cog6ToothIcon, PencilSquareIcon, PlusIcon, TrashIcon, ArrowsPointingOutIcon, Bars3Icon, CpuChipIcon, ClockIcon } from '@heroicons/vue/24/outline';
const props = defineProps<{ name: string }>();
const icons: Record<string, typeof HomeIcon> = { home: HomeIcon, printer: PrinterIcon, window: WindowIcon, keypad: Squares2X2Icon, play: PlayIcon, backspace: BackspaceIcon, check: CheckIcon, close: XMarkIcon, back: ArrowLeftIcon, reload: ArrowPathIcon, settings: Cog6ToothIcon, edit: PencilSquareIcon, plus: PlusIcon, remove: TrashIcon, resize: ArrowsPointingOutIcon, move: Bars3Icon, system: CpuChipIcon, clock: ClockIcon };
const icon = computed(() => icons[props.name] || WindowIcon);
</script>
<template><img v-if="name === 'foxoe'" class="icon" src="/foxoe.svg" alt=""><component v-else :is="icon" class="icon" aria-hidden="true" /></template>
