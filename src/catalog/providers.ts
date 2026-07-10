import type { CatalogProvider } from "./types";

/**
 * Provider registry — declarative, à la Jan's `predefinedProviders`.
 *
 * Add a provider = append one object here. The catalog index and the Models UI
 * derive everything (filters, sections, badges) from this list, so nothing else
 * needs to change.
 *
 * `runnable: true`  → KAMVEX runs it now (local llama.cpp).
 * `runnable: false` → catalog-ready, inference is pluggable for the future
 *                     (keeps KAMVEX local-first; remote engines are not wired yet).
 */
export const PROVIDERS: CatalogProvider[] = [
  {
    id: "llamacpp",
    name: "Llama.cpp (local)",
    kind: "local",
    icon: "Cpu",
    runnable: true,
    description: "Motor local GGUF. Corre 100% en tu equipo (CPU / Vulkan / CUDA).",
  },
  {
    id: "openai",
    name: "OpenAI",
    kind: "remote",
    icon: "Sparkles",
    baseUrl: "https://api.openai.com/v1",
    exploreUrl: "https://platform.openai.com/docs/models",
    runnable: false,
  },
  {
    id: "anthropic",
    name: "Anthropic",
    kind: "remote",
    icon: "Sparkles",
    baseUrl: "https://api.anthropic.com/v1",
    exploreUrl: "https://docs.anthropic.com/en/docs/about-claude/models",
    runnable: false,
  },
  {
    id: "gemini",
    name: "Google Gemini",
    kind: "remote",
    icon: "Sparkles",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    exploreUrl: "https://ai.google.dev/gemini-api/docs/models/gemini",
    runnable: false,
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    kind: "remote",
    icon: "Globe",
    baseUrl: "https://openrouter.ai/api/v1",
    exploreUrl: "https://openrouter.ai/models",
    runnable: false,
  },
  {
    id: "mistral",
    name: "Mistral",
    kind: "remote",
    icon: "Sparkles",
    baseUrl: "https://api.mistral.ai/v1",
    exploreUrl: "https://docs.mistral.ai/getting-started/models/models_overview/",
    runnable: false,
  },
  {
    id: "groq",
    name: "Groq",
    kind: "remote",
    icon: "Zap",
    baseUrl: "https://api.groq.com/openai/v1",
    exploreUrl: "https://console.groq.com/docs/models",
    runnable: false,
  },
  {
    id: "huggingface",
    name: "HuggingFace",
    kind: "remote",
    icon: "Globe",
    baseUrl: "https://router.huggingface.co/v1",
    exploreUrl: "https://huggingface.co/models?pipeline_tag=text-generation",
    runnable: false,
  },
  {
    id: "xai",
    name: "xAI (Grok)",
    kind: "remote",
    icon: "Sparkles",
    baseUrl: "https://api.x.ai/v1",
    exploreUrl: "https://docs.x.ai/overview",
    runnable: false,
  },
  {
    id: "nvidia",
    name: "NVIDIA NIM",
    kind: "remote",
    icon: "Zap",
    baseUrl: "https://integrate.api.nvidia.com/v1",
    exploreUrl: "https://build.nvidia.com/models",
    runnable: false,
  },
  {
    id: "minimax",
    name: "MiniMax",
    kind: "remote",
    icon: "Sparkles",
    baseUrl: "https://api.minimax.io/v1",
    exploreUrl: "https://platform.minimax.io/docs/api-reference/text-openai-api",
    runnable: false,
  },
];

export function getProvider(id: string): CatalogProvider | undefined {
  return PROVIDERS.find((p) => p.id === id);
}
