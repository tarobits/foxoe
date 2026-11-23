import type { IconName } from './icons';
export type { IconName } from './icons';
export interface KeyColors { iconColor?: string | null; textColor?: string | null; backgroundColor?: string | null }
export interface Application extends KeyColors { id: string; name: string; url: string; icon: IconName | null; textSize: number; image?: string | null; images?: Record<string, string>; screens?: unknown[] }
export interface Source { id: string; name: string; url: string; interval: number; authEnv: string }
export interface Widget { id: string; kind: 'clock' | 'text' | 'value' | 'list'; title: string; text: string; source: string; path: string; itemPath: string; unit: string; x: number; y: number; w: number; h: number }
export interface Config { revision: number; title: string; locale: 'en' | 'de'; brightness: number; apps: Application[]; sources: Source[]; widgets: Widget[] }
export interface DeckButton extends KeyColors { id: string; label: string; icon: IconName | null; textSize?: number; image?: string | null; disabled?: boolean }
export interface DeckState { connected: boolean; device: string; activeApp: string | null; generation: number; configRevision: number; buttons: (DeckButton | null)[] }
export interface DataEntry { value: unknown; error: string | null; updatedAt: number | null }
