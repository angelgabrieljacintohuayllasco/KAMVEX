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
import urllib.request
import uuid
import zipfile
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
    _DASA_AVAILABLE = True
except ImportError:
    pass


def _can_build() -> bool:
    """Building an index needs scikit-learn (k-means); querying does not."""
    return _DASA_AVAILABLE and importlib.util.find_spec("sklearn") is not None


def _require_builder():
    """Import the IVF-PQ builder lazily so chat keeps working when scikit-learn is absent."""
    try:
        from shard.index.ivfpq_builder import build_ivfpq
    except ImportError as e:
        raise HTTPException(
            503,
            f"Este sidecar no puede construir datasets (falta scikit-learn: {e}). "
            "El chat sobre datasets ya construidos sí funciona.",
        ) from e
    return build_ivfpq

from downloads import DownloadManager, DownloadState, is_allowed_url, is_valid_filename, is_valid_hf_repo  # noqa: E402
from embedding_gguf import LlamaEmbeddingEngine  # noqa: E402
from embedding_gguf import DEFAULT_FILE as EMBED_FILE, DEFAULT_REPO as EMBED_REPO  # noqa: E402
from grounding import (DETERMINISTIC_SEED, MIN_COVERAGE, coverage as lexical_coverage,  # noqa: E402
                       exact_definition_answer, grounded_messages, trim_fragments)
import experts as experts_mod  # noqa: E402
from jobs import BuildJob, run_build  # noqa: E402
from keyindex import KEY_HIT_SCORE, KeyIndex  # noqa: E402
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
# Catalog of downloadable datasets: the live manifest of the GitHub release (so new datasets
# appear without reinstalling), with the bundled copy as offline fallback.
DEFAULT_CATALOG_URL = "https://github.com/angelgabrieljacintohuayllasco/KAMVEX/releases/download/datasets-v1/manifest.json"
DATASET_CATALOG_FILE: Path = paths.SIDECAR_DIR / "datasets_catalog.json"
KAMVEX_FORMAT = 1
_CATALOG_CACHE: dict = {"at": 0.0, "data": None}

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
_KEY_INDEXES: dict[str, KeyIndex | None] = {}
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
        d = engine.describe()
        info.update({k: d.get(k) for k in ("running", "port", "pid", "dim", "job_assigned")})
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
        _KEY_INDEXES[db.name] = KeyIndex.load(db)
        pipe._kamvex_name = db.name
    return pipe


def _close_pipeline(name: str) -> None:
    _KEY_INDEXES.pop(name, None)
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


# ── .kamvex bundles (download / import / catalog) ───────────────────────────

