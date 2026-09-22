# Changelog

All notable changes to KAMVEX. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] — 2026-09-21

### Fixed
- **Installer was unusable outside the dev machine**: the Rust shell resolved the sidecar,
  the llama.cpp binaries and the models through compile-time paths (`CARGO_MANIFEST_DIR`)
  and a `TAURI_RESOURCE_DIR` variable Tauri 2 never sets. Release builds now use the
  per-user app-data folder and find the bundled `kamvex-sidecar.exe` next to the app.
- **Backend selection never reached llama-server**: `llama_start` ignored the chosen backend
  and always spawned the CPU build. The prescription (backend + flags) is now built and
  applied by Rust (`prescription_to_flags`), single source of truth.
- **Chat auto-start always failed**: it passed a bare `-fa`, which llama.cpp b9827 rejects
  (`--flash-attn` requires `on|off|auto`).
- **"Anclado" (grounded) mode could invent**: when the corpus did not cover the question,
  DASA fell back to a free LLM answer. Grounded mode now answers "La información disponible
  no cubre este tema." and never calls the LLM without relevant fragments.
- **RAG dead in the installer**: PyInstaller excludes torch/sentence-transformers, so every
  build/chat failed. Embeddings now run through `llama-server --embedding` with the
  all-MiniLM-L6-v2 GGUF (same model, same 384-dim space) when sentence-transformers is absent.
- **Bundled sidecar reported "DASA/SHARD no disponibles"**: `shard.index.ivfpq_builder` imports
  scikit-learn at module level and the PyInstaller spec excluded it, so the whole DASA import
  failed inside the exe. The builder is now imported lazily (chat works without scikit-learn)
  and scikit-learn ships in the bundle (dataset builds need its k-means).
- **Embedding llama-server outlived the sidecar**: Tauri terminates the sidecar with
  `TerminateProcess`, which skips `atexit`; the embedding server is now assigned to a
  Windows Job Object with `KILL_ON_JOB_CLOSE`, so it dies with the sidecar no matter how
  the sidecar ends (verified by force-killing the process).
- **CUDA backend could not start**: the CUDA runtime DLLs (`cudart-*.zip`) were never downloaded.
- Oregano Test always ran a single generic query (`pipeline.agent_a._cfg` does not exist);
  test cases are now generated from the real records (`keys.json` written at build time).
- `llama_start` did not stop a previous instance; quitting from the tray left the sidecar and
  llama-server running; child processes opened console windows in release builds.
- Model start timed out after 30 s regardless of model size; the shell now waits for the
  model to load (up to 3 min) and reports when the process dies (with the log path).
- GPU VRAM was capped at 4 GB (WMI `AdapterRAM` is 32-bit); the registry
  `HardwareInformation.qwMemorySize` and `nvidia-smi` are used as well.
- `ngl` was computed as a percentage instead of a layer count; auto-tune now reads the real
  layer count / training context from the GGUF metadata.
- A client system prompt sent to `/v1/chat/completions` leaked into later chats.
- `build-installer.py` looked for a onedir output while the spec produced a onefile exe.
- The LLM connector had no `max_tokens` (runaway generations) and no stop tokens.
- Free-mode chat had no memory: the conversation history is now sent to the model.

### Added
- GGUF metadata reader in Rust (`gguf.rs`): architecture, layers, training context,
  quantization, MoE flag; shown in the Models page and used by auto-tune.
- Auto-tune warnings (model larger than 60 % of RAM, integrated GPU, CPU-only, MoE) and
  offloaded/total layer counts.
- Models page: list of downloaded models with *Use* / *Delete*, downloads re-attach after
  navigating away, start stages ("Cargando modelo…"), engine log path.
- Knowledge page: embeddings readiness banner with one-click setup, dataset deletion,
  export through the system browser.
- Conversations persist across restarts (localStorage) and can be deleted.
- Settings → Engine: sidecar launch mode, PID, version, DASA/embeddings availability,
  inference engine status and the folders KAMVEX uses. Settings → Hardware: VRAM,
  integrated/discrete, AVX2/AVX-512, available backends.
- Sidecar endpoints: `DELETE /datasets/{name}`, `DELETE /models/local/{file}`,
  `GET /embeddings/status`, `POST /embeddings/setup`, `GET /models/hub/downloads`,
  richer `/health`; `/chat/free` accepts `history` and `system_prompt`.
- Sidecar receives its directories from the shell (`KAMVEX_DATA_DIR`, `KAMVEX_MODELS_DIR`,
  `KAMVEX_BINARIES_DIR`, `KAMVEX_LLAMA_SERVER`); `KAMVEX_HOME` overrides everything.
- Logs: `logs/sidecar.log` and `logs/llama-server.log`.
- Test suites: 72 sidecar tests (API, modes, security, downloads, Oregano, GGUF embeddings
  with a real llama-server, job-object cleanup) and 34 Rust unit tests.

### Changed
- Sidecar split into modules: `paths.py`, `downloads.py`, `embedding_gguf.py`, `textsource.py`.
- Dataset build reports embedding progress in chunks and stores `keys.json`,
  `records.json` (text/PDF sources) and the embedding backend in `meta.json`.
- Tray menu in Spanish; the window close button hides to the tray, *Salir* quits and kills
  every child process.
- `/models/hub` (a stale duplicate of the TypeScript catalog) was removed.

### Security
- Dataset names and download file names are validated (no path traversal); HuggingFace repo
  ids validated; zip extraction refuses zip-slip entries.
- CORS restricted to the Tauri webview and the Vite dev server (`KAMVEX_CORS_ORIGINS` to
  extend); `/inference/connect` accepts loopback hosts only; request bounds on samplers,
  query length and chunk sizes.

## [0.1.0] — 2026-06-30

Initial public version: Tauri 2 shell + FastAPI sidecar over DASA/SHARD, llama-server
lifecycle with on-demand binaries, hardware detection and auto-tune presets, three Agent B
modes, Oregano Test, metrics dashboard, HuggingFace downloads with pause/resume, federated
router, A/B compare, `.kamvex` export, PDF/text dataset builder, OpenAI-compatible API,
system tray, auto-update, ES/EN i18n and dark/light themes.
