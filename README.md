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
| BitNet ternary | no | no | no | needs fork | planned |
| RWKV / Mamba | partial | if gguf | if gguf | yes | planned |
| Anti-hallucination RAG | no | no | no | no | **yes (DASA)** |
| Dataset → intelligence builder | no | no | no | no | **yes (SHARD)** |
| Ready-made corpora (one click, pre-indexed) | no | no | no | no | **yes** |
| Domain experts (corpus + model + prompt) | no | no | no | no | **yes** |
| Hardware auto-tune (layer-aware) | no | no | partial | no | **yes** |
| Quality audit (Oregano Test) | no | no | no | no | **yes** |
| Ease of use | max | medium | medium | min | **max** |

## Expertos: hacer al modelo bueno en un área

Un modelo de 1,5B no sabe qué dice el Artículo 2 de la Constitución peruana ni qué
parámetros acepta `functools.lru_cache`. Un **experto** de KAMVEX ata las cuatro cosas
que sí lo hacen preciso en ese dominio, y las instala con un botón:

| | |
|---|---|
| **corpus** | los datasets del área, ya convertidos en shards + índice |
| **modelo** | el GGUF que rinde mejor ahí (código → Qwen2.5-Coder) |
| **modo** | Exacto para normas y definiciones, Anclado para explicar |
| **prompt + decodificación** | instrucciones del dominio, temperatura 0 y semilla fija |

Expertos incluidos: **Programación** (documentación de Python y MDN en español),
**Salud** (MedlinePlus), **Leyes del Perú** (Constitución), **Lengua española**
(64 643 lemas), **Perú** (Wikipedia) y **General** (sin corpus).

Medido en un Ryzen 5 5600GT sin GPU ([benchmarks](docs/benchmarks/)):

| experto | con el experto | mismo corpus, prompt genérico | el modelo solo |
|---|---|---|---|
| Programación (Coder-3B) | **12/12** | 7/12 | 12/12 |
| Leyes del Perú | **3/3** | 3/3 | 1/3 |
| Perú (cultura) | **3/3** | 3/3 | 2/3 |
| Lengua española | **2/2** | 2/2 | 1/2 |

Recuperación: **hit@1 del 100 %** en los cuatro corpus medidos y **Oregano 100/100**
(cero alucinaciones). Modo Exacto responde en 26-80 ms; Anclado, entre 1,2 y 3,2 s en CPU.

> **Status: v0.2.0.** Every v1/v2 feature is implemented; 0.2.0 is the hardening release
> (release paths, backend wiring, real grounded mode, embeddings without torch, process
> lifecycle, validation). See [CHANGELOG.md](CHANGELOG.md).

## Architecture

```
Tauri 2 (Rust shell, src-tauri/)
├── React 19 + Vite + Tailwind 4   UI: Chat · Knowledge · Models · Compare · Settings
├── Python sidecar (FastAPI)       DASA pipeline · SHARD builds · Oregano Test · downloads
├── llama-server subprocess        local inference (CPU / Vulkan / CUDA), OpenAI-compatible
├── llama-server --embedding       384-dim MiniLM embeddings when sentence-transformers is absent
└── hardware detection + auto-tune CPU / RAM / GPU / VRAM + GGUF metadata → llama-server flags
```

The sidecar imports `dasa` and `shard` from the **sibling repos** `DASA-main` and
`SHARD-main` (dev) or from the PyInstaller bundle (installer). No logic is duplicated.

```
2 REPOS DASA AND SHARD/
├── DASA-main/      # RAG pipeline (Agent A retrieval + Agent B synthesis)
├── SHARD-main/     # binary DB + IVF-PQ vector index
└── KAMVEX/         # this app
```

### Where data lives

