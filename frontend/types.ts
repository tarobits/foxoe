import type { IconName } from './icons';
export type { IconName } from './icons';
export interface KeyColors { iconColor?: string | null; textColor?: string | null; backgroundColor?: string | null }
export interface Application extends KeyColors { id: string; name: string; url: string; icon: IconName | null; textSize: number; image?: string | null; images?: Record<string, string>; screens?: unknown[] }
export interface Source { id: string; name: string; url: string; interval: number; authEnv: string }
export interface WidgetRule { source: string; path: string; operator: 'eq' | 'ne' | 'gt' | 'gte' | 'lt' | 'lte' | 'contains' | 'exists' | 'missing' | 'truthy' | 'falsy'; value: string | number | boolean | null; target: 'textColor' | 'backgroundColor' | 'iconColor' | 'visible'; color: string | null; visible: boolean }
export interface WidgetAppearance { textColor?: string | null; backgroundColor?: string | null; iconColor?: string | null; fontSize?: number | null; align?: 'left' | 'center' | 'right'; rules: WidgetRule[] }
export interface WidgetElement extends WidgetAppearance { id: string; kind: 'clock' | 'text' | 'value' | 'list' | 'icon' | 'layout'; title: string; text: string; source: string; path: string; itemPath: string; unit: string; icon?: IconName | null }
export interface WidgetItem extends WidgetElement { row: number; column: number; rowSpan: number; columnSpan: number }
export interface Widget extends WidgetElement { x: number; y: number; w: number; h: number; padding: number; gap: number; allowOverlap?: boolean; columns: number[]; rows: number[]; items: WidgetItem[] }
export interface Config { gridVersion: 2; revision: number; title: string; locale: 'en' | 'de'; brightness: number; apps: Application[]; sources: Source[]; widgets: Widget[] }
export interface DeckButton extends KeyColors { id: string; label: string; icon: IconName | null; textSize?: number; image?: string | null; disabled?: boolean }
export interface DeckState { connected: boolean; device: string; activeApp: string | null; generation: number; configRevision: number; buttons: (DeckButton | null)[] }
export interface DataEntry { value: unknown; error: string | null; updatedAt: number | null }
