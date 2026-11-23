import type { IconName } from './icons';
export type { IconName } from './icons';
export interface Application { id: string; name: string; url: string; icon: IconName | null; textSize: number; image?: string | null; images?: Record<string, string>; screens?: unknown[] }
export interface Source { id: string; name: string; url: string; interval: number; authEnv: string }
export interface Widget { id: string; kind: 'clock' | 'text' | 'value' | 'list'; title: string; text: string; source: string; path: string; itemPath: string; unit: string; x: number; y: number; w: number; h: number }
export interface Config { revision: number; title: string; locale: 'en' | 'de'; brightness: number; apps: Application[]; sources: Source[]; widgets: Widget[] }
export interface DeckState { connected: boolean; device: string; activeApp: string | null; generation: number; configRevision: number; buttons: ({ id: string; label: string; icon: IconName | null; textSize?: number; image?: string | null; disabled: boolean } | null)[] }
export interface DataEntry { value: unknown; error: string | null; updatedAt: number | null }
