import catalog from '../foxoe/icon_catalog.json';

export type IconName = keyof typeof catalog | 'foxoe';
export const iconNames: IconName[] = ['foxoe', ...Object.keys(catalog).sort() as (keyof typeof catalog)[]];
export function matchingIcons(query: string): IconName[] {
  const words = query.toLowerCase().trim().split(/\s+/);
  return iconNames.filter(name => words.every(word => name.includes(word)));
}
