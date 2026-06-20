# DASA-UI

Desktop GUI for **DASA** (RAG anti-hallucination) + **SHARD** (IVF-PQ vector search
at TB scale). Build "intelligence from datasets" without the terminal: import a
JSON corpus, build a SHARD + IVF-PQ index, and chat grounded over it — answers are
constructed only from retrieved fragments (hallucination-free by design).

> MVP slice 1: **Datasets + grounded RAG chat**. The local inference engine
> (llama.cpp / bitnet.cpp / RWKV with Vulkan, KV-quant, speculative, MoE, BitNet)
> and hardware auto-tuning land in later slices — see Roadmap.

## Architecture

```
Tauri (Rust shell) ──spawns──> Python sidecar (FastAPI)
  · React + Vite + Tailwind          · reuses DASA pipeline + SHARD IVF-PQ
  · manages sidecar lifecycle        · /datasets  /datasets/build (SSE)  /chat
  · hardware detection               · embeddings (MiniLM, CPU)
        │  HTTP 127.0.0.1:<free port>
        └──────────────────────────────────────────►
```

The sidecar imports `dasa` and `shard` from the **sibling repos** `DASA-main` and
`SHARD-main` (must sit next to this folder). No logic is duplicated.

```
2 REPOS DASA AND SHARD/
├── DASA-main/      # RAG pipeline (Agent A retrieval + Agent B synthesis)
├── SHARD-main/     # binary DB + IVF-PQ vector index
└── DASA-UI/        # this app
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

1. **Datasets** — pick a JSON array of records (e.g. `../DASA-main/data/demo_dataset.json`),
   choose a profile (`low-ram` / `medium` / `fast`), build. Progress streams live.
2. **Chat** — select a dataset, ask. The answer plus its source fragments (with
   scores) are shown — the grounding is visible.
3. **Settings** — sidecar status + detected hardware.

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

- **Slice 2 — Inference engine:** managed llama.cpp (Vulkan→iGPU, KV-quant,
  speculative, MoE GGUF) + bitnet.cpp + RWKV; engine toggles in the GUI;
  Agent B LLM-guided synthesis.
- **Slice 3 — Hardware auto-tuning:** detect CPU/RAM/iGPU/GPU → recommend model +
  profile + flags (quality vs efficiency per machine).
- **Slice 4 — Packaging:** Windows installer with embedded Python (PyInstaller
  sidecar `externalBin`); then cross-platform.
- **Slice 5 — OpenAI-compatible API** exposed from the UI.
