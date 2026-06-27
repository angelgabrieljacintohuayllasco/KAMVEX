# KAMVEX

**The desktop app that combines everything:** the ease of Ollama, the control of
LM Studio, the raw flags of llama.cpp, **Vulkan → Vega iGPU** (that Ollama
ignores), and the **deterministic anti-hallucination RAG** of
[DASA](https://github.com/angelgabrieljacintohuayllasco/DASA) +
[SHARD](https://github.com/angelgabrieljacintohuayllasco/SHARD).

| Feature | Ollama | Jan | LM Studio | llama.cpp raw | **KAMVEX** |
|---|---|---|---|---|---|
| MoE GGUF (Qwen3-MoE) | pull | import | yes | yes | **yes** |
| KV cache quant toggle | env var only | sometimes | toggle | flag | **toggle** |
| Speculative decode | no | no | yes | flag | **toggle** |
| Vulkan → Vega iGPU | no (ROCm) | depends | selector | build | **selector** |
| BitNet ternary | no | no | no | needs fork | **v2** |
| RWKV / Mamba | partial | if gguf | if gguf | yes | **v2** |
| Anti-hallucination RAG | no | no | no | no | **yes (DASA)** |
| Dataset → intelligence builder | no | no | no | no | **yes (SHARD)** |
| Hardware auto-tune | no | no | partial | no | **yes** |
| Ease of use | max | medium | medium | min | **max** |

> **Status:** v1 in development. Slice 1 (datasets + grounded RAG chat) is
> functional. The local inference engine, hardware auto-tuning, and quality
> auditing land next — see Roadmap.

## Architecture

```
Tauri (Rust shell)
├── React 19 + Vite + Tailwind    (UI: Chat · Models · Knowledge · Tuning · Settings)
├── Python sidecar (FastAPI)      (DASA pipeline + SHARD builds + Oregano Test)
├── llama-server subprocess       (local inference: CPU + Vulkan, OpenAI-compatible API)
└── hardware detection + auto-tune (CPU/RAM/GPU/VRAM → optimal flags)
```

The sidecar imports `dasa` and `shard` from the **sibling repos** `DASA-main`
and `SHARD-main` (must sit next to this folder). No logic is duplicated.

```
2 REPOS DASA AND SHARD/
├── DASA-main/      # RAG pipeline (Agent A retrieval + Agent B synthesis)
├── SHARD-main/     # binary DB + IVF-PQ vector index
└── KAMVEX/         # this app
```

## Prerequisites

- **Node.js** 18+ and **npm**
- **Rust** stable + the platform toolchain (Windows: MSVC build tools + WebView2)
- **Python** 3.10+ (64-bit) with the DASA/SHARD deps:
  ```bash
  pip install -r ../DASA-main/requirements.txt -r ../SHARD-main/requirements.txt
  pip install -r sidecar/requirements.txt
  ```
  (brings numpy, scikit-learn, sentence-transformers, torch, fastapi, uvicorn)

## Run (dev)

```bash
npm install
npm run tauri dev
```

Tauri picks a free port, launches `sidecar/server.py` on it, waits for `/health`,
then opens the window. Closing the app kills the sidecar.

First run downloads the MiniLM embedding model (~80 MB) on the first build/chat.

## Use

1. **Knowledge** — pick a JSON/JSONL/CSV corpus, choose a profile
   (`low-ram` / `medium` / `fast`), build a SHARD + IVF-PQ index. Progress
   streams live. Run the **Oregano Test** to audit anti-hallucination quality.
2. **Models** — import GGUF files (drag-drop) or pull from HuggingFace. Select
   backend (CPU/Vulkan), toggle KV cache quant, speculative decode, flash
   attention. Auto-tune picks the optimal flags for your hardware.
3. **Chat** — select a dataset (intelligence) + a local model + an Agent B mode:
   - **Statistical** (green, 0 hallucination — vocabulary locked to fragments)
   - **LLM-grounded** (yellow, LLM formats fragments without inventing)
   - **LLM-free** (grey, free chat with your system prompt)
   
   The answer plus its source fragments (with scores) are shown — the grounding
   is visible. Live metrics: tokens/s, VRAM, time-to-first-token.
4. **Tuning** — detected hardware, auto-tune prescription, manual flag override,
   presets (Eco / Balanced / Max).
5. **Settings** — sidecar status, DASA API key, language.

JSON record format (fields auto-detected): `lemma`/`term`/`title`/`name` as key,
`definition`/`text`/`content` as body.

## Tests

```bash
# Sidecar (build demo dataset + chat, offline fake embeddings)
cd sidecar && python -m pytest test_sidecar.py -q

# Rust sidecar manager (spawn -> port ready -> kill)
cd src-tauri && cargo test
```

## Roadmap

### v1 — "exploit llama.cpp + DASA to the max"

- [x] Slice 1: datasets + grounded RAG chat (Tauri + Python sidecar)
- [ ] Bundle `llama-server` (CPU + Vulkan) with auto-download per GPU/ISA
- [ ] Models view: import GGUF, backend selector, KV quant, speculative, flash attn
- [ ] Hardware detection v2 (GPU/Vulkan/VRAM) + auto-tune with override + presets
- [ ] `LlamaCppConnector` + Agent B 3 modes + guarantee indicator
- [ ] Live metrics dashboard (tokens/s, VRAM, TTFT)
- [ ] Knowledge expanded (multi-dataset, JSONL/CSV, auto `num_shards`)
- [ ] Oregano Test runner (anti-hallucination quality audit)
- [ ] Sampler controls + HuggingFace pull (curated list) + quant recommendation

### v2 — "complete the matrix + distribution"

- [ ] `bitnet.cpp` ternary + `rwkv.cpp` / Mamba backends
- [ ] Windows installer with embedded Python (PyInstaller `externalBin`)
- [ ] OpenAI-compatible API exposed from the UI (Kamvex as backend for other apps)
- [ ] Multi-dataset federation + MoE semantic router
- [ ] Model A/B comparison · dataset builder from PDF/web · knowledge graph view
- [ ] Intelligence cards export (.kamvex) · auto-update · system tray · i18n ES/EN

## License

Apache 2.0 (consistent with DASA and SHARD).
