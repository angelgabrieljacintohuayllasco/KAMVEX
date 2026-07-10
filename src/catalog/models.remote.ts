import type { CatalogModel, ModelCapability } from "./types";

/**
 * Remote provider seed models — derived from Jan's `providerModels` capability
 * matrix. These are catalog-ready (shown in the Models UI with badges) but
 * inference is not wired (KAMVEX stays local-first).
 *
 * Add a model = append one object. The Models UI picks it up automatically.
 */

type Caps = {
  images?: string[];
  tools?: string[];
};

function caps(id: string, info?: Caps): ModelCapability[] {
  const c: ModelCapability[] = ["chat"];
  if (info?.tools?.includes(id)) c.push("tools");
  if (info?.images?.includes(id)) c.push("vision");
  return c;
}

function remote(
  provider: string,
  id: string,
  name: string,
  developer: string,
  capabilities: ModelCapability[],
  contextK?: number,
): CatalogModel {
  return { id: `${provider}/${id}`, provider, name, developer, type: "chat", capabilities, contextK };
}

// ── OpenAI ──
const oaiImg = ["gpt-5", "gpt-5-mini", "gpt-4.5-preview", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo"];
const oaiTools = ["gpt-5", "gpt-5-mini", "gpt-4.5-preview", "gpt-4.1", "gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4-turbo"];
const oaiCaps: Caps = { images: oaiImg, tools: oaiTools };

// ── Anthropic ──
const antAll = ["claude-sonnet-4-5", "claude-haiku-4-5", "claude-opus-4-1", "claude-sonnet-4", "claude-opus-4", "claude-3-7-sonnet-20250219", "claude-3-5-haiku-20241022"];
const antCaps: Caps = { images: antAll, tools: antAll };

// ── Gemini ──
const gemAll = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"];
const gemCaps: Caps = { images: gemAll, tools: gemAll };

// ── Mistral ──
const misImg = ["magistral-medium-2509", "magistral-small-2509", "pixtral-large-2411", "pixtral-12b-2409", "mistral-small-2506"];
const misTools = ["mistral-large-2411", "mistral-small-2506"];

// ── Groq ──
// ── xAI ──
const xaiTools = ["grok-4-1-fast-reasoning", "grok-4-fast-reasoning", "grok-3", "grok-3-mini"];
const xaiImg = ["grok-2-vision-1212"];

export const REMOTE_MODELS: CatalogModel[] = [
  // OpenAI
  remote("openai", "gpt-5", "GPT-5", "OpenAI", caps("gpt-5", oaiCaps), 128),
  remote("openai", "gpt-5-mini", "GPT-5 Mini", "OpenAI", caps("gpt-5-mini", oaiCaps), 128),
  remote("openai", "gpt-4.1", "GPT-4.1", "OpenAI", caps("gpt-4.1", oaiCaps), 128),
  remote("openai", "gpt-4o", "GPT-4o", "OpenAI", caps("gpt-4o", oaiCaps), 128),
  remote("openai", "gpt-4o-mini", "GPT-4o Mini", "OpenAI", caps("gpt-4o-mini", oaiCaps), 128),
  remote("openai", "o3-mini", "o3-mini", "OpenAI", caps("o3-mini", oaiCaps), 128),

  // Anthropic
  remote("anthropic", "claude-sonnet-4-5", "Claude Sonnet 4.5", "Anthropic", caps("claude-sonnet-4-5", antCaps), 200),
  remote("anthropic", "claude-opus-4-1", "Claude Opus 4.1", "Anthropic", caps("claude-opus-4-1", antCaps), 200),
  remote("anthropic", "claude-sonnet-4", "Claude Sonnet 4", "Anthropic", caps("claude-sonnet-4", antCaps), 200),
  remote("anthropic", "claude-haiku-4-5", "Claude Haiku 4.5", "Anthropic", caps("claude-haiku-4-5", antCaps), 200),

  // Gemini
  remote("gemini", "gemini-2.5-pro", "Gemini 2.5 Pro", "Google", caps("gemini-2.5-pro", gemCaps), 1000),
  remote("gemini", "gemini-2.5-flash", "Gemini 2.5 Flash", "Google", caps("gemini-2.5-flash", gemCaps), 1000),
  remote("gemini", "gemini-2.0-flash", "Gemini 2.0 Flash", "Google", caps("gemini-2.0-flash", gemCaps), 1000),
  remote("gemini", "gemini-1.5-flash", "Gemini 1.5 Flash", "Google", caps("gemini-1.5-flash", gemCaps), 1000),

  // Mistral
  remote("mistral", "mistral-large-2411", "Mistral Large", "Mistral", caps("mistral-large-2411", { tools: misTools }), 128),
  remote("mistral", "codestral-2508", "Codestral", "Mistral", ["chat", "code"], 256),
  remote("mistral", "pixtral-large-2411", "Pixtral Large", "Mistral", caps("pixtral-large-2411", { images: misImg }), 128),
  remote("mistral", "mistral-small-2506", "Mistral Small", "Mistral", caps("mistral-small-2506", { images: misImg, tools: misTools }), 128),

  // Groq
  remote("groq", "llama-3.3-70b-versatile", "Llama 3.3 70B", "Meta (via Groq)", ["chat"], 128),
  remote("groq", "llama-3.1-8b-instant", "Llama 3.1 8B", "Meta (via Groq)", ["chat"], 128),
  remote("groq", "qwen/qwen3-32b", "Qwen3 32B", "Qwen (via Groq)", ["chat"], 128),

  // xAI
  remote("xai", "grok-4-1-fast-reasoning", "Grok 4.1 Fast", "xAI", caps("grok-4-1-fast-reasoning", { tools: xaiTools }), 128),
  remote("xai", "grok-3", "Grok 3", "xAI", caps("grok-3", { tools: xaiTools }), 128),
  remote("xai", "grok-3-mini", "Grok 3 Mini", "xAI", caps("grok-3-mini", { tools: xaiTools }), 128),
  remote("xai", "grok-2-vision-1212", "Grok 2 Vision", "xAI", caps("grok-2-vision-1212", { images: xaiImg }), 32),

  // HuggingFace
  remote("huggingface", "deepseek-ai/DeepSeek-R1-0528", "DeepSeek R1", "DeepSeek (via HF)", ["chat", "reasoning", "tools"], 128),
  remote("huggingface", "deepseek-ai/DeepSeek-V3-0324", "DeepSeek V3", "DeepSeek (via HF)", ["chat", "tools"], 128),

  // NVIDIA NIM
  remote("nvidia", "moonshotai/kimi-k2.5", "Kimi K2.5", "Moonshot (via NVIDIA)", ["chat"], 128),

  // MiniMax
  remote("minimax", "MiniMax-M2.7", "MiniMax M2.7", "MiniMax", ["chat", "tools"], 204),
  remote("minimax", "MiniMax-M2.5", "MiniMax M2.5", "MiniMax", ["chat", "tools"], 204),

  // OpenRouter (representative — router supports many more)
  remote("openrouter", "deepseek/deepseek-r1:free", "DeepSeek R1 (free)", "DeepSeek (via OR)", ["chat", "reasoning"], 128),
  remote("openrouter", "qwen/qwen3-30b-a3b:free", "Qwen3 30B A3B (free)", "Qwen (via OR)", ["chat"], 128),
];
