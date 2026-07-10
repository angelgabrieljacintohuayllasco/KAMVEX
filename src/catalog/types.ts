/**
 * Model catalog types — the modular data layer behind KAMVEX's model library.
 *
 * Design goal (inspired by Jan's `predefinedProviders` registry): adding a new
 * model or provider is a single declarative object in a data file — no UI or
 * logic changes. The Models page derives all its filters/sections from this data.
 */

/** What a model can do. Drives capability badges + the capability filter. */
export type ModelCapability =
  | "chat"
  | "tools"
  | "vision"
  | "reasoning"
  | "code"
  | "embedding";

/** Primary specialization. Drives the type filter + grouping. */
export type ModelType =
  | "chat"
  | "code"
  | "vision"
  | "reasoning"
  | "embedding"
  | "multimodal";

/** Size bucket for local GGUF models. */
export type SizeCategory = "ultralight" | "light" | "medium" | "large" | "xl";

/** Local = runnable now via llama.cpp. Remote = pluggable, future inference. */
export type ProviderKind = "local" | "remote";

export type CatalogProvider = {
  id: string;
  name: string;
  kind: ProviderKind;
  /** lucide-react icon name rendered by the UI, or undefined for a generic dot. */
  icon?: string;
  baseUrl?: string;
  /** External page to browse/obtain models for this provider. */
  exploreUrl?: string;
  /**
   * Whether KAMVEX can run inference against this provider today.
   * Local llama.cpp = true. Remote providers are catalog-ready but not yet
   * wired for inference (local-first philosophy) → false, shown as "pluggable".
   */
  runnable: boolean;
  description?: string;
};

export type CatalogModel = {
  id: string;
  /** Provider id (see providers.ts). */
  provider: string;
  name: string;
  developer?: string;
  description?: string;
  type: ModelType;
  capabilities: ModelCapability[];

  // ── Local GGUF fields (provider kind = "local") ──
  repo?: string;
  file?: string;
  sizeMb?: number;
  sizeCategory?: SizeCategory;
  params?: string; // e.g. "7B"
  quant?: string; // e.g. "Q4_K_M"
  /** Needs an mmproj companion to actually see images (vision GGUF). */
  needsMmproj?: boolean;

  // ── Remote fields (provider kind = "remote") ──
  contextK?: number;
};
