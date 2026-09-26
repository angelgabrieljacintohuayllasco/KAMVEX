# Changelog

All notable changes to KAMVEX. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.4.0] — 2026-09-26

### Added
- **Agent A is an ensemble**. Predictors propose candidates and vote: semantic (MiniLM +
  IVF-PQ), exact key index, **BM25 over the record text** (new) and lexical overlap. Their
  lists merge with weighted Reciprocal Rank Fusion plus an agreement bonus. A record whose
  key the question names in full is *authoritative*: it ranks first regardless.
- **Your own predictors over HTTP**: `KAMVEX_PREDICTORS=name=url,name=url`. One POST with
  `{query, top_k, dataset}`, one reply with `{candidates:[{key,text,score}]}`. A predictor
  that is down or answers nonsense is recorded in the diagnostics and the rest keep voting.
- **Agent B (the LLM) now runs on the corpus experts.** It resolves follow-ups against the
  conversation before retrieving, picks the candidate that answers, and writes the reply.
  `POST /chat` accepts `history`, and the UI sends it.
- **Gemma models**: Gemma 3 1B/4B/12B in the model catalog next to Gemma 2 2B/9B, and as
  options for the Lengua, Leyes, Salud, Perú and General experts. Measured on the real
  stack: Gemma 2 2B answers 4 of 8 turns in its own words with 7 of 8 candidates correctly
  picked, ahead of Qwen2.5 1.5B and Gemma 3 1B.
- `scripts/qa/prove_agent_b.py` replays the conversations that failed against the real
  stack, asking each turn twice (Exact and Grounded); `scripts/qa/app.ps1` builds and
  launches the app with the debug port open.
- `docs/agente-a-y-agente-b.md` describes the two-agent contract end to end.

### Fixed
- **The corpus experts never called the LLM.** Lengua and Leyes defaulted to `statistical`,
  which has no model in the loop, so the answer was the raw record. They now default to
  grounded; Exact stays available as an explicit choice.
- **"explicame que es Pene" answered with *pendiente***: two weak predictors agreeing
  outvoted the exact key hit. Fusion is now weighted and exact hits are authoritative.
- **"dame más explicación" searched for the word *explicación***: follow-ups are rewritten
  against the last topic before retrieval.
- **A small model repeated its previous answer** when the topic changed. The conversation
  only enters the prompt when the question actually needs it.
- **`Además,` injected into legal citations**: DASA's statistical rewriter chains sentences
  with its own connectors. KAMVEX strips them when the sentence without the connector is
  verbatim in the sources, and cites an authoritative record without rewriting it at all.
- **Guardrail fallback dumped a 9 000-character article**; it is now focused on the question,
  and when the user asked for more detail it says the sources record nothing further.
- **BM25 buried the long article that answers the question** ("explícame mis derechos" →
  Artículo 2). The length penalty is capped at twice the average.
- **Stopword keys hijacked retrieval**: "y el artículo 35?" matched the dictionary entry for
  *y* with a perfect score.
- **"Failed to fetch" right after switching model**: llama-server answers 503 while loading
  the GGUF; the connector now waits instead of failing.
- **The app showed "Motor inactivo" with a model loaded and answering**: recent llama.cpp
  builds wrap `next_token` in a list, which crashed `/inference/metrics`.
- **`cargo build --release` produced an app that asked for the dev server**: the
  `custom-protocol` feature was missing from `Cargo.toml`.
- A corpus expert without its corpus fell through to the bare LLM in grounded mode, which is
  exactly the invention the app exists to prevent. It now fails with a clear message; only
  Free mode, chosen by hand, answers without sources.

## [0.3.0] — 2026-09-22

### Added
- **Experts**: domain profiles that tie a corpus, a recommended GGUF, a default mode, a
  system prompt and decoding settings. `GET /experts`, `POST /experts/{id}/chat`, an
  Experts page that installs everything missing in one click, an expert selector in the
  chat top bar and clickable example questions. Included: Programación, Salud, Leyes del
  Perú, Lengua española, Perú and General. Measured on a Ryzen 5 5600GT without GPU:
  12/12 answers for the programming expert against 7/12 with the same corpus and a
  generic prompt, and 3/3 against 1/3 for the bare model on the Peruvian constitution.
- **Ready-made knowledge**: six corpora published as `.kamvex` bundles (shards + IVF-PQ
  index + records) in the `datasets-v1` release — Constitución del Perú (206 artículos),
  MedlinePlus salud (1 014 temas), Wikipedia Perú (2 512 artículos), diccionario español
  (64 643 lemas), documentación de Python en español (5 770 símbolos) and MDN Web Docs en
  español (1 780 páginas). `GET /datasets/catalog` reads the release manifest (bundled
  copy as offline fallback), `POST /datasets/install` downloads, verifies the sha256 and
  unpacks it, `POST /datasets/import` installs a local bundle and
  `POST /datasets/{name}/rebuild` re-embeds from the bundled records.
- `scripts/datasets/`: fetchers for every corpus and `build_kamvex.py` (records → bundle
  + manifest with size and sha256). `scripts/qa/stack.py` brings up the real stack and
  `scripts/qa/ui.mjs` drives the packaged app through WebView2's debugging port.
- `sidecar/bench.py` (hit@1, hit@5, groundedness, fallback rate, latency, Oregano) and
  `sidecar/bench_experts.py` (expert vs. generic prompt vs. bare model); results and
  method in `docs/benchmarks/`.
- Models page: advanced editor for every flag (backend, ngl, threads, ctx, batch, KV
  quant, flash attention, mlock) on top of the automatic prescription.

### Fixed
- **Retrieval missed exact names**: "Artículo 2" retrieved "Artículo 55". A lexical key
  index (n-gram, prefix and 1-edit fuzzy over the dataset's own keys) now pulls the named
  record straight from the SHARD store and merges it in front of the semantic candidates:
  hit@1 went to 100 % on the four measured corpora. Ambiguous names ("Departamento de
  Amazonas" matches Perú, Colombia and the Confederación) are ranked so only the best one
  reaches the grounded context.
- **Grounded mode refused to answer**: a 1.5B model read the strict rule as an easy way
  out and replied "La información disponible no cubre este tema" with the answer in front
  of it. The prompt now carries a worked example, and each fragment is reduced to the
  sentences that actually answer the question — the model stopped missing facts buried in
  2 000 characters and grounded latency halved.
- Documentation records put code examples before the description, and those examples
  repeat the symbol name, so they outranked the prose. Code-looking sentences are demoted.
- `llama-server --embedding` answered HTTP 500 when a request exceeded the physical batch
  (any large corpus): requests are capped by a token budget and split on failure.
- NVIDIA adapters with drivers older than 525 cannot run the CUDA 12 build (below 470 not
  even Vulkan); they are marked unusable and the largest usable adapter wins, so a Radeon
  APU is no longer skipped in favour of a 2012 card. Driver and reason shown in Settings.
- The packaged sidecar could not find its catalogs (PyInstaller extracts data files to
  `sys._MEIPASS`, not next to the source).

### Changed
- Spanish questions are normalized (`¿`, `¡`, `?`, `!`) before retrieval so DASA's
  exact-key boost fires.
- Grounded mode is deterministic by default (greedy + fixed seed) and the lexical
  guardrail can be disabled per request (`guardrail: false`).
- `/chat` returns a `meta` block: engine used, coverage, fallback, unsupported words and
  timings.

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
