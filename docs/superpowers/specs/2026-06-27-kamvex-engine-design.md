# KAMVEX Engine Design

**Date:** 2026-06-27
**Status:** Approved
**Author:** Design session (brainstorming skill)

## 1. Vision

KAMVEX is a desktop application that combines every important local-LLM capability
into a single UI, plus the deterministic anti-hallucination RAG of DASA and the
TB-scale vector search of SHARD. The goal is to be the only desktop app a user
needs to exploit local AI to the maximum — inference performance, quality
auditing, and intelligence creation from datasets.

### Positioning matrix

| Feature | Ollama | Jan | LM Studio | llama.cpp raw | **KAMVEX** |
|---|---|---|---|---|---|
| MoE GGUF (Qwen3-MoE) | pull | import | yes | yes | **yes** |
| KV cache quant toggle | env var | sometimes | toggle | flag | **toggle** |
| Speculative decode | no | no | yes | flag | **toggle** |
| Vulkan -> Vega iGPU | no (ROCm) | depends | selector | build | **selector** |
| BitNet ternary | no | no | no | needs fork | **v2** |
| RWKV / Mamba | partial | if gguf | if gguf | yes | **v2** |
| Anti-hallucination RAG | no | no | no | no | **yes (DASA)** |
| Dataset -> intelligence builder | no | no | no | no | **yes (SHARD)** |
| Hardware auto-tune | no | no | partial | no | **yes** |
| Ease of use | max | medium | medium | min | **max** |

## 2. Decisions (from brainstorming session)

