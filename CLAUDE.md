# KAMVEX — notes for coding agents

Desktop local-LLM app: Tauri 2 (Rust shell) + React/TS UI + Python FastAPI sidecar that
orchestrates the sibling repos `../DASA-main` (anti-hallucination RAG) and `../SHARD-main`
(binary DB + IVF-PQ). KAMVEX never reimplements DASA/SHARD/llama.cpp logic — it orchestrates.

## Layout
- `src/` React UI. `src/api/client.ts` is the only place that talks to Rust (`invoke`) and the
  sidecar (HTTP/SSE). `src/components/EngineCard.tsx` = model start/stop.
- `src-tauri/src/` Rust: `lib.rs` (commands, lifecycle), `sidecar.rs`, `llama.rs`,
  `hardware.rs`, `autotune.rs`, `gguf.rs`.
- `sidecar/` Python: `server.py` (FastAPI), `paths.py`, `downloads.py`, `embedding_gguf.py`,
  `jobs.py`, `oregano.py`, `textsource.py`, `llama_connector.py`, tests `test_*.py`.
- Data (dev): `sidecar/appdata/datasets`, `sidecar/models`, `binarios/`, `logs/` — all gitignored.
  Release: `%LOCALAPPDATA%\com.kamvex.app\{datasets,models,binarios,logs}`.

## Commands
```bash
npm run build                                   # tsc strict + vite
.venv/Scripts/python -m pytest sidecar -q       # 71 tests (needs ../DASA-main, ../SHARD-main)
cargo check --manifest-path src-tauri/Cargo.toml
cargo test  --manifest-path src-tauri/Cargo.toml --lib
npm run tauri dev                               # needs Rust MSVC + VS Build Tools + WebView2
python scripts/build-installer.py               # PyInstaller sidecar + tauri build
```

## Rules that matter
- Flags for llama-server come from `autotune::prescription_to_flags` (Rust). Do not build
  flag lists in TypeScript. `-fa` needs a value (`--flash-attn on|off`).
- Dataset/file names go through `server.safe_name` / `downloads.is_valid_filename`.
- Agent B modes live in `server._synthesize`; grounded mode must never call the LLM without
  fragments scoring ≥ `GROUNDED_MIN_SCORE`.
- Never use `env!("CARGO_MANIFEST_DIR")` for runtime paths outside `cfg!(debug_assertions)`.
- Child processes: `CREATE_NO_WINDOW` on Windows, logs under `logs/`, killed on `RunEvent::Exit`.
- Embeddings: sentence-transformers if installed, else `LlamaEmbeddingEngine` (llama-server
  `--embedding` + `models/embeddings/all-MiniLM-L6-v2.F16.gguf`). Same 384-dim space.
- TS is strict (`noUnusedLocals`, `noUnusedParameters`). i18n keys in `src/i18n.tsx` (ES/EN).