| | Dev (`npm run tauri dev`) | Installed app |
|---|---|---|
| Datasets | `sidecar/appdata/datasets/` | `%LOCALAPPDATA%\com.kamvex.app\datasets\` |
| GGUF models | `sidecar/models/` | `…\com.kamvex.app\models\` |
| llama.cpp binaries | `binarios/<backend>/` | `…\com.kamvex.app\binarios\<backend>\` |
| Logs | `logs/` | `…\com.kamvex.app\logs\` (`sidecar.log`, `llama-server.log`) |

Set `KAMVEX_HOME=<folder>` to put everything under one folder in both modes.

## Prerequisites

- **Node.js** 18+ and **npm**
- **Rust** stable (MSVC toolchain) + Visual Studio Build Tools (C++ workload) + WebView2
- **Python** 3.10+ (64-bit). Recommended: a venv in the repo (`python -m venv .venv`).
  ```bash
  pip install -r sidecar/requirements.txt -r sidecar/requirements-dev.txt
  pip install -r ../DASA-main/requirements.txt -r ../SHARD-main/requirements.txt
  ```
  `sentence-transformers` (torch) is **optional**: without it KAMVEX serves embeddings
  through `llama-server --embedding` with the all-MiniLM-L6-v2 GGUF (downloaded once from
  the Knowledge page, ~45 MB). Datasets built either way are compatible.

## Run (dev)

```bash
npm install
npm run tauri dev
```

The shell picks a free port, launches `sidecar/server.py` with the directories above as
environment variables, waits for `/health` and opens the window. Closing the window hides
the app to the tray; **Salir** in the tray quits and kills the sidecar and llama-server.

## Use

0. **Expertos** — pick a field, press *Instalar lo que falta* and KAMVEX downloads its
   corpus (already indexed) and its recommended model. From then on the chat answers from
   that corpus with the mode, prompt and decoding of that expert. The example questions on
   each card open the chat with the question already typed.
1. **Knowledge** — *Conocimiento listo para usar* lists the pre-built corpora: one click
   downloads a `.kamvex` bundle, verifies its sha256 and installs it — no embedding work
   on your machine. You can also import a `.kamvex` file, or build your own: pick a
   JSON/JSONL/CSV, paste text or import a PDF, choose a profile (`low-ram` / `medium` /
   `fast`) and build (needs the embedding engine: the banner installs it once). Progress
   streams live. Run the **Oregano Test** to audit anti-hallucination quality; *Gestionar*
   shows details, rebuild, export (`.kamvex`) and deletion.
2. **Models** — download a GGUF from the catalog (pause / resume / cancel) or import one.
   The engine card reads the GGUF metadata (architecture, layers, trained context,
   quantization), auto-tunes flags for your hardware (Eco / Balanceado / Máx), shows
   warnings, lets you add a draft model for speculative decoding and starts llama-server.
3. **Chat** — select knowledge (or *Auto* for the federated router), a model and a mode:
   - **Exacto** (green): StatisticalRewriter, no LLM, zero hallucination.
   - **Anclado** (amber): the LLM formats the retrieved fragments under DASA's strict
     prompt; if the corpus does not cover the question it says so — it never free-talks.
   - **Libre** (grey): general chat with memory; uses the corpus when it is relevant.
   The engine auto-starts when a mode needs it. Source fragments and scores are shown;
   live metrics: tokens/s, TTFT, context, RAM, VRAM.
4. **Compare** — same query, two modes, side by side.
5. **Settings** — language, theme, updates, hardware (VRAM, integrated/discrete, AVX),
   engine status (sidecar launch mode, PID, logs, folders).

JSON record format (fields auto-detected): `lemma`/`term`/`title`/`name` as key,
`definition`/`text`/`content` as body.

### KAMVEX as an OpenAI-compatible backend

Other apps (Jan, Open WebUI, scripts) can use a dataset as a "model":

```bash
curl http://127.0.0.1:<sidecar-port>/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"my-dataset","messages":[{"role":"user","content":"¿Qué es X?"}]}'
```

The sidecar port is shown in *Settings → Motor*. With an inference engine running the
answer uses the LLM (grounded when the corpus is relevant); otherwise it is statistical.

## Configuration (environment variables)

| Variable | Purpose |
|---|---|
| `KAMVEX_HOME` | Root folder for datasets/models/binaries/logs (shell + sidecar) |
| `KAMVEX_DATA_DIR`, `KAMVEX_MODELS_DIR`, `KAMVEX_BINARIES_DIR` | Individual folders (set by the shell) |
| `KAMVEX_LLAMA_SERVER` | llama-server binary used for embeddings |
| `KAMVEX_EMBED_BACKEND` | `auto` (default) · `st` (sentence-transformers) · `gguf` |
| `KAMVEX_EMBED_MODEL` | Path to the embedding GGUF |
| `KAMVEX_DATASET_CATALOG_URL` | Dataset catalog manifest (`off` to use the bundled copy) |
| `KAMVEX_ALLOWED_HOSTS` | Extra hosts allowed for downloads (default: github.com, huggingface.co) |
| `KAMVEX_CORS_ORIGINS` | Extra browser origins allowed to call the sidecar |
| `KAMVEX_PYTHON` | Interpreter for `sidecar/server.py` in dev (default `python`) |
| `KAMVEX_SIDECAR_BIN` / `KAMVEX_USE_SIDECAR_BIN=1` | Force a sidecar executable |
| `HF_TOKEN` | HuggingFace token for gated repos |

## Tests

```bash
# Sidecar: API, modes, experts, key index, grounding, validation, downloads, Oregano
python -m pytest sidecar -q            # 104 tests; the real-llama-server ones skip if
                                       # binarios/cpu/llama-server.exe or the MiniLM GGUF are absent