| Decision | Choice | Rationale |
|---|---|---|
| Inference engine base | Bundle llama.cpp server | Full flag control, Vulkan works on Vega, what LM Studio uses under the hood |
| BitNet / RWKV / Mamba | Phase to v2 | v1 ships llama.cpp features (MoE/Vulkan/KV-quant/speculative); v2 adds ternary + RNN backends |
| Hardware auto-tuning | Recommend + auto-apply with override | Detects hardware, calculates optimal flags, applies on load, user can override each flag |
| GitHub repo | `angelgabrieljacintohuayllasco/KAMVEX`, public | Follows DASA/SHARD convention |
| Agent B with local LLM | 3-mode toggle in UI | Statistical (0 hallucination) / LLM-grounded (format, don't invent) / LLM-free (chat) |

## 3. Architecture

### 3.1 Layer diagram

```
+-----------------------------------------------------------+
|  UI  (React 19 + TS + Tailwind, Tauri 2 webview)          |
|  Chat | Models | Knowledge | Tuning | Settings            |
+--------------+--------------------------+-----------------+
               | Tauri commands           | HTTP/SSE
+--------------v---------+  +-------------v--------------+
|  Rust core (src-tauri)  |  |  Python sidecar (FastAPI)   |
|  - sidecar lifecycle    |  |  - /chat (DASA pipeline)    |
|  - llama-server proc    |  |  - /datasets build (SSE)    |
|  - hardware detect v2   |  |  - DASA Agent A/B + SHARD   |
|  - auto-tune engine     |  |  - LlamaCppConnector        |
+--------------+---------+  +-------------+--------------+
               | spawn/HTTP               | import
+--------------v--------------------------v--------------+
|  Backends (external binaries, not our code):              |
|  - llama-server (CPU + Vulkan)        <-- NEW             |
|  - [v2] bitnet.cpp - rwkv.cpp                            |
+----------------------------------------------------------+
               |
+--------------v------------------------------------------+
|  DASA-main  (RAG anti-hallucination) + SHARD-main (DB)   |
|  siblings on sys.path, no duplicated logic              |
+----------------------------------------------------------+
```

### 3.2 Key principle

KAMVEX never reimplements logic from DASA, SHARD, or llama.cpp. It orchestrates
existing binaries and libraries. The sidecar pattern (already proven in Slice 1)
extends to the llama-server subprocess.

## 4. Local inference engine (llama-server bundle)

### 4.1 What

Package precompiled `llama.cpp` binaries (`llama-server`) for Windows:
- **CPU build** (AVX2 / AVX512 variants)
- **Vulkan build** (works on AMD Vega iGPU, NVIDIA, Intel)

Binaries are downloaded from official llama.cpp GitHub releases on first run,
selected automatically based on detected GPU vendor and CPU ISA. We do not
compile anything in v1.

### 4.2 Lifecycle

The Rust core manages `llama-server` as a subprocess (same pattern as the
existing Python sidecar). Communication via OpenAI-compatible HTTP API on
`http://127.0.0.1:<free-port>`. This mirrors what DASA already does, so the
`LlamaCppConnector` is trivial.

### 4.3 Exposed flags

| Flag | UI control | Auto-tune logic |
|---|---|---|
| `-m model.gguf` | model selector | -- |
| `-ngl N` (GPU layers) | slider 0-999 | based on VRAM vs model size |
| `-t N` (threads) | slider | physical cores |
| `-c N` (context window) | input | based on VRAM/RAM |
| `-b` / `-ub` (batch) | input | based on threads |
| `-ctk q8_0` / `-ctv q8_0` (KV cache quant) | toggle q4/q8/f16 | aggressive on low-VRAM |
| `--draft-model` + `--draft-max` (speculative) | toggle + draft selector | suggest small draft from same family |
| `-fa` (flash attention) | toggle | on if supported |
| `--mlock` / `--no-mmap` | toggles | -- |
| backend (CPU/Vulkan/CUDA) | runtime selector | based on GPU vendor |
| `--main-gpu` / `--tensor-split` (multi-GPU) | advanced (v2) | -- |

### 4.4 Vulkan -> Vega

The Vulkan backend of llama.cpp works on Vega iGPU (Vulkan 1.x). Ollama uses
ROCm which ignores Vega entirely — this is the key differentiator. For APU Vega
(shared VRAM): partial offload + small context + aggressive KV quantization.

### 4.5 MoE GGUF

llama.cpp already supports Mixture-of-Experts GGUF (Qwen3-MoE etc.). No special
handling needed — just load the GGUF file.

### 4.6 Model management

- `models/` directory for GGUF files
- Import via drag-and-drop (like Jan)
- Pull from HuggingFace Hub (direct `.gguf` download from curated list, no
  dependency on Ollama's registry)
- Hub view with searchable curated model list

## 5. Hardware auto-tuning

### 5.1 Hardware detection v2

Extend `hardware.rs` (currently CPU/RAM only):

- **GPU/Vulkan enumeration**: use `wgpu` crate (enumerates Vulkan/DX12/Metal
  adapters, cross-platform) or `ash` (Vulkan pure). Fallback to `vulkaninfo`
  subprocess. Obtains: vendor (AMD/NVIDIA/Intel), approximate VRAM, device name.
- **CUDA detection**: `nvidia-smi` subprocess if present.
- **CPU ISA detection**: detect AVX2/AVX512 to select the correct CPU binary.

### 5.2 Auto-tune heuristics

Produce a "prescription" JSON, auto-applied on model load, overridable in
Settings -> Advanced:

```json
{
  "backend": "vulkan",
  "binary": "llama-server-vulkan-avx2",
  "ngl": 18,
  "threads": 6,
  "ctx": 4096,
  "batch": 512,
  "ctk": "q8_0",
  "ctv": "q8_0",
  "draft_model": null,
  "flash_attn": true
}
```

Rules:
- Model size <= RAM * 0.6
- If VRAM >= model size: `-ngl 999` (full offload)
- If VRAM < model size: partial offload (fit what fits)
- threads = physical cores
- Vega APU: aggressive KV quant + small context
- Presets: **Eco** / **Balanced** / **Max** (mirror SHARD's low-ram/medium/fast)

## 6. DASA Agent B integration (3 modes)

### 6.1 Injection point

DASA already provides: `pipeline.agent_b._llm_callable = <callable>`. We create
`LlamaCppConnector` (analogous to the existing `OllamaConnector`) that points to
the active `llama-server`. It's a callable `(messages) -> str`.

### 6.2 Mode selector in Chat UI

| Mode | Guarantee | Behavior | Indicator |
|---|---|---|---|
| **Statistical** | green, 0 hallucination | `StatisticalRewriter` pure, vocabulary locked, no LLM | green dot |
| **LLM-grounded** | yellow, formats without inventing | LLM formats fragments under strict DASA system prompt | yellow dot |
| **LLM-free** | grey, free chat | LLM responds freely (greetings, general); respects user system prompt | grey dot |

### 6.3 Contract preservation

In LLM-grounded mode, the DASA contract is preserved — the LLM only rewrites
fragments, never introduces new vocabulary. The strict system prompt is injected
by Kamvex (not editable by the user in grounded mode). The Oregano Test (section
8) audits this.

`.dasa_config.json` already has `agent_b_mode` — Kamvex reads/writes it from the
UI.

## 7. Intelligence creation from datasets (Knowledge page)

The Knowledge page already exists (build with SSE progress). Expansions:

- **Multi-dataset gallery**: cards showing "specialized intelligences" (name,
  emoji, stats: records, index size, profile, date). Switch between them in chat.
- **Import formats**: JSON (existing) + JSONL + CSV in v1 (DASA CONTRIBUTING
  invites these adapters). Parquet in v2.
- **Auto `num_shards`**: use `ShardRouter.recommended_shards(...)` instead of
  hardcoding 64. (SHARD's `MMapReader` requires `num_shards` to match the build
  value — Kamvex persists it in `meta.json`.)
- **Oregano Test runner** (see section 8): quality audit per dataset.
- **Embedding model selector** in UI (multilingual-MiniLM vs mini) — already in
  config, expose it.
- **Source fragments** visible per query with score + highlight (partially
  exists, expand).

## 8. Oregano Test (anti-hallucination quality audit)

A test suite that verifies DASA's anti-hallucination guarantee per dataset:

- User defines test queries with expected/forbidden terms
- Runner executes each query through the DASA pipeline
- Checks: do forbidden terms (not in the corpus) appear in the output?
- Produces a confidence score 0-100
- This is a differential feature — no other desktop LLM app audits quality

Example: a recipe dataset entry omits "oregano". If the query "recipe for X"
produces output containing "oregano", the test fails (hallucination detected).

The Oregano Test can also run automatically in CI for regression testing.

## 9. UI views

Sidebar (dark `#0b0f17`, Jan/LM Studio style):

- **Chat** — model selector + dataset/intelligence selector + Agent B mode
  selector (3 buttons) + sampler controls (temp, top-p, top-k, repeat penalty)
  for free mode
- **Models** (replaces Hub placeholder) — installed GGUF models, import/drag-drop,
  pull from HF, backend/runtime selector, KV quant toggle, speculative toggle,
  flash attention, model info, recommended quantization
- **Knowledge** — dataset gallery + expanded import + Oregano Test
- **Tuning** (new, or merged with Settings) — hardware detection, auto-tune
  prescription, advanced flag override, presets (Eco/Balanced/Max)
- **Settings** — sidecar status, DASA API key, language (ES/EN)

## 10. Live metrics dashboard

Real-time inference metrics (like LM Studio):
- Tokens per second (generation speed)
- Time to first token (TTFT)
- VRAM usage (GPU)
- RAM usage (system)
- Context fill percentage

Obtained from `llama-server`'s OpenAI-compatible API response metadata and
system monitoring (sysinfo crate).

## 11. File structure (changes over existing MVP)

```
KAMVEX/
├── src/
│   ├── pages/
│   │   ├── Chat.tsx          (extend: Agent B mode + model select)
│   │   ├── Models.tsx        (NEW, replaces Hub.tsx)
│   │   ├── Knowledge.tsx     (rename Datasets.tsx + expand)
│   │   ├── Tuning.tsx        (NEW)
│   │   └── Settings.tsx
│   ├── components/
│   │   ├── ModeSelector.tsx  (3 Agent B modes)
│   │   ├── MetricsPanel.tsx  (NEW dashboard)
│   │   ├── OreganoTest.tsx   (NEW)
│   │   └── FlagEditor.tsx    (advanced override)
│   └── api/client.ts         (extend: /models, /inference, /tune, /oregano)
├── src-tauri/src/
│   ├── lib.rs                (extend: manage llama-server proc)
│   ├── llama.rs              (NEW: spawn/control llama-server)
│   ├── hardware.rs           (extend: GPU/Vulkan via wgpu)
│   ├── autotune.rs           (NEW: heuristics -> prescription)
│   └── sidecar.rs            (no changes)
├── sidecar/
│   ├── server.py             (extend: /inference, /tune, /oregano, /models)
│   ├── llama_connector.py    (NEW: LlamaCppConnector for DASA Agent B)
│   ├── autotune.py           (NEW: heuristics Python mirror)
│   └── oregano.py            (NEW: anti-hallucination test runner)
├── binarios/                 (NEW, gitignored: downloaded llama-server binaries)
├── models/                   (NEW, gitignored: user GGUF files)
└── docs/superpowers/specs/   (this spec)
```

## 12. Roadmap

### v1 — "exploit llama.cpp + DASA to the max"

1. Bundle `llama-server` (CPU+Vulkan) + auto-download per GPU/ISA
2. Hardware detection v2 (GPU/Vulkan/VRAM) + auto-tune with override + presets
3. Models view real (import GGUF, backend selector, KV quant, speculative, flash attn)
4. `LlamaCppConnector` + Agent B 3 modes + guarantee indicator
5. Metrics dashboard (tokens/s, VRAM, TTFT)
6. Knowledge expanded (multi-dataset, JSONL/CSV, auto num_shards)
7. Oregano Test runner (quality audit)
8. Sampler controls + HuggingFace pull (curated list) + quant recommendation

### v2 — "complete the matrix + distribution"

- `bitnet.cpp` ternary + `rwkv.cpp` / Mamba backends
- Windows installer with embedded Python (PyInstaller `externalBin`)
- OpenAI-compatible API exposed from the UI (Kamvex as backend for other apps)
- Multi-dataset federation + MoE semantic router
- Model A/B comparison
- Dataset builder from PDF/web
- Knowledge graph view
- Intelligence cards export (.kamvex)
- Auto-update
- System tray
- i18n ES/EN

## 13. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Binary size (Vulkan ~100MB) | Download on demand at first run based on detected GPU, don't bundle all variants |
| Vega APU shared VRAM instability | Conservative auto-tune: partial offload + KV q8 + ctx 2048 default, explicit override to increase |
| `llama-server` API changes between releases | Pin a llama.cpp version; tolerant client wrapper |
| DASA contract broken by LLM grounded mode | Oregano Test in CI + strict system prompt injected by Kamvex (not user-editable in grounded mode) |
| Double sidecar (Python + llama-server) complicates lifecycle | Rust core orchestrates both; joint "ready" gate before enabling chat |
| SHARD `num_shards` not auto-discovered by `MMapReader` | Kamvex persists `num_shards` in dataset `meta.json` (already does during build) |
