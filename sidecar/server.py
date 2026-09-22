"""
KAMVEX sidecar — thin FastAPI server launched by the Tauri shell.

Reuses DASA (pipeline, embeddings) and SHARD (storage, IVF-PQ builder) without
rewriting any logic. Exposes dataset build + grounded chat over localhost and
an OpenAI-compatible API so other apps can use KAMVEX as a backend.

Run:  python server.py --port 8765 [--data <dir>] [--models <dir>]
Env:  see paths.py (KAMVEX_DATA_DIR, KAMVEX_MODELS_DIR, KAMVEX_BINARIES_DIR, ...)
      KAMVEX_CORS_ORIGINS   comma-separated allowed browser origins
      KAMVEX_EMBED_BACKEND  auto | st | gguf   (embedding engine selection)
      KAMVEX_EMBED_MODEL    path to an embedding GGUF (default: models/embeddings/...)
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import os
import queue
import re
import shutil
import sys
import threading
import time
import uuid
from pathlib import Path

import paths

# ── Resolve sibling DASA-main / SHARD-main onto sys.path (dev layout) ────────
_SIBLINGS = paths.siblings_dir()
if _SIBLINGS is not None:
    for _sib, _pkg in (("DASA-main", "dasa"), ("SHARD-main", "shard")):
        _p = _SIBLINGS / _sib
        if (_p / _pkg).is_dir() and str(_p) not in sys.path:
            sys.path.insert(0, str(_p))

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

# ── DASA / SHARD imports (may be unavailable in a stripped bundle) ──────────
_DASA_AVAILABLE = False
try:
    from dasa.config import DASAConfig
    from dasa.pipeline import DASAPipeline
    from dasa.agent_a.embeddings import EmbeddingEngine
    from shard.storage.shard_writer import ShardWriter
    from shard.index.ivfpq_builder import build_ivfpq
    _DASA_AVAILABLE = True
except ImportError:
    pass

from downloads import DownloadManager, is_valid_filename, is_valid_hf_repo  # noqa: E402
from embedding_gguf import LlamaEmbeddingEngine  # noqa: E402
from embedding_gguf import DEFAULT_FILE as EMBED_FILE, DEFAULT_REPO as EMBED_REPO  # noqa: E402
from jobs import BuildJob, run_build  # noqa: E402
from llama_connector import LlamaCppConnector  # noqa: E402
from oregano import run_oregano_test  # noqa: E402
from textsource import records_from_pdf, records_from_text  # noqa: E402

VERSION = "0.2.0"
NUM_SHARDS = 64
PROFILES = ("low-ram", "medium", "fast")
MODES = ("statistical", "grounded", "free")
# Mirrors DASA's SynthesisEngine._RELEVANCE_THRESHOLD: below it the corpus does
# not cover the question. Grounded mode must then say so instead of inventing.
GROUNDED_MIN_SCORE = 0.40
NO_INFO = "No se encontró información relevante en el corpus para esta consulta."
NOT_COVERED = "La información disponible no cubre este tema."
DEFAULT_FREE_SYSTEM_PROMPT = "Eres KAMVEX, un asistente local. Responde de forma natural, útil y concisa."
SOURCE_FILES = ("json", "jsonl", "csv")

DATA_DIR: Path = paths.data_dir()
MODELS_DIR: Path = paths.models_dir()

DEFAULT_CORS_ORIGINS = [
    "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
    "http://localhost:1420", "http://127.0.0.1:1420",
]


def _cors_origins() -> list[str]:
    raw = os.environ.get("KAMVEX_CORS_ORIGINS", "").strip()
    if not raw:
        return DEFAULT_CORS_ORIGINS
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(title="KAMVEX sidecar", version=VERSION)
# Browser origins only: the Tauri webview and the Vite dev server. Server-to-server
# clients of the OpenAI-compatible API (Jan, Open WebUI, curl) are not subject to CORS.
app.add_middleware(
    CORSMiddleware, allow_origins=_cors_origins(), allow_methods=["*"], allow_headers=["*"],
)

_JOBS: dict[str, BuildJob] = {}
_PIPELINES: dict = {}
_PIPE_LOCK = threading.Lock()      # pipelines share Agent B state (mode + callable)
_EMBED_LOCK = threading.Lock()
_embedding_engine = None
_LLAMA_CONNECTOR: LlamaCppConnector | None = None
_DOWNLOADS = DownloadManager()

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$")


# ── Validation helpers ──────────────────────────────────────────────────────

def safe_name(name: str) -> str:
    """A dataset name must be a single, sane path component."""
    name = (name or "").strip()
    if not _NAME_RE.match(name) or ".." in name or name.endswith("."):
        raise HTTPException(
            400, "nombre inválido: usa letras, números, espacios, '.', '_' o '-' (máx. 64)")
    return name


def _dataset_dir(name: str) -> Path:
    return DATA_DIR / safe_name(name)


def _require_dataset(name: str) -> tuple[Path, dict]:
    db = _dataset_dir(name)
    meta_path = db / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, f"dataset desconocido: {name}")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(500, f"meta.json corrupto en {name}: {e}") from e
    return db, meta


def _require_dasa() -> None:
    if not _DASA_AVAILABLE:
        raise HTTPException(
            503,
            "DASA/SHARD no disponibles en este sidecar. Ejecuta KAMVEX en modo desarrollo "
            "(Python + repos hermanos) o reinstala la aplicación.",
        )


def _require_profile(profile: str) -> str:
    if profile not in PROFILES:
        raise HTTPException(400, f"perfil inválido: {profile} (usa {', '.join(PROFILES)})")
    return profile


def _require_connector() -> LlamaCppConnector:
    if _LLAMA_CONNECTOR is None:
        raise HTTPException(400, "No hay motor de inferencia activo. Inicia un modelo en Modelos.")
    return _LLAMA_CONNECTOR


# ── Embedding engine (sentence-transformers or llama-server GGUF) ───────────

def _st_available() -> bool:
    return importlib.util.find_spec("sentence_transformers") is not None


def _embed_backend_pref() -> str:
    return os.environ.get("KAMVEX_EMBED_BACKEND", "auto").strip().lower() or "auto"


def _embed_model_path() -> Path:
    explicit = os.environ.get("KAMVEX_EMBED_MODEL", "").strip()
    if explicit:
        return Path(explicit).expanduser()
    return MODELS_DIR / "embeddings" / EMBED_FILE


def _get_embedding_engine():
    """Lazily create the shared embedding engine (heavy: loads the model once)."""
    global _embedding_engine
    with _EMBED_LOCK:
        if _embedding_engine is not None:
            return _embedding_engine
        pref = _embed_backend_pref()
        if pref in ("auto", "st") and _DASA_AVAILABLE and _st_available():
            _embedding_engine = EmbeddingEngine(DASAConfig())
            return _embedding_engine
        if pref in ("auto", "gguf"):
            server_bin = paths.llama_server_binary()
            model = _embed_model_path()
            if server_bin is not None and model.is_file():
                _embedding_engine = LlamaEmbeddingEngine(server_bin, model)
                return _embedding_engine
            missing = []
            if server_bin is None:
                missing.append("el motor llama-server (descárgalo en Modelos)")
            if not model.is_file():
                missing.append("el modelo de embeddings (Conocimiento → Preparar embeddings)")
            raise HTTPException(503, "Motor de embeddings no disponible: falta " + " y ".join(missing) + ".")
        raise HTTPException(503, "sentence-transformers no está instalado y KAMVEX_EMBED_BACKEND=st.")


def _embeddings_status() -> dict:
    engine = _embedding_engine
    server_bin = paths.llama_server_binary()
    model = _embed_model_path()
    st = _DASA_AVAILABLE and _st_available()
    pref = _embed_backend_pref()
    if engine is not None:
        backend = "llama-gguf" if isinstance(engine, LlamaEmbeddingEngine) else "sentence-transformers"
    elif pref in ("auto", "st") and st:
        backend = "sentence-transformers"
    elif pref in ("auto", "gguf") and server_bin is not None and model.is_file():
        backend = "llama-gguf"
    else:
        backend = "none"
    info = {
        "backend": backend,
        "ready": backend != "none",
        "st_installed": bool(st),
        "server_bin": str(server_bin) if server_bin else None,
        "model_path": str(model),
        "model_present": model.is_file(),
        "model_repo": EMBED_REPO,
        "model_file": EMBED_FILE,
        "running": False,
        "port": None,
    }
    if isinstance(engine, LlamaEmbeddingEngine):
        info.update({"running": engine.running, "port": engine.port, "dim": engine.dim})
    return info


# ── Pipelines ───────────────────────────────────────────────────────────────

def _new_pipeline(db: Path, meta: dict):
    cfg = DASAConfig(use_shard_backend=True, shard_db_path=str(db),
                     shard_num_shards=int(meta.get("num_shards", NUM_SHARDS)))
    pipe = DASAPipeline(cfg)
    # One shared engine for every dataset (ST loads MiniLM once; GGUF = one process).
    pipe.agent_a.embedding_engine = _get_embedding_engine()
    pipe.load(str(db))
    return pipe


def _load_pipeline(dataset_name: str):
    """Load and cache a pipeline for a dataset."""
    _require_dasa()
    db, meta = _require_dataset(dataset_name)
    pipe = _PIPELINES.get(db.name)
    if pipe is None:
        pipe = _new_pipeline(db, meta)
        _PIPELINES[db.name] = pipe
    return pipe


def _close_pipeline(name: str) -> None:
    pipe = _PIPELINES.pop(name, None)
    if pipe is None:
        return
    for attr in ("_shard_reader", "_ivf", "_shard_index"):
        obj = getattr(pipe.agent_a, attr, None)
        close = getattr(obj, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001 — best effort
                pass
    gc.collect()


# ── Request models ──────────────────────────────────────────────────────────

class SamplerFields(BaseModel):
    temperature: float = Field(0.1, ge=0.0, le=2.0)
    top_p: float = Field(0.95, ge=0.0, le=1.0)
    top_k: int = Field(40, ge=1, le=1000)
    repeat_penalty: float = Field(1.0, ge=0.5, le=3.0)
    max_tokens: int = Field(512, ge=16, le=8192)


class BuildReq(BaseModel):
    name: str
    json_path: str
    profile: str = "low-ram"


class BuildTextReq(BaseModel):
    name: str
    text: str = ""
    pdf_path: str = ""
    chunk_size: int = Field(500, ge=100, le=5000)
    profile: str = "low-ram"


class ChatReq(SamplerFields):
    dataset: str
    query: str = Field(..., min_length=1, max_length=20000)
    agent_b_mode: str = "statistical"


class FederatedReq(SamplerFields):
    query: str = Field(..., min_length=1, max_length=20000)
    agent_b_mode: str = "statistical"


class ChatMessage(BaseModel):
    role: str
    content: str


class FreeChatReq(SamplerFields):
    query: str = Field(..., min_length=1, max_length=20000)
    system_prompt: str = Field("", max_length=8000)
    history: list[ChatMessage] = Field(default_factory=list)


class CompareReq(SamplerFields):
    dataset: str
    query: str = Field(..., min_length=1, max_length=20000)
    mode_a: str = "statistical"
    mode_b: str = "grounded"


class InferenceConnectReq(BaseModel):
    host: str = "127.0.0.1"
    port: int = Field(..., ge=1, le=65535)
    model: str = "local"


class HubDownloadReq(BaseModel):
    repo: str
    file: str


# ── Synthesis (single place where Agent B modes are applied) ────────────────

def _fragments_json(fragments) -> list[dict]:
    return [{"text": f.text, "score": float(f.score), "source_id": f.source_id} for f in fragments]


def _synthesize(pipe, mode: str, query: str, fragments, s: SamplerFields,
                free_system_prompt: str | None = None) -> str:
    """Run Agent B in the requested mode.

    statistical — StatisticalRewriter only, no LLM (0 hallucination).
    grounded    — LLM formats relevant fragments under DASA's strict prompt; if the
                  corpus does not cover the question it says so (never free-talks).
    free        — LLM answers from the corpus when relevant, freely otherwise.
    """
    if mode not in MODES:
        raise HTTPException(400, f"modo agent_b inválido: {mode}")

    with _PIPE_LOCK:
        agent_b = pipe.agent_b
        if mode == "statistical":
            agent_b._llm_callable = None
            return (agent_b.synthesize(query, fragments) or "").strip() or NO_INFO

        connector = _require_connector()
        connector.set_samplers(s.temperature, s.top_p, s.top_k, s.repeat_penalty, s.max_tokens)
        agent_b._llm_callable = connector

        if mode == "grounded":
            relevant = [f for f in fragments if f.score >= GROUNDED_MIN_SCORE]
            if not relevant:
                return NOT_COVERED
            guided = getattr(agent_b, "_llm_guided_synthesis", None)
            if guided is None:
                return (agent_b.synthesize(query, relevant) or "").strip() or NOT_COVERED
            return (guided(query, relevant) or "").strip() or NOT_COVERED

        original_prompt = getattr(agent_b, "_free_system_prompt", None)
        try:
            if free_system_prompt and original_prompt is not None:
                agent_b._free_system_prompt = free_system_prompt
            return (agent_b.synthesize(query, fragments) or "").strip() or NO_INFO
        finally:
            if original_prompt is not None:
                agent_b._free_system_prompt = original_prompt


# ── Health / status ─────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": VERSION,
        "dasa": _DASA_AVAILABLE,
        "embeddings": _embeddings_status()["backend"],
        "data_dir": str(DATA_DIR),
        "models_dir": str(MODELS_DIR),
    }


@app.get("/embeddings/status")
def embeddings_status():
    return _embeddings_status()


@app.post("/embeddings/setup")
def embeddings_setup():
    """Download the embedding GGUF (only needed when sentence-transformers is absent)."""
    dest = _embed_model_path()
    if dest.is_file():
        return {"status": "already", "path": str(dest)}
    dest.parent.mkdir(parents=True, exist_ok=True)
    state = _DOWNLOADS.start(EMBED_REPO, EMBED_FILE, dest)
    return {"status": "started", "download_id": state.id}


@app.post("/embeddings/stop")
def embeddings_stop():
    global _embedding_engine
    with _EMBED_LOCK:
        engine, _embedding_engine = _embedding_engine, None
    if isinstance(engine, LlamaEmbeddingEngine):
        engine.stop()
    with _PIPE_LOCK:
        for name in list(_PIPELINES):
            _close_pipeline(name)
    return {"status": "stopped"}


# ── Datasets ────────────────────────────────────────────────────────────────

@app.get("/datasets")
def list_datasets():
    out = []
    if not DATA_DIR.exists():
        return out
    for d in sorted(DATA_DIR.iterdir()):
        meta = d / "meta.json"
        if d.is_dir() and meta.exists():
            try:
                out.append(json.loads(meta.read_text(encoding="utf-8")) | {"path": str(d)})
            except json.JSONDecodeError:
                continue
    return out


def _start_build(name: str, json_path: Path, profile: str, extra_meta: dict | None = None) -> str:
    job = BuildJob()
    jid = uuid.uuid4().hex
    _JOBS[jid] = job
    with _PIPE_LOCK:
        _close_pipeline(name)   # invalidate any cached pipeline for this name
    engine = _get_embedding_engine()
    threading.Thread(
        target=run_build, args=(job,),
        kwargs=dict(name=name, json_path=str(json_path), profile=profile,
                    data_dir=DATA_DIR, num_shards=None,
                    embedding_engine=engine,
                    shard_writer_cls=ShardWriter, build_ivfpq_fn=build_ivfpq,
                    extra_meta=extra_meta),
        daemon=True, name=f"build-{name}",
    ).start()
    return jid


@app.post("/datasets/build")
def build_dataset(req: BuildReq):
    _require_dasa()
    name = safe_name(req.name)
    _require_profile(req.profile)
    src = Path(req.json_path)
    if not src.is_file():
        raise HTTPException(404, f"Archivo no encontrado: {req.json_path}")
    if src.suffix.lower().lstrip(".") not in SOURCE_FILES:
        raise HTTPException(400, "formato no soportado: usa .json, .jsonl o .csv")
    return {"job_id": _start_build(name, src, req.profile)}


@app.post("/datasets/build-text")
def build_from_text(req: BuildTextReq):
    """Build a dataset from raw text or a PDF by chunking it into records."""
    _require_dasa()
    name = safe_name(req.name)
    _require_profile(req.profile)

    try:
        if req.pdf_path:
            full_text, records, extra_meta = records_from_pdf(req.pdf_path, req.chunk_size)
        else:
            full_text, records, extra_meta = records_from_text(req.text, req.chunk_size)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e)) from e
    if not full_text or not records:
        raise HTTPException(400, "texto vacío o PDF sin texto extraíble")

    db = DATA_DIR / name
    db.mkdir(parents=True, exist_ok=True)
    (db / "fulltext.txt").write_text(full_text, encoding="utf-8")
    source = db / "records.json"
    source.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    return {"job_id": _start_build(name, source, req.profile, extra_meta), "n_chunks": len(records)}


@app.get("/datasets/build/{job_id}/events")
def build_events(job_id: str):
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "job desconocido")

    def gen():
        while True:
            try:
                ev = job.q.get(timeout=30)
            except queue.Empty:
                if job.done:
                    break
                continue
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if ev["stage"] in ("done", "error"):
                break

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.delete("/datasets/{name}")
def delete_dataset(name: str):
    db, _ = _require_dataset(name)
    with _PIPE_LOCK:
        _close_pipeline(db.name)
    try:
        shutil.rmtree(db)
    except PermissionError as e:
        raise HTTPException(409, "dataset en uso; reinicia KAMVEX y vuelve a intentarlo") from e
    return {"status": "deleted", "name": db.name}


@app.post("/datasets/{name}/summary")
def dataset_summary(name: str):
    """Summarize a dataset's source document using the active inference engine.

    Grounded by construction: the prompt only contains the dataset's own
    extracted text, so the model cannot introduce facts from elsewhere.
    """
    connector = _require_connector()
    db, _ = _require_dataset(name)
    fulltext_path = db / "fulltext.txt"
    if not fulltext_path.exists():
        raise HTTPException(404, "Este dataset no tiene texto fuente disponible para resumir.")

    text = fulltext_path.read_text(encoding="utf-8")[:8000]
    messages = [
        {"role": "system", "content": (
            "Resume el documento del usuario de forma fiel y concisa, en español. "
            "No inventes información que no esté presente en el texto.")},
        {"role": "user", "content": text},
    ]
    with _PIPE_LOCK:
        summary = connector(messages)
    return {"summary": summary}


@app.get("/datasets/{name}/export")
def export_dataset(name: str):
    """Export a dataset as a .kamvex file (portable zip of shards + index + meta)."""
    import io
    import zipfile
    db, _ = _require_dataset(name)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in db.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(db).as_posix())
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{db.name}.kamvex"'},
    )


# ── Chat ────────────────────────────────────────────────────────────────────

@app.post("/chat")
def chat(req: ChatReq):
    pipe = _load_pipeline(req.dataset)
    fragments = pipe.agent_a.search(req.query)
    answer = _synthesize(pipe, req.agent_b_mode, req.query, fragments, req)
    return {
        "answer": answer,
        "fragments": _fragments_json(fragments),
        "mode": req.agent_b_mode,
        "dataset": safe_name(req.dataset),
    }


@app.post("/chat/free")
def chat_free(req: FreeChatReq):
    """Direct LLM chat — no dataset or DASA pipeline required. Keeps the conversation."""
    connector = _require_connector()
    connector.set_samplers(req.temperature, req.top_p, req.top_k, req.repeat_penalty, req.max_tokens)
    messages = [{"role": "system", "content": req.system_prompt.strip() or DEFAULT_FREE_SYSTEM_PROMPT}]
    for m in req.history[-20:]:
        if m.role in ("user", "assistant") and m.content:
            messages.append({"role": m.role, "content": m.content})
    messages.append({"role": "user", "content": req.query})
    with _PIPE_LOCK:
        answer = connector(messages)
    return {"answer": answer or NO_INFO, "fragments": [], "mode": "free"}


@app.post("/federated")
def federated_query(req: FederatedReq):
    """
    MoE semantic router: query ALL datasets, pick the one with the best
    top-fragment score, and answer from that dataset. The user doesn't need
    to pick a dataset.
    """
    _require_dasa()
    datasets = list_datasets()
    if not datasets:
        raise HTTPException(404, "No hay datasets disponibles.")

    best_dataset = None
    best_score = -1.0
    best_fragments: list = []
    best_pipe = None

    for ds in datasets:
        name = ds.get("name")
        if not name:
            continue
        try:
            pipe = _load_pipeline(name)
            fragments = pipe.agent_a.search(req.query)
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 — a broken dataset must not break the router
            continue
        if fragments:
            top_score = max(f.score for f in fragments)
            if top_score > best_score:
                best_score, best_dataset, best_fragments, best_pipe = top_score, name, fragments, pipe

    if best_pipe is None or best_score < 0.2:
        return {"answer": "No se encontró información relevante en ningún corpus.",
                "fragments": [], "mode": req.agent_b_mode, "dataset": None, "score": 0.0}

    answer = _synthesize(best_pipe, req.agent_b_mode, req.query, best_fragments, req)
    return {
        "answer": answer,
        "fragments": _fragments_json(best_fragments),
        "mode": req.agent_b_mode,
        "dataset": best_dataset,
        "score": float(best_score),
    }


@app.post("/compare")
def compare_models(req: CompareReq):
    """Run the same query with two Agent B modes and return both answers for A/B comparison."""
    pipe = _load_pipeline(req.dataset)
    fragments = pipe.agent_a.search(req.query)
    results = {}
    for label, mode in (("a", req.mode_a), ("b", req.mode_b)):
        try:
            answer = _synthesize(pipe, mode, req.query, fragments, req)
        except HTTPException as e:
            if e.status_code == 400 and mode in ("grounded", "free") and _LLAMA_CONNECTOR is None:
                answer = "(sin motor de inferencia)"
            else:
                raise
        results[label] = {"answer": answer, "mode": mode, "fragments": _fragments_json(fragments)}
    return results


@app.post("/oregano/{dataset}")
def oregano_test(dataset: str):
    """Run the anti-hallucination quality audit on a dataset."""
    pipe = _load_pipeline(dataset)
    with _PIPE_LOCK:
        return run_oregano_test(pipe, safe_name(dataset))


# ── Local GGUF models ───────────────────────────────────────────────────────

@app.get("/models/local")
def list_local_models():
    """List GGUF model files in the models directory (top level only)."""
    if not MODELS_DIR.exists():
        return []
    result = []
    for f in sorted(MODELS_DIR.iterdir()):
        if f.is_file() and f.suffix.lower() == ".gguf":
            st = f.stat()
            result.append({"name": f.stem, "file": f.name, "path": str(f),
                           "size_mb": round(st.st_size / (1024 * 1024)),
                           "mtime": int(st.st_mtime)})
    return result


@app.delete("/models/local/{file}")
def delete_local_model(file: str):
    if not is_valid_filename(file) or not file.lower().endswith(".gguf"):
        raise HTTPException(400, "nombre de archivo inválido")
    target = MODELS_DIR / file
    if not target.is_file():
        raise HTTPException(404, "modelo no encontrado")
    try:
        target.unlink()
    except PermissionError as e:
        raise HTTPException(409, "el modelo está en uso; detén la inferencia primero") from e
    Path(str(target) + ".part").unlink(missing_ok=True)
    return {"status": "deleted", "file": file}


# ── Inference engine hook (llama-server managed by the Rust shell) ─────────

@app.post("/inference/connect")
def inference_connect(req: InferenceConnectReq):
    """Register the llama-server endpoint so Agent B can use it (loopback only)."""
    global _LLAMA_CONNECTOR
    if req.host not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(400, "solo se permite un motor local (127.0.0.1)")
    _LLAMA_CONNECTOR = LlamaCppConnector(req.host, req.port, req.model)
    return {"status": "connected", "alive": _LLAMA_CONNECTOR.is_alive(), "port": req.port}


@app.post("/inference/disconnect")
def inference_disconnect():
    global _LLAMA_CONNECTOR
    _LLAMA_CONNECTOR = None
    return {"status": "disconnected"}


@app.get("/inference/status")
def inference_status():
    if _LLAMA_CONNECTOR is None:
        return {"connected": False}
    return {"connected": True, "alive": _LLAMA_CONNECTOR.is_alive()}


def _get_vram_usage() -> tuple[int, int] | None:
    """VRAM (used_mb, total_mb) via nvidia-smi. AMD/Intel report nothing here."""
    import subprocess
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().splitlines()[0].split(", ")
            if len(parts) >= 2:
                return int(parts[0]), int(parts[1])
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


@app.get("/inference/metrics")
def inference_metrics():
    """Live metrics from llama-server: tokens/s, TTFT, context, RAM, VRAM."""
    if _LLAMA_CONNECTOR is None:
        return {
            "connected": False, "active_slots": 0, "total_decoded": 0,
            "tokens_per_second": 0, "ttft_ms": 0,
            "context_used": 0, "context_total": 0, "context_pct": 0,
            "slots": [],
        }
    m = _LLAMA_CONNECTOR.get_metrics()
    try:
        import psutil
        vm = psutil.virtual_memory()
        m["ram_used_gb"] = round(vm.used / 1e9, 1)
        m["ram_total_gb"] = round(vm.total / 1e9, 1)
    except ImportError:
        pass
    vram = _get_vram_usage()
    if vram:
        m["vram_used_mb"], m["vram_total_mb"] = vram
    return {"connected": True, **m}


# ── HuggingFace downloads (GGUF) ────────────────────────────────────────────

@app.post("/models/hub/download")
def hub_download(req: HubDownloadReq):
    """Start a GGUF download from HuggingFace. Returns download_id for tracking."""
    if not is_valid_hf_repo(req.repo):
        raise HTTPException(400, "repositorio inválido (formato: usuario/repo)")
    if not is_valid_filename(req.file) or not req.file.lower().endswith(".gguf"):
        raise HTTPException(400, "nombre de archivo inválido (debe ser un .gguf sin rutas)")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dest = MODELS_DIR / req.file
    if dest.exists():
        return {"status": "already", "path": str(dest)}
    running = _DOWNLOADS.active_for(dest)
    if running is not None:
        return {"status": "in_progress", "download_id": running.id}
    state = _DOWNLOADS.start(req.repo, req.file, dest)
    return {"status": "started", "download_id": state.id}


@app.get("/models/hub/downloads")
def hub_downloads():
    """Every download the sidecar knows about (lets the UI re-attach after a remount)."""
    return _DOWNLOADS.snapshot()


def _download_or_404(dl_id: str):
    state = _DOWNLOADS.get(dl_id)
    if state is None:
        raise HTTPException(404, "download desconocido")
    return state


@app.get("/models/hub/download/{dl_id}/events")
def hub_download_events(dl_id: str):
    """SSE stream of download progress."""
    state = _download_or_404(dl_id)

    def gen():
        state.emit()
        while True:
            try:
                ev = state.q.get(timeout=30)
            except queue.Empty:
                if not state.active:
                    break
                continue
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
            if ev["status"] in ("done", "error", "cancelled"):
                break

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/models/hub/download/{dl_id}/cancel")
def hub_download_cancel(dl_id: str):
    _download_or_404(dl_id).cancel()
    return {"status": "cancelling"}


@app.post("/models/hub/download/{dl_id}/pause")
def hub_download_pause(dl_id: str):
    state = _download_or_404(dl_id)
    state.pause()
    return {"status": state.status}


@app.post("/models/hub/download/{dl_id}/resume")
def hub_download_resume(dl_id: str):
    state = _download_or_404(dl_id)
    state.resume()
    return {"status": state.status}


# ── OpenAI-compatible API out (KAMVEX as backend for other apps) ────────────

class OAIMessage(BaseModel):
    role: str
    content: str


class OAIRequest(BaseModel):
    model: str = "kamvex"
    messages: list[OAIMessage] = Field(default_factory=list)
    stream: bool = False
    temperature: float = Field(0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(512, ge=16, le=8192)


def _first_dataset_name() -> str | None:
    for d in list_datasets():
        if d.get("name"):
            return d["name"]
    return None


@app.get("/v1/models", tags=["openai-compatible"])
def v1_models():
    """List available 'models' — each dataset is a model in OpenAI terms."""
    out = [{"id": d["name"], "object": "model", "created": int(d.get("built_at", 0)), "owned_by": "kamvex"}
           for d in list_datasets() if d.get("name")]
    if not out:
        out.append({"id": "kamvex", "object": "model", "created": 0, "owned_by": "kamvex"})
    return {"object": "list", "data": out}


@app.post("/v1/chat/completions", tags=["openai-compatible"])
def v1_chat_completions(req: OAIRequest):
    """
    OpenAI-compatible endpoint. Other apps (Jan, Open WebUI, etc.) can use
    KAMVEX as a backend. The `model` field maps to a dataset name.
    Supports stream=true (SSE, word-chunked) and stream=false (JSON).
    """
    _require_dasa()
    user_content = ""
    system_content = ""
    for msg in reversed(req.messages):
        if msg.role == "user" and not user_content:
            user_content = msg.content.strip()
        elif msg.role == "system" and not system_content:
            system_content = msg.content.strip()
    if not user_content:
        raise HTTPException(400, "No se encontró mensaje con role='user'.")

    dataset_name = req.model
    if dataset_name == "kamvex" or not _NAME_RE.match(dataset_name) \
            or not (DATA_DIR / dataset_name / "meta.json").exists():
        dataset_name = _first_dataset_name()
    if not dataset_name:
        raise HTTPException(404, "No hay datasets disponibles. Construye uno en Conocimiento.")

    pipe = _load_pipeline(dataset_name)
    fragments = pipe.agent_a.search(user_content)
    llm_ready = _LLAMA_CONNECTOR is not None and _LLAMA_CONNECTOR.is_alive()
    samplers = SamplerFields(temperature=req.temperature, max_tokens=req.max_tokens)
    mode = "free" if llm_ready else "statistical"
    response_text = _synthesize(pipe, mode, user_content, fragments, samplers,
                                free_system_prompt=system_content or None)

    req_id = f"chatcmpl-kamvex-{int(time.time() * 1000)}"
    created = int(time.time())

    if req.stream:
        def _stream():
            words = response_text.split(" ")
            for i, word in enumerate(words):
                chunk_content = word + (" " if i < len(words) - 1 else "")
                chunk = {"id": req_id, "object": "chat.completion.chunk", "created": created,
                         "model": req.model,
                         "choices": [{"index": 0, "delta": {"content": chunk_content},
                                      "finish_reason": None}]}
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            final_chunk = {"id": req_id, "object": "chat.completion.chunk", "created": created,
                           "model": req.model,
                           "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _stream(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    prompt_tokens = len(user_content.split())
    completion_tokens = len(response_text.split())
    return {
        "id": req_id,
        "object": "chat.completion",
        "created": created,
        "model": req.model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": response_text},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                  "total_tokens": prompt_tokens + completion_tokens},
        "system_fingerprint": "kamvex-local",
    }


# ── Entrypoint ──────────────────────────────────────────────────────────────

def main():
    global DATA_DIR, MODELS_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data", default=None, help="datasets dir (overrides KAMVEX_DATA_DIR)")
    ap.add_argument("--models", default=None, help="models dir (overrides KAMVEX_MODELS_DIR)")
    args = ap.parse_args()
    if args.data:
        DATA_DIR = Path(args.data)
    if args.models:
        MODELS_DIR = Path(args.models)
    paths.ensure_dir(DATA_DIR)
    paths.ensure_dir(MODELS_DIR)
    print(f"[kamvex-sidecar] v{VERSION} data={DATA_DIR} models={MODELS_DIR} "
          f"dasa={_DASA_AVAILABLE} embeddings={_embeddings_status()['backend']}", flush=True)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port,
                log_level=os.environ.get("KAMVEX_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