# Rust: auto-tune, GGUF parser, hardware parsing, llama lifecycle, sidecar resolution
cargo test --manifest-path src-tauri/Cargo.toml --lib     # 39 tests
cargo test --manifest-path src-tauri/Cargo.toml --lib -- --ignored   # spawns the real sidecar
# Frontend
npm run build                          # tsc strict + vite
```

## Build the installer

```bash
pip install -r sidecar/requirements-dev.txt
python scripts/build-installer.py      # --sidecar-only / --skip-sidecar
# Output: src-tauri/target/release/bundle/nsis/KAMVEX_0.2.0_x64-setup.exe
#         src-tauri/target/release/bundle/msi/KAMVEX_0.2.0_x64_en-US.msi
```

`bundle.createUpdaterArtifacts` is enabled, so `tauri build` needs
`TAURI_SIGNING_PRIVATE_KEY` (and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`). Auto-update reads
`latest.json` from the GitHub release. The sidecar exe (~60 MB) bundles DASA + SHARD +
numpy + scikit-learn but **not** torch; embeddings run through llama-server (see
Prerequisites). Smoke-test it without Tauri:
`sidecar/dist/kamvex-sidecar.exe --port 8765` then `curl http://127.0.0.1:8765/health`.

## Troubleshooting

- **"No se pudo iniciar KAMVEX"** — the sidecar did not start. Check `logs/sidecar.log`
  (dev) or `%LOCALAPPDATA%\com.kamvex.app\logs\sidecar.log`; in dev make sure the venv
  Python is on `PATH` or set `KAMVEX_PYTHON`.
- **The engine does not start** — the error names `logs/llama-server.log`; typical causes:
  model too big for RAM/VRAM (see the auto-tune warnings), Vulkan driver missing (the
  prescription falls back to CPU), CUDA build without the NVIDIA driver.
- **"Motor de embeddings no listo"** — click *Preparar embeddings* in Knowledge, or install
  `sentence-transformers` in the dev venv.

## Add your own dataset or expert

A dataset is a JSON array of records; `title`/`lemma`/`name` is the key and
`content`/`definition`/`text` the body. To publish one as a ready-made bundle:

```bash
python scripts/datasets/build_kamvex.py datasets-src/mi-dataset.json --profile low-ram
# → datasets-out/mi-dataset.kamvex + an entry in manifest.json (size + sha256)
```

Upload the bundle and `manifest.json` to a GitHub release and point
`KAMVEX_DATASET_CATALOG_URL` at that manifest: the catalog in the app picks it up.
`scripts/datasets/fetch_*.py` are the fetchers used for the bundled corpora.

An expert is one object in `sidecar/experts_catalog.json`: its datasets, its recommended
models, its default mode, its system prompt and its samplers. No code changes needed.

## Roadmap

- `bitnet.cpp` ternary and `rwkv.cpp` backends (enums and download slots exist; no official
  Windows binaries yet).
- Token streaming in the chat, mmproj (vision) wiring, knowledge-graph view.
- Production CSP for the webview (policy drafted; needs a runtime check on a packaged build).
- Publishing the bundles on Hugging Face as well (today they live in a GitHub release).

## License

Apache 2.0 (consistent with DASA and SHARD).
