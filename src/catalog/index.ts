import type { CatalogModel, ModelCapability, ModelType, SizeCategory } from "./types";
import { PROVIDERS } from "./providers";
import { LOCAL_MODELS } from "./models.local";
import { REMOTE_MODELS } from "./models.remote";

export type { CatalogModel, CatalogProvider, ModelCapability, ModelType, SizeCategory } from "./types";
export { PROVIDERS, getProvider } from "./providers";

// ── Aggregate catalog ──

function deriveSizeCategory(m: CatalogModel): CatalogModel {
  if (m.sizeCategory || !m.sizeMb) return m;
  let cat: SizeCategory;
  if (m.sizeMb < 1000) cat = "ultralight";
  else if (m.sizeMb < 3000) cat = "light";
  else if (m.sizeMb < 6000) cat = "medium";
  else if (m.sizeMb < 10000) cat = "large";
  else cat = "xl";
  return { ...m, sizeCategory: cat };
}

export const ALL_MODELS: CatalogModel[] = [
  ...LOCAL_MODELS.map(deriveSizeCategory),
  ...REMOTE_MODELS,
];

// ── Search ──

export function searchModels(models: CatalogModel[], query: string): CatalogModel[] {
  const q = query.trim().toLowerCase();
  if (!q) return models;
  const tokens = q.split(/\s+/);
  return models.filter((m) => {
    const hay = `${m.name} ${m.developer ?? ""} ${m.provider} ${m.description ?? ""} ${m.params ?? ""}`.toLowerCase();
    return tokens.every((t) => hay.includes(t));
  });
}

// ── Filters ──

export function filterByProvider(models: CatalogModel[], providerId: string): CatalogModel[] {
  return models.filter((m) => m.provider === providerId);
}

export function filterByType(models: CatalogModel[], type: ModelType): CatalogModel[] {
  return models.filter((m) => m.type === type);
}

export function filterByCapability(models: CatalogModel[], cap: ModelCapability): CatalogModel[] {
  return models.filter((m) => m.capabilities.includes(cap));
}

export function filterBySize(models: CatalogModel[], cat: SizeCategory): CatalogModel[] {
  return models.filter((m) => m.sizeCategory === cat);
}

export type CatalogFilters = {
  provider?: string;
  type?: ModelType;
  capability?: ModelCapability;
  size?: SizeCategory;
};

export function applyFilters(models: CatalogModel[], f: CatalogFilters): CatalogModel[] {
  let result = models;
  if (f.provider) result = filterByProvider(result, f.provider);
  if (f.type) result = filterByType(result, f.type);
  if (f.capability) result = filterByCapability(result, f.capability);
  if (f.size) result = filterBySize(result, f.size);
  return result;
}

// ── Grouping ──

export function groupByProvider(models: CatalogModel[]): Map<string, CatalogModel[]> {
  const map = new Map<string, CatalogModel[]>();
  for (const m of models) {
    const list = map.get(m.provider) ?? [];
    list.push(m);
    map.set(m.provider, list);
  }
  return map;
}

export function groupByType(models: CatalogModel[]): Map<ModelType, CatalogModel[]> {
  const map = new Map<ModelType, CatalogModel[]>();
  for (const m of models) {
    const list = map.get(m.type) ?? [];
    list.push(m);
    map.set(m.type, list);
  }
  return map;
}

// ── Sort ──

export type SortKey = "name" | "size" | "provider";

export function sortModels(models: CatalogModel[], key: SortKey): CatalogModel[] {
  const sorted = [...models];
  switch (key) {
    case "name":
      sorted.sort((a, b) => a.name.localeCompare(b.name));
      break;
    case "size":
      sorted.sort((a, b) => (a.sizeMb ?? Infinity) - (b.sizeMb ?? Infinity));
      break;
    case "provider":
      sorted.sort((a, b) => a.provider.localeCompare(b.provider));
      break;
  }
  return sorted;
}

// ── Stats ──

export function catalogStats() {
  const local = LOCAL_MODELS.length;
  const remote = REMOTE_MODELS.length;
  return { local, remote, total: local + remote, providers: PROVIDERS.length };
}