def _validate_bundle(zf: zipfile.ZipFile) -> dict:
    """Reject unsafe entries; return the bundle's meta.json (must be at the root)."""
    names = zf.namelist()
    for n in names:
        p = Path(n)
        if p.is_absolute() or ".." in p.parts or n.startswith(("/", "\\")) or ":" in n:
            raise HTTPException(400, f"bundle inválido: entrada insegura {n!r}")
    if "meta.json" not in names:
        raise HTTPException(400, "bundle inválido: falta meta.json en la raíz")
    try:
        meta = json.loads(zf.read("meta.json").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(400, f"bundle inválido: meta.json corrupto ({e})") from e
    if not isinstance(meta, dict) or "n_records" not in meta or "num_shards" not in meta:
        raise HTTPException(400, "bundle inválido: meta.json incompleto")
    return meta


def _install_bundle(zip_path: Path, name: str) -> dict:
    """Unpack a .kamvex into DATA_DIR/<name> (replacing any previous dataset of that name)."""
    name = safe_name(name)
    target = DATA_DIR / name
    tmp = DATA_DIR / f"_tmp_{uuid.uuid4().hex[:8]}"
    with zipfile.ZipFile(zip_path) as zf:
        meta = _validate_bundle(zf)
        tmp.mkdir(parents=True, exist_ok=True)
        zf.extractall(tmp)
    meta["name"] = name
    meta.setdefault("installed_from", zip_path.name)
    meta["installed_at"] = int(time.time())
    (tmp / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    with _PIPE_LOCK:
        _close_pipeline(name)
        if target.exists():
            shutil.rmtree(target)
        os.replace(tmp, target)
    return meta


def _load_catalog() -> dict:
    """Dataset catalog: remote manifest (KAMVEX_DATASET_CATALOG_URL) or the bundled file."""
    now = time.time()
    if _CATALOG_CACHE["data"] is not None and now - _CATALOG_CACHE["at"] < 600:
        return _CATALOG_CACHE["data"]
    data: dict = {"version": 1, "datasets": []}
    url = os.environ.get("KAMVEX_DATASET_CATALOG_URL", DEFAULT_CATALOG_URL).strip()
    if url and url.lower() != "off" and is_allowed_url(url):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": f"KAMVEX/{VERSION}"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 — offline: fall back to the bundled catalog
            data = {}
    if not data.get("datasets") and DATASET_CATALOG_FILE.exists():
        try:
            data = json.loads(DATASET_CATALOG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {"version": 1, "datasets": []}
    base = (data.get("release_base") or "").rstrip("/")
    for d in data.get("datasets", []):
        if not d.get("url") and base and d.get("file"):
            d["url"] = f"{base}/{d['file']}"
        if not d.get("source_url_file") and base and d.get("source_file"):
            d["source_url_file"] = f"{base}/{d['source_file']}"
    _CATALOG_CACHE.update(at=now, data=data)
    return data


# ── Request models ──────────────────────────────────────────────────────────

class SamplerFields(BaseModel):
    temperature: float = Field(0.1, ge=0.0, le=2.0)
    top_p: float = Field(0.95, ge=0.0, le=1.0)
    top_k: int = Field(40, ge=1, le=1000)
    repeat_penalty: float = Field(1.0, ge=0.5, le=3.0)
    max_tokens: int = Field(512, ge=16, le=8192)
    # Grounded mode: greedy + fixed seed (same question → same answer) and the lexical guardrail.
    deterministic: bool = True
    guardrail: bool = True


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


class ExpertChatReq(SamplerFields):
    """Chat through an expert: it picks dataset(s), mode, prompt and samplers."""
    expert: str
    query: str = Field(..., min_length=1, max_length=20000)
    dataset: str = ""          # optional: pin one of the expert's datasets
    mode: str = ""             # optional: override the expert's default mode
    history: list["ChatMessage"] = Field(default_factory=list)
    override_samplers: bool = False   # true = use the request's samplers, not the expert's


class InstallReq(BaseModel):
    """Install a .kamvex bundle by catalog id or by explicit URL."""
    id: str = ""
    url: str = ""
    name: str = ""
    sha256: str = ""


class ImportReq(BaseModel):
    path: str
    name: str = ""


class RebuildReq(BaseModel):
    profile: str = "low-ram"


# ── Synthesis (single place where Agent B modes are applied) ────────────────

def _fragments_json(fragments) -> list[dict]:
    return [{"text": f.text, "score": float(f.score), "source_id": f.source_id} for f in fragments]


def _statistical_answer(agent_b, query: str, fragments) -> tuple[str, dict]:
    """Deterministic answer: exact record text for definition questions, else DASA's rewriter."""
    exact = exact_definition_answer(query, fragments)
    if exact:
        return exact, {"engine": "exact"}
    agent_b._llm_callable = None
    return (agent_b.synthesize(query, fragments) or "").strip() or NO_INFO, {"engine": "rewriter"}


def _synthesize(pipe, mode: str, query: str, fragments, s: SamplerFields,
                free_system_prompt: str | None = None) -> str:
    return _synthesize_ex(pipe, mode, query, fragments, s, free_system_prompt)[0]


def _synthesize_ex(pipe, mode: str, query: str, fragments, s: SamplerFields,
                   free_system_prompt: str | None = None) -> tuple[str, dict]:
    """Run Agent B in the requested mode. Returns (answer, meta).

    statistical — no LLM: exact record text for "¿qué es X?" or DASA's rewriter (0 hallucination).
    grounded    — LLM formats relevant fragments under a strict prompt, greedy + fixed seed;
                  a lexical guardrail rejects answers that use words the corpus does not
                  contain and falls back to the statistical answer. Never free-talks.
    free        — LLM answers from the corpus when relevant, freely otherwise.
    """
    if mode not in MODES:
        raise HTTPException(400, f"modo agent_b inválido: {mode}")

    with _PIPE_LOCK:
        agent_b = pipe.agent_b
        if mode == "statistical":
            return _statistical_answer(agent_b, query, fragments)

        connector = _require_connector()

        if mode == "grounded":
            relevant = [f for f in fragments if f.score >= GROUNDED_MIN_SCORE]
            if not relevant:
                return NOT_COVERED, {"engine": "none", "reason": "no_relevant_fragments"}
            # An exact key hit is authoritative: keep the context to those records.
            exact_hits = [f for f in relevant if f.score >= KEY_HIT_SCORE]
            context = trim_fragments(exact_hits or relevant, query)
            if s.deterministic:
                connector.set_deterministic(DETERMINISTIC_SEED, s.max_tokens)
            else:
                connector.set_samplers(s.temperature, s.top_p, s.top_k, s.repeat_penalty, s.max_tokens)
            agent_b._llm_callable = connector
            answer = (connector(grounded_messages(query, context)) or "").strip()
            if not answer:
                return NOT_COVERED, {"engine": "llm", "reason": "empty"}
            meta: dict = {"engine": "llm", "deterministic": s.deterministic}
            if s.guardrail:
                cov, missing = lexical_coverage(answer, context)
                meta.update({"coverage": cov, "unsupported": missing[:12]})
                if cov < MIN_COVERAGE and normalize_answer(answer) != normalize_answer(NOT_COVERED):
                    fallback, fb_meta = _statistical_answer(agent_b, query, relevant)
                    meta.update({"fallback": True, "llm_answer": answer, "fallback_engine": fb_meta["engine"]})
                    return fallback, meta
            return answer, meta

        connector.set_samplers(s.temperature, s.top_p, s.top_k, s.repeat_penalty, s.max_tokens)
        agent_b._llm_callable = connector
        original_prompt = getattr(agent_b, "_free_system_prompt", None)
        try:
            if free_system_prompt and original_prompt is not None:
                agent_b._free_system_prompt = free_system_prompt
            return (agent_b.synthesize(query, fragments) or "").strip() or NO_INFO, {"engine": "llm"}
        finally:
            if original_prompt is not None:
                agent_b._free_system_prompt = original_prompt


def normalize_answer(text: str) -> str:
    return " ".join(text.lower().split()).strip(" .")


def search_query(query: str) -> str:
    """Strip Spanish inverted marks and trailing punctuation so DASA's exact-key boost
    ('qué es X' → X) sees the question shape it expects."""
    q = query.strip().lstrip("¿¡ ").rstrip("?! ")
    return q or query


def _key_hits(pipe, query: str):
    """Records whose key is named in the question, fetched straight from the SHARD store."""
    index = _KEY_INDEXES.get(getattr(pipe, "_kamvex_name", ""))
    reader = getattr(pipe.agent_a, "_shard_reader", None)
    if not index or reader is None:
        return []
    from dasa.agent_a.retrieval_agent import Fragment
    hits = []
    for rank, key in enumerate(index.match(query)):
        raw = reader.find(key)
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            record = {"text": str(raw)}
        # Decreasing scores: "Departamento de Amazonas" matches Perú, Colombia and the
        # Confederación. All three are worth showing, but only the best one goes into the
        # grounded context — three records with three different capitals confuse a 1.5B model.
        hits.append(Fragment(text=pipe.agent_a._record_to_text(record),
                             score=KEY_HIT_SCORE - 0.02 * rank, source_id=key))
    return hits


def _search(pipe, query: str):
    """Semantic search (DASA) with lexical key hits merged in front."""
    semantic = pipe.agent_a.search(search_query(query))
    hits = _key_hits(pipe, query)
    if not hits:
        return semantic
    seen = {h.source_id for h in hits}
    merged = hits + [f for f in semantic if f.source_id not in seen]
    return merged[: max(len(hits), pipe.config.top_k_fragments)]


# ── Health / status ─────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": VERSION,
        "dasa": _DASA_AVAILABLE,
        "can_build": _can_build(),
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
                out.append(json.loads(meta.read_text(encoding="utf-8"))
                           | {"path": str(d), "has_records": (d / "records.json").is_file()})
            except json.JSONDecodeError:
                continue
    return out


def _start_build(name: str, json_path: Path, profile: str, extra_meta: dict | None = None) -> str:
    build_ivfpq = _require_builder()
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


# ── Experts (domain profiles: corpus + model + mode + prompt + samplers) ────

def _experts() -> list:
    return experts_mod.load_catalog()


def _expert_or_404(expert_id: str):
    for e in _experts():
        if e.id == expert_id:
            return e
    raise HTTPException(404, f"experto desconocido: {expert_id}")


def _expert_status(expert) -> dict:
    installed = {d.get("name") for d in list_datasets()}
    local_files = {m["file"] for m in list_local_models()}
    return experts_mod.status(expert, installed, local_files)


@app.get("/experts")
def list_experts():
    """Every expert with what is already installed on this machine."""
    out = []
    installed = {d.get("name") for d in list_datasets()}
    local_files = {m["file"] for m in list_local_models()}
    for e in _experts():
        out.append({**e.to_json(), "status": experts_mod.status(e, installed, local_files)})
    return {"version": 1, "experts": out}


@app.get("/experts/{expert_id}")
def get_expert(expert_id: str):
    e = _expert_or_404(expert_id)
    return {**e.to_json(), "status": _expert_status(e)}


@app.post("/experts/{expert_id}/chat")
def expert_chat(expert_id: str, req: ExpertChatReq):
    """Ask the expert: its corpus, its mode, its prompt and its decoding settings."""
    expert = _expert_or_404(expert_id)
    mode = req.mode or expert.default_mode
    if mode not in MODES:
        raise HTTPException(400, f"modo inválido: {mode}")

    samplers = req
    if not req.override_samplers and expert.samplers:
        merged = req.model_dump()
        merged.update({k: v for k, v in expert.samplers.items() if k in SamplerFields.model_fields})
        samplers = SamplerFields(**{k: v for k, v in merged.items() if k in SamplerFields.model_fields})

    # No corpus (or free mode without datasets) → straight LLM chat with the expert's prompt.
    datasets = [req.dataset] if req.dataset else expert.datasets
    available = [d for d in datasets if (DATA_DIR / d / "meta.json").exists()]
    if not available:
        if mode == "statistical":
            raise HTTPException(400, f"el experto «{expert.name}» necesita su corpus: {', '.join(expert.datasets)}")
        connector = _require_connector()
        connector.set_samplers(samplers.temperature, samplers.top_p, samplers.top_k,
                               samplers.repeat_penalty, samplers.max_tokens)
        messages = [{"role": "system", "content": expert.system_prompt or DEFAULT_FREE_SYSTEM_PROMPT}]
        for m in req.history[-20:]:
            if m.role in ("user", "assistant") and m.content:
                messages.append({"role": m.role, "content": m.content})
        messages.append({"role": "user", "content": req.query})
        with _PIPE_LOCK:
            answer = connector(messages)
        return {"answer": answer or NO_INFO, "fragments": [], "mode": mode, "dataset": None,
                "expert": expert.id, "meta": {"engine": "llm", "corpus": False}}

    # With corpus: search every dataset of the expert and keep the best fragments.
    t0 = time.perf_counter()
    scored: list = []
    used: list[str] = []
    for name in available:
        try:
            pipe = _load_pipeline(name)
        except HTTPException:
            continue
        frags = _search(pipe, req.query)
        if frags:
            used.append(name)
            scored.extend((f, name, pipe) for f in frags)
    if not scored:
        return {"answer": NOT_COVERED if mode != "free" else NO_INFO, "fragments": [], "mode": mode,
                "dataset": None, "expert": expert.id, "meta": {"engine": "none", "datasets": available}}

    scored.sort(key=lambda t: t[0].score, reverse=True)
    top = scored[: max(1, expert.top_k)]
    fragments = [t[0] for t in top]
    best_pipe = top[0][2]
    best_dataset = top[0][1]
    t_search = time.perf_counter() - t0

    answer, meta = _synthesize_ex(best_pipe, mode, req.query, fragments, samplers,
                                  free_system_prompt=expert.system_prompt or None)
    return {
        "answer": answer,
        "fragments": _fragments_json(fragments),
        "mode": mode,
        "dataset": best_dataset,
        "expert": expert.id,
        "meta": {**meta, "corpus": True, "datasets": used, "search_ms": round(t_search * 1000, 1),
                 "total_ms": round((time.perf_counter() - t0) * 1000, 1)},
    }


@app.get("/datasets/catalog")
def datasets_catalog():
    """Downloadable datasets (pre-built shards + index) with an `installed` flag."""
    data = _load_catalog()
    installed = {d.get("name") for d in list_datasets()}
    out = []
    for d in data.get("datasets", []):
        entry = dict(d)
        entry["installed"] = entry.get("id") in installed or entry.get("name") in installed
        out.append(entry)
    return {"version": data.get("version", 1), "release_base": data.get("release_base", ""), "datasets": out}


@app.post("/datasets/install")
def install_dataset(req: InstallReq):
    """Download a .kamvex bundle (catalog id or URL), verify it and unpack it. Progress via /downloads/{id}/events."""
    url, name, sha = req.url.strip(), req.name.strip(), req.sha256.strip().lower()
    if req.id:
        entry = next((d for d in _load_catalog().get("datasets", []) if d.get("id") == req.id), None)
        if entry is None:
            raise HTTPException(404, f"dataset {req.id!r} no está en el catálogo")
        url = url or entry.get("url", "")
        name = name or entry.get("id", "")
        sha = sha or (entry.get("sha256") or "").lower()
    if not url or not is_allowed_url(url):
        raise HTTPException(400, "URL no permitida (solo https en github.com / huggingface.co)")
    if not name:
        name = Path(url.split("?")[0]).stem
    name = safe_name(name)
    dl_dir = DATA_DIR / "_downloads"
    dl_dir.mkdir(parents=True, exist_ok=True)
    dest = dl_dir / f"{name}.kamvex"
    running = _DOWNLOADS.active_for(dest)
    if running is not None:
        return {"status": "in_progress", "download_id": running.id, "name": name}
    dest.unlink(missing_ok=True)

    def _post(state: DownloadState) -> dict:
        try:
            meta = _install_bundle(state.dest, name)
        finally:
            state.dest.unlink(missing_ok=True)
        return {"name": name, "n_records": meta.get("n_records"), "dim": meta.get("dim")}

    state = _DOWNLOADS.start("", f"{name}.kamvex", dest, url=url, kind="dataset",
                             sha256=sha or None, post_process=_post)
    return {"status": "started", "download_id": state.id, "name": name}


@app.post("/datasets/import")
def import_dataset(req: ImportReq):
    """Install a local .kamvex file (e.g. exported from another KAMVEX)."""
    src = Path(req.path)
    if not src.is_file() or src.suffix.lower() not in (".kamvex", ".zip"):
        raise HTTPException(404, "archivo .kamvex no encontrado")
    name = req.name.strip() or src.stem
    meta = _install_bundle(src, name)
    return {"status": "installed", "name": meta["name"], "n_records": meta.get("n_records"), "dim": meta.get("dim")}


@app.post("/datasets/{name}/rebuild")
def rebuild_dataset(name: str, req: RebuildReq):
    """Re-embed a dataset from its bundled records.json with the local embedding engine."""
    _require_dasa()
    _require_profile(req.profile)
    db, meta = _require_dataset(name)
    records = db / "records.json"
    if not records.is_file():
        raise HTTPException(404, "este dataset no incluye records.json; no se puede reconstruir")
    keep = {k: meta.get(k) for k in ("display_name", "description", "language", "license", "source_url",
                                     "source_doc", "n_pages", "kamvex_format") if meta.get(k) is not None}
    # run_build overwrites shards/index in place; keep the source file where it is.
    return {"job_id": _start_build(db.name, records, req.profile, keep or None)}


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
    t0 = time.perf_counter()
    fragments = _search(pipe, req.query)
    t_search = time.perf_counter() - t0
    answer, meta = _synthesize_ex(pipe, req.agent_b_mode, req.query, fragments, req)
    return {
        "answer": answer,
        "fragments": _fragments_json(fragments),
        "mode": req.agent_b_mode,
        "dataset": safe_name(req.dataset),
        "meta": {**meta, "search_ms": round(t_search * 1000, 1), "total_ms": round((time.perf_counter() - t0) * 1000, 1)},
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
            fragments = _search(pipe, req.query)
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
    fragments = _search(pipe, req.query)
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
@app.get("/downloads")
def hub_downloads():
    """Every download the sidecar knows about (lets the UI re-attach after a remount)."""
    return _DOWNLOADS.snapshot()


def _download_or_404(dl_id: str):
    state = _DOWNLOADS.get(dl_id)
    if state is None:
        raise HTTPException(404, "download desconocido")
    return state


@app.get("/models/hub/download/{dl_id}/events")
@app.get("/downloads/{dl_id}/events")
def hub_download_events(dl_id: str):
    """SSE stream of download progress (models and dataset bundles)."""
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
@app.post("/downloads/{dl_id}/cancel")
def hub_download_cancel(dl_id: str):
    _download_or_404(dl_id).cancel()
    return {"status": "cancelling"}


@app.post("/models/hub/download/{dl_id}/pause")
@app.post("/downloads/{dl_id}/pause")
def hub_download_pause(dl_id: str):
    state = _download_or_404(dl_id)
    state.pause()
    return {"status": state.status}


@app.post("/models/hub/download/{dl_id}/resume")
@app.post("/downloads/{dl_id}/resume")
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
    fragments = _search(pipe, user_content)
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
