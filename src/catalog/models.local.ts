import type { CatalogModel } from "./types";

/**
 * Local GGUF catalog — runnable now via llama.cpp.
 *
 * Each entry is downloaded by the sidecar via (repo, file). Filenames follow
 * HuggingFace GGUF conventions; a 404 at download time just means that exact
 * quant isn't on that repo — swap the file string, no code changes.
 *
 * `sizeCategory` is derived from `sizeMb` in index.ts — don't set it here.
 * Add a model = append one object. The Models UI picks it up automatically.
 *
 * ponytail: vision entries carry `needsMmproj` + the multimodal tag, but the
 * llama.cpp mmproj wiring isn't built yet — they download and tag correctly,
 * full image input is a future backend step.
 */
const L = (m: Omit<CatalogModel, "provider">): CatalogModel => ({ ...m, provider: "llamacpp" });

export const LOCAL_MODELS: CatalogModel[] = [
  // ── Chat — ultraligeros / ligeros ──
  L({ id: "qwen2.5-0.5b", name: "Qwen2.5 0.5B", developer: "Qwen", type: "chat", capabilities: ["chat", "tools"], params: "0.5B", quant: "Q4_K_M", sizeMb: 491, repo: "Qwen/Qwen2.5-0.5B-Instruct-GGUF", file: "qwen2.5-0.5b-instruct-q4_k_m.gguf", description: "El más pequeño de Qwen2.5. Arranca al instante en cualquier equipo." }),
  L({ id: "tinyllama-1.1b", name: "TinyLlama 1.1B", developer: "TinyLlama", type: "chat", capabilities: ["chat"], params: "1.1B", quant: "Q4_K_M", sizeMb: 700, repo: "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF", file: "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf", description: "Modelo diminuto para pruebas rápidas y hardware muy limitado." }),
  L({ id: "llama-3.2-1b", name: "Llama 3.2 1B", developer: "Meta", type: "chat", capabilities: ["chat", "tools"], params: "1B", quant: "Q4_K_M", sizeMb: 808, repo: "bartowski/Llama-3.2-1B-Instruct-GGUF", file: "Llama-3.2-1B-Instruct-Q4_K_M.gguf", description: "Llama compacto de Meta, buen equilibrio para CPU." }),
  L({ id: "smollm2-1.7b", name: "SmolLM2 1.7B", developer: "HuggingFace", type: "chat", capabilities: ["chat"], params: "1.7B", quant: "Q4_K_M", sizeMb: 1060, repo: "bartowski/SmolLM2-1.7B-Instruct-GGUF", file: "SmolLM2-1.7B-Instruct-Q4_K_M.gguf", description: "Pequeño pero capaz, entrenado por HuggingFace." }),
  L({ id: "qwen2.5-1.5b", name: "Qwen2.5 1.5B", developer: "Qwen", type: "chat", capabilities: ["chat", "tools"], params: "1.5B", quant: "Q4_K_M", sizeMb: 1120, repo: "Qwen/Qwen2.5-1.5B-Instruct-GGUF", file: "qwen2.5-1.5b-instruct-q4_k_m.gguf", description: "Ligero y versátil, soporta uso de herramientas." }),
  L({ id: "gemma-2-2b", name: "Gemma 2 2B", developer: "Google", type: "chat", capabilities: ["chat"], params: "2B", quant: "Q4_K_M", sizeMb: 1710, repo: "bartowski/gemma-2-2b-it-GGUF", file: "gemma-2-2b-it-Q4_K_M.gguf", description: "Modelo abierto de Google, fuerte en su tamaño." }),
  L({ id: "llama-3.2-3b", name: "Llama 3.2 3B", developer: "Meta", type: "chat", capabilities: ["chat", "tools"], params: "3B", quant: "Q4_K_M", sizeMb: 2020, repo: "unsloth/Llama-3.2-3B-Instruct-GGUF", file: "Llama-3.2-3B-Instruct-Q4_K_M.gguf", description: "Llama 3B, excelente para chat general en equipos modestos." }),
  L({ id: "qwen2.5-3b", name: "Qwen2.5 3B", developer: "Qwen", type: "chat", capabilities: ["chat", "tools"], params: "3B", quant: "Q4_K_M", sizeMb: 2100, repo: "Qwen/Qwen2.5-3B-Instruct-GGUF", file: "qwen2.5-3b-instruct-q4_k_m.gguf", description: "Buen rendimiento general con soporte de herramientas." }),
  L({ id: "phi-3.5-mini", name: "Phi-3.5 Mini", developer: "Microsoft", type: "chat", capabilities: ["chat", "tools"], params: "3.8B", quant: "Q4_K_M", sizeMb: 2390, repo: "bartowski/Phi-3.5-mini-instruct-GGUF", file: "Phi-3.5-mini-instruct-Q4_K_M.gguf", description: "Modelo de Microsoft optimizado para razonamiento eficiente." }),

  // ── Chat — medianos / grandes ──
  L({ id: "qwen2.5-7b", name: "Qwen2.5 7B", developer: "Qwen", type: "chat", capabilities: ["chat", "tools"], params: "7B", quant: "Q4_K_M", sizeMb: 4680, repo: "Qwen/Qwen2.5-7B-Instruct-GGUF", file: "qwen2.5-7b-instruct-q4_k_m.gguf", description: "Uno de los mejores modelos abiertos de 7B." }),
  L({ id: "mistral-7b-v0.3", name: "Mistral 7B v0.3", developer: "Mistral", type: "chat", capabilities: ["chat", "tools"], params: "7B", quant: "Q4_K_M", sizeMb: 4370, repo: "bartowski/Mistral-7B-Instruct-v0.3-GGUF", file: "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf", description: "Clásico de Mistral, sólido y rápido." }),
  L({ id: "llama-3.1-8b", name: "Llama 3.1 8B", developer: "Meta", type: "chat", capabilities: ["chat", "tools"], params: "8B", quant: "Q4_K_M", sizeMb: 4920, repo: "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF", file: "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf", description: "Insignia de Meta en 8B, gran calidad general." }),
  L({ id: "gemma-2-9b", name: "Gemma 2 9B", developer: "Google", type: "chat", capabilities: ["chat"], params: "9B", quant: "Q4_K_M", sizeMb: 5760, repo: "bartowski/gemma-2-9b-it-GGUF", file: "gemma-2-9b-it-Q4_K_M.gguf", description: "Versión grande de Gemma 2, muy competente." }),
  L({ id: "mistral-nemo-12b", name: "Mistral Nemo 12B", developer: "Mistral", type: "chat", capabilities: ["chat", "tools"], params: "12B", quant: "Q4_K_M", sizeMb: 7480, repo: "bartowski/Mistral-Nemo-Instruct-2407-GGUF", file: "Mistral-Nemo-Instruct-2407-Q4_K_M.gguf", description: "12B con contexto largo (128K), creado con NVIDIA." }),
  L({ id: "qwen2.5-14b", name: "Qwen2.5 14B", developer: "Qwen", type: "chat", capabilities: ["chat", "tools"], params: "14B", quant: "Q4_K_M", sizeMb: 8990, repo: "bartowski/Qwen2.5-14B-Instruct-GGUF", file: "Qwen2.5-14B-Instruct-Q4_K_M.gguf", description: "Modelo grande para respuestas de mayor calidad." }),
  L({ id: "qwen3-30b-a3b", name: "Qwen3-MoE 30B A3B", developer: "Qwen", type: "chat", capabilities: ["chat", "tools", "reasoning"], params: "30B", quant: "Q4_K_M", sizeMb: 18000, repo: "Qwen/Qwen3-MoE-30B-A3B-GGUF", file: "qwen3-moe-30b-a3b-q4_k_m.gguf", description: "Mixture-of-Experts: 30B totales, ~3B activos. Potente y eficiente." }),

  // ── Código ──
  L({ id: "qwen2.5-coder-1.5b", name: "Qwen2.5 Coder 1.5B", developer: "Qwen", type: "code", capabilities: ["code", "chat"], params: "1.5B", quant: "Q4_K_M", sizeMb: 1120, repo: "Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF", file: "qwen2.5-coder-1.5b-instruct-q4_k_m.gguf", description: "Asistente de código ligero." }),
  L({ id: "qwen2.5-coder-3b", name: "Qwen2.5 Coder 3B", developer: "Qwen", type: "code", capabilities: ["code", "chat"], params: "3B", quant: "Q4_K_M", sizeMb: 2100, repo: "Qwen/Qwen2.5-Coder-3B-Instruct-GGUF", file: "qwen2.5-coder-3b-instruct-q4_k_m.gguf", description: "Código eficiente en equipos modestos." }),
  L({ id: "qwen2.5-coder-7b", name: "Qwen2.5 Coder 7B", developer: "Qwen", type: "code", capabilities: ["code", "chat", "tools"], params: "7B", quant: "Q4_K_M", sizeMb: 4680, repo: "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", file: "qwen2.5-coder-7b-instruct-q4_k_m.gguf", description: "Referente de código abierto en 7B." }),
  L({ id: "deepseek-coder-6.7b", name: "DeepSeek Coder 6.7B", developer: "DeepSeek", type: "code", capabilities: ["code", "chat"], params: "6.7B", quant: "Q4_K_M", sizeMb: 4000, repo: "TheBloke/deepseek-coder-6.7B-instruct-GGUF", file: "deepseek-coder-6.7b-instruct.Q4_K_M.gguf", description: "Especializado en programación, muy popular." }),
  L({ id: "codegemma-7b", name: "CodeGemma 7B", developer: "Google", type: "code", capabilities: ["code", "chat"], params: "7B", quant: "Q4_K_M", sizeMb: 5000, repo: "bartowski/codegemma-1.1-7b-it-GGUF", file: "codegemma-1.1-7b-it-Q4_K_M.gguf", description: "Gemma afinado para código." }),

  // ── Razonamiento ──
  L({ id: "deepseek-r1-distill-qwen-1.5b", name: "DeepSeek-R1 Distill 1.5B", developer: "DeepSeek", type: "reasoning", capabilities: ["reasoning", "chat"], params: "1.5B", quant: "Q4_K_M", sizeMb: 1120, repo: "bartowski/DeepSeek-R1-Distill-Qwen-1.5B-GGUF", file: "DeepSeek-R1-Distill-Qwen-1.5B-Q4_K_M.gguf", description: "Razonamiento paso a paso en un tamaño minúsculo." }),
  L({ id: "deepseek-r1-distill-qwen-7b", name: "DeepSeek-R1 Distill 7B", developer: "DeepSeek", type: "reasoning", capabilities: ["reasoning", "chat"], params: "7B", quant: "Q4_K_M", sizeMb: 4680, repo: "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF", file: "DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf", description: "Destilado de R1, fuerte en lógica y matemáticas." }),
  L({ id: "deepseek-r1-distill-llama-8b", name: "DeepSeek-R1 Distill 8B", developer: "DeepSeek", type: "reasoning", capabilities: ["reasoning", "chat"], params: "8B", quant: "Q4_K_M", sizeMb: 4920, repo: "bartowski/DeepSeek-R1-Distill-Llama-8B-GGUF", file: "DeepSeek-R1-Distill-Llama-8B-Q4_K_M.gguf", description: "R1 destilado sobre Llama 8B." }),
  L({ id: "qwq-32b", name: "QwQ 32B", developer: "Qwen", type: "reasoning", capabilities: ["reasoning", "chat"], params: "32B", quant: "Q4_K_M", sizeMb: 19000, repo: "bartowski/QwQ-32B-GGUF", file: "QwQ-32B-Q4_K_M.gguf", description: "Modelo de razonamiento profundo de Qwen." }),

  // ── Visión / multimodal ──
  L({ id: "moondream2", name: "Moondream 2", developer: "vikhyatk", type: "vision", capabilities: ["vision", "chat"], params: "1.8B", quant: "Q4_K_M", sizeMb: 1700, needsMmproj: true, repo: "vikhyatk/moondream2", file: "moondream2-text-model-f16.gguf", description: "Visión-lenguaje diminuto. Describe imágenes con poco hardware." }),
  L({ id: "smolvlm-2.2b", name: "SmolVLM 2.2B", developer: "HuggingFace", type: "vision", capabilities: ["vision", "chat"], params: "2.2B", quant: "Q4_K_M", sizeMb: 1600, needsMmproj: true, repo: "ggml-org/SmolVLM2-2.2B-Instruct-GGUF", file: "SmolVLM2-2.2B-Instruct-Q4_K_M.gguf", description: "Visión-lenguaje compacto de HuggingFace." }),
  L({ id: "qwen2-vl-2b", name: "Qwen2-VL 2B", developer: "Qwen", type: "multimodal", capabilities: ["vision", "chat", "tools"], params: "2B", quant: "Q4_K_M", sizeMb: 1900, needsMmproj: true, repo: "bartowski/Qwen2-VL-2B-Instruct-GGUF", file: "Qwen2-VL-2B-Instruct-Q4_K_M.gguf", description: "Multimodal de Qwen: texto + imagen." }),
  L({ id: "qwen2-vl-7b", name: "Qwen2-VL 7B", developer: "Qwen", type: "multimodal", capabilities: ["vision", "chat", "tools"], params: "7B", quant: "Q4_K_M", sizeMb: 5200, needsMmproj: true, repo: "bartowski/Qwen2-VL-7B-Instruct-GGUF", file: "Qwen2-VL-7B-Instruct-Q4_K_M.gguf", description: "Visión-lenguaje potente, entiende imágenes complejas." }),
  L({ id: "llava-1.6-mistral-7b", name: "LLaVA 1.6 Mistral 7B", developer: "LLaVA", type: "multimodal", capabilities: ["vision", "chat"], params: "7B", quant: "Q4_K_M", sizeMb: 4400, needsMmproj: true, repo: "cjpais/llava-1.6-mistral-7b-gguf", file: "llava-v1.6-mistral-7b.Q4_K_M.gguf", description: "Clásico modelo de visión sobre Mistral 7B." }),

  // ── Embeddings ──
  L({ id: "nomic-embed-text", name: "Nomic Embed Text v1.5", developer: "Nomic", type: "embedding", capabilities: ["embedding"], params: "137M", quant: "F16", sizeMb: 280, repo: "nomic-ai/nomic-embed-text-v1.5-GGUF", file: "nomic-embed-text-v1.5.f16.gguf", description: "Embeddings de texto de alta calidad para RAG." }),
  L({ id: "bge-small-en", name: "BGE Small EN v1.5", developer: "BAAI", type: "embedding", capabilities: ["embedding"], params: "33M", quant: "F16", sizeMb: 130, repo: "CompendiumLabs/bge-small-en-v1.5-gguf", file: "bge-small-en-v1.5-f16.gguf", description: "Embeddings pequeños y rápidos." }),
  L({ id: "mxbai-embed-large", name: "mxbai Embed Large v1", developer: "MixedBread", type: "embedding", capabilities: ["embedding"], params: "335M", quant: "F16", sizeMb: 670, repo: "mixedbread-ai/mxbai-embed-large-v1-gguf", file: "mxbai-embed-large-v1-f16.gguf", description: "Embeddings grandes con fuerte recuperación." }),
];
