"""
DASA-UI sidecar — thin FastAPI server launched by the Tauri shell.

Reuses DASA (pipeline, embeddings) and SHARD (storage, IVF-PQ builder) without
rewriting any logic. Exposes dataset build + grounded chat over localhost.

Run:  python server.py --port 8765 [--data <dir>]
"""

import argparse
import json
import os
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

# ── Resolve sibling DASA-main / SHARD-main onto sys.path ─────────────────────
_HERE = Path(__file__).resolve()
_PARENT_OF_REPOS = _HERE.parents[2]   # .../2 REPOS DASA AND SHARD
for _sib, _pkg in (("DASA-main", "dasa"), ("SHARD-main", "shard")):
    _p = _PARENT_OF_REPOS / _sib
    if (_p / _pkg).is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ── DASA / SHARD imports (lazy: may be unavailable in PyInstaller bundle) ──
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

from jobs import BuildJob, run_build
from llama_connector import LlamaCppConnector
from oregano import run_oregano_test

NUM_SHARDS = 64
DATA_DIR = Path(os.environ.get("DASA_UI_DATA", _HERE.parent / "appdata" / "datasets"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="DASA-UI sidecar")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

_JOBS: "dict[str, BuildJob]" = {}
_PIPELINES: dict = {}
_embedding_engine = None
_LLAMA_CONNECTOR: LlamaCppConnector | None = None


def _get_embedding_engine():
    """Lazily create the embedding engine (heavy: loads sentence-transformers)."""
    global _embedding_engine
    if _embedding_engine is None and _DASA_AVAILABLE:
        _embedding_engine = EmbeddingEngine(DASAConfig())
    return _embedding_engine


def _require_dasa():
    """Raise HTTPException if DASA/SHARD are not available."""
    if not _DASA_AVAILABLE:
        raise HTTPException(
            503,
            "DASA/SHARD no disponibles. En el instalador, usa datasets pre-construidos. "
            "Para construir nuevos datasets, ejecuta KAMVEX en modo desarrollo (Python + deps).",
        )


# ── Models ──────────────────────────────────────────────────────────────────
class BuildReq(BaseModel):
    name: str
    json_path: str
    profile: str = "low-ram"


class BuildTextReq(BaseModel):
    name: str
    text: str = ""
    pdf_path: str = ""
    chunk_size: int = 500
    profile: str = "low-ram"


class ChatReq(BaseModel):
    dataset: str
    query: str
    agent_b_mode: str = "statistical"
    temperature: float = 0.1
    top_p: float = 0.95
    top_k: int = 40
    repeat_penalty: float = 1.0


class InferenceConnectReq(BaseModel):
    host: str = "127.0.0.1"
    port: int
    model: str = "local"


# ── Endpoints ───────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/datasets")
def list_datasets():
    out = []
    for d in sorted(DATA_DIR.iterdir()) if DATA_DIR.exists() else []:
        meta = d / "meta.json"
        if d.is_dir() and meta.exists():
            try:
                out.append(json.loads(meta.read_text(encoding="utf-8")) | {"path": str(d)})
            except json.JSONDecodeError:
                continue
    return out


def _load_pipeline(dataset_name: str) -> DASAPipeline:
    """Load and cache a pipeline for a dataset."""
    db = DATA_DIR / dataset_name
    meta = json.loads((db / "meta.json").read_text(encoding="utf-8"))
    pipe = _PIPELINES.get(dataset_name)
    if pipe is None:
        cfg = DASAConfig(use_shard_backend=True, shard_db_path=str(db),
                         shard_num_shards=meta.get("num_shards", NUM_SHARDS))
        pipe = DASAPipeline(cfg)
        pipe.load(str(db))
        _PIPELINES[dataset_name] = pipe
    return pipe


@app.post("/federated")
def federated_query(req: ChatReq):
    _require_dasa()
    """
    MoE semantic router: query ALL datasets, pick the one with the best
    top-fragment score, and answer from that dataset. This enables
    multi-dataset federation — the user doesn't need to pick a dataset.
    """
    datasets = list_datasets()
    if not datasets:
        raise HTTPException(404, "No hay datasets disponibles.")

    best_dataset = None
    best_score = -1.0
    best_fragments = []
    best_pipe = None

    for ds in datasets:
        name = ds["name"]
        try:
            pipe = _load_pipeline(name)
            fragments = pipe.agent_a.search(req.query)
            if fragments:
                top_score = max(f.score for f in fragments)
                if top_score > best_score:
                    best_score = top_score
                    best_dataset = name
                    best_fragments = fragments
                    best_pipe = pipe
        except Exception:
            continue

    if best_pipe is None or best_score < 0.2:
        return {
            "answer": "No se encontró información relevante en ningún corpus.",
            "fragments": [],
            "mode": req.agent_b_mode,
            "dataset": None,
            "score": 0.0,
        }

    mode = req.agent_b_mode
    if mode == "statistical":
        best_pipe.agent_b._llm_callable = None
    elif mode in ("grounded", "free"):
        if _LLAMA_CONNECTOR is None:
            raise HTTPException(400, "No hay motor de inferencia activo.")
        _LLAMA_CONNECTOR.set_samplers(req.temperature, req.top_p, req.top_k, req.repeat_penalty)
        best_pipe.agent_b._llm_callable = _LLAMA_CONNECTOR

    answer = best_pipe.agent_b.synthesize(req.query, best_fragments) or \
        "No se encontró información relevante."

    return {
        "answer": answer,
        "fragments": [
            {"text": f.text, "score": float(f.score), "source_id": f.source_id}
            for f in best_fragments
        ],
        "mode": mode,
        "dataset": best_dataset,
        "score": best_score,
    }


@app.post("/datasets/build")
def build_dataset(req: BuildReq):
    _require_dasa()
    if not Path(req.json_path).exists():
        raise HTTPException(404, f"Archivo no encontrado: {req.json_path}")
    if req.profile not in ("low-ram", "medium", "fast"):
        raise HTTPException(400, f"perfil inválido: {req.profile}")
    job = BuildJob()
    jid = uuid.uuid4().hex
    _JOBS[jid] = job
    _PIPELINES.pop(req.name, None)   # invalidate any cached pipeline for this name
    threading.Thread(
        target=run_build, args=(job,),
        kwargs=dict(name=req.name, json_path=req.json_path, profile=req.profile,
                    data_dir=DATA_DIR, num_shards=None,
                    embedding_engine=_get_embedding_engine(),
                    shard_writer_cls=ShardWriter, build_ivfpq_fn=build_ivfpq),
        daemon=True,
    ).start()
    return {"job_id": jid}


def _extract_pdf_text(pdf_path: str) -> str:
    """Extract text from a PDF file. Tries pypdf first, falls back to raw stream parsing."""
    if not Path(pdf_path).exists():
        raise HTTPException(404, f"PDF no encontrado: {pdf_path}")

    # Try pypdf if available
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_path)
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        pass

    # Fallback: extract text from raw PDF streams (works for simple text PDFs)
    import re
    import zlib
    raw = Path(pdf_path).read_bytes()
    texts = []
    # Find all stream...endstream blocks
    for match in re.finditer(b'stream\r?\n(.*?)\r?\nendstream', raw, re.DOTALL):
        data = match.group(1)
        try:
            decompressed = zlib.decompress(data)
            # Extract text between BT...ET markers (text objects)
            text_matches = re.findall(rb'\((.*?)\)', decompressed)
            if text_matches:
                texts.append(" ".join(t.decode('latin-1') for t in text_matches))
        except Exception:
            continue
    return "\n".join(texts)


@app.post("/datasets/build-text")
def build_from_text(req: BuildTextReq):
    _require_dasa()
    """Build a dataset from raw text or PDF by chunking it into records."""
    if req.profile not in ("low-ram", "medium", "fast"):
        raise HTTPException(400, f"perfil inválido: {req.profile}")

    text = req.text.strip()
    if req.pdf_path:
        text = _extract_pdf_text(req.pdf_path)

    if not text:
        raise HTTPException(400, "texto vacío o PDF sin texto extraíble")
    chunks = []
    current = ""
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) > req.chunk_size and current:
            chunks.append(current)
            current = para
        else:
            current = f"{current} {para}".strip() if current else para
    if current:
        chunks.append(current)

    if not chunks:
        raise HTTPException(400, "no se pudo extraer texto válido")

    records = [{"id": f"chunk_{i}", "title": f"Fragmento {i+1}", "content": c}
               for i, c in enumerate(chunks)]

    # Write to temp JSON and run build
    import tempfile
    tmp = Path(tempfile.mktemp(suffix=".json"))
    tmp.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

    job = BuildJob()
    jid = uuid.uuid4().hex
    _JOBS[jid] = job
    _PIPELINES.pop(req.name, None)
    threading.Thread(
        target=run_build, args=(job,),
        kwargs=dict(name=req.name, json_path=str(tmp), profile=req.profile,
                    data_dir=DATA_DIR, num_shards=None,
                    embedding_engine=_get_embedding_engine(),
                    shard_writer_cls=ShardWriter, build_ivfpq_fn=build_ivfpq),
        daemon=True,
    ).start()
    return {"job_id": jid, "n_chunks": len(chunks)}


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


@app.post("/chat")
def chat(req: ChatReq):
    _require_dasa()
    db = DATA_DIR / req.dataset
    meta_path = db / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, f"dataset desconocido: {req.dataset}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    pipe = _PIPELINES.get(req.dataset)
    if pipe is None:
        cfg = DASAConfig(use_shard_backend=True, shard_db_path=str(db),
                         shard_num_shards=meta.get("num_shards", NUM_SHARDS))
        pipe = DASAPipeline(cfg)
        pipe.load(str(db))
        _PIPELINES[req.dataset] = pipe

    fragments = pipe.agent_a.search(req.query)

    mode = req.agent_b_mode
    if mode == "statistical":
        pipe.agent_b._llm_callable = None
    elif mode == "grounded":
        if _LLAMA_CONNECTOR is None:
            raise HTTPException(400, "No hay motor de inferencia activo. Inicia un modelo en Models.")
        _LLAMA_CONNECTOR.set_samplers(req.temperature, req.top_p, req.top_k, req.repeat_penalty)
        pipe.agent_b._llm_callable = _LLAMA_CONNECTOR
    elif mode == "free":
        if _LLAMA_CONNECTOR is None:
            raise HTTPException(400, "No hay motor de inferencia activo. Inicia un modelo en Models.")
        _LLAMA_CONNECTOR.set_samplers(req.temperature, req.top_p, req.top_k, req.repeat_penalty)
        pipe.agent_b._llm_callable = _LLAMA_CONNECTOR
    else:
        raise HTTPException(400, f"modo agent_b inválido: {mode}")

    answer = pipe.agent_b.synthesize(req.query, fragments) or \
        "No se encontró información relevante en el corpus para esta consulta."
    return {
        "answer": answer,
        "fragments": [
            {"text": f.text, "score": float(f.score), "source_id": f.source_id}
            for f in fragments
        ],
        "mode": mode,
    }


@app.post("/inference/connect")
def inference_connect(req: InferenceConnectReq):
    """Register the llama-server endpoint so Agent B can use it."""
    global _LLAMA_CONNECTOR
    _LLAMA_CONNECTOR = LlamaCppConnector(req.host, req.port, req.model)
    return {"status": "connected", "alive": _LLAMA_CONNECTOR.is_alive()}


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


def _get_vram_usage():
    """Try to get VRAM usage via nvidia-smi. Returns (used_mb, total_mb) or None."""
    import subprocess
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts = r.stdout.strip().split(", ")
            if len(parts) >= 2:
                return (int(parts[0]), int(parts[1]))
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


@app.get("/inference/metrics")
def inference_metrics():
    """Fetch live metrics from llama-server: tokens/s, TTFT, context, RAM, VRAM."""
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
        m["vram_used_mb"] = vram[0]
        m["vram_total_mb"] = vram[1]

    return {"connected": True, **m}


# ── HuggingFace model hub (curated GGUF list) ──────────────────────────────

_HF_CURATED = [
    # ── Ultraligeros (< 1 GB) — CPU / poca RAM ──
    {"repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF", "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
     "name": "Qwen2.5 0.5B Q4", "size_mb": 491, "category": "ultralight",
     "desc": "Ultraligero, ideal para CPU o 4 GB RAM"},
    {"repo": "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF", "file": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
     "name": "TinyLlama 1.1B Q4", "size_mb": 700, "category": "ultralight",
     "desc": "Mínimo, para pruebas rápidas"},

    # ── Ligeros (1-3 GB) — CPU / RAM media ──
    {"repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF", "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
     "name": "Qwen2.5 1.5B Q4", "size_mb": 1120, "category": "light",
     "desc": "Pequeño, rápido, buena calidad"},
    {"repo": "bartowski/gemma-2-2b-it-GGUF", "file": "gemma-2-2b-it-Q4_K_M.gguf",
     "name": "Gemma 2 2B Q4", "size_mb": 1710, "category": "light",
     "desc": "Google, multilingüe, compacto"},
    {"repo": "Qwen/Qwen2.5-3B-Instruct-GGUF", "file": "qwen2.5-3b-instruct-q4_k_m.gguf",
     "name": "Qwen2.5 3B Q4", "size_mb": 2100, "category": "light",
     "desc": "Equilibrio calidad/velocidad"},
    {"repo": "bartowski/Phi-3.5-mini-instruct-GGUF", "file": "Phi-3.5-mini-instruct-Q4_K_M.gguf",
     "name": "Phi-3.5 Mini Q4", "size_mb": 2390, "category": "light",
     "desc": "Microsoft, multilingüe, código"},

    # ── Medios (3-6 GB) — GPU recomendada ──
    {"repo": "Qwen/Qwen2.5-7B-Instruct-GGUF", "file": "qwen2.5-7b-instruct-q3_k_m.gguf",
     "name": "Qwen2.5 7B Q3", "size_mb": 3810, "category": "medium",
     "desc": "Alta calidad, necesita GPU o 16 GB RAM"},
    {"repo": "bartowski/Mistral-7B-Instruct-v0.3-GGUF", "file": "Mistral-7B-Instruct-v0.3-Q4_K_M.gguf",
     "name": "Mistral 7B v0.3 Q4", "size_mb": 4370, "category": "medium",
     "desc": "Europeo, buen multilingüe"},
    {"repo": "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF", "file": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
     "name": "Qwen2.5 Coder 7B Q4", "size_mb": 4680, "category": "medium",
     "desc": "Especializado en código y programación"},
    {"repo": "bartowski/DeepSeek-R1-Distill-Qwen-7B-GGUF", "file": "DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf",
     "name": "DeepSeek-R1 Distill 7B Q4", "size_mb": 4680, "category": "medium",
     "desc": "Razonamiento avanzado, estilo R1"},
    {"repo": "lmstudio-community/Meta-Llama-3.1-8B-Instruct-GGUF", "file": "Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf",
     "name": "Llama 3.1 8B Q4", "size_mb": 4920, "category": "medium",
     "desc": "Meta, equilibrio calidad/tamaño"},

    # ── Grandes (6-10 GB) — GPU / mucha RAM ──
    {"repo": "bartowski/Mistral-Nemo-Instruct-2407-GGUF", "file": "Mistral-Nemo-Instruct-2407-Q4_K_M.gguf",
     "name": "Mistral Nemo 12B Q4", "size_mb": 7480, "category": "large",
     "desc": "12B, 128k contexto, multilingüe"},
    {"repo": "bartowski/Qwen2.5-14B-Instruct-GGUF", "file": "Qwen2.5-14B-Instruct-Q4_K_M.gguf",
     "name": "Qwen2.5 14B Q4", "size_mb": 8990, "category": "large",
     "desc": "Alta calidad, necesita 12 GB VRAM"},

    # ── XL (> 10 GB) — VRAM alta ──
    {"repo": "Qwen/Qwen3-MoE-30B-A3B-GGUF", "file": "qwen3-moe-30b-a3b-q4_k_m.gguf",
     "name": "Qwen3-MoE 30B Q4", "size_mb": 18000, "category": "xl",
     "desc": "MoE, necesita 24 GB VRAM"},
]


@app.get("/models/hub")
def list_hub_models():
    """List curated GGUF models available for download."""
    return _HF_CURATED


class HubDownloadReq(BaseModel):
    repo: str
    file: str


@app.post("/models/hub/download")
def hub_download(req: HubDownloadReq):
    """Download a GGUF model from HuggingFace to the models/ directory."""
    import urllib.request
    models_dir = _HERE.parent / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    dest = models_dir / req.file

    if dest.exists():
        return {"status": "already", "path": str(dest)}

    url = f"https://huggingface.co/{req.repo}/resolve/main/{req.file}"
    try:
        urllib.request.urlretrieve(url, str(dest))
        return {"status": "downloaded", "path": str(dest), "size_mb": dest.stat().st_size // 1_000_000}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post("/oregano/{dataset}")
def oregano_test(dataset: str):
    _require_dasa()
    """Run the anti-hallucination quality audit on a dataset."""
    db = DATA_DIR / dataset
    meta_path = db / "meta.json"
    if not meta_path.exists():
        raise HTTPException(404, f"dataset desconocido: {dataset}")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    pipe = _PIPELINES.get(dataset)
    if pipe is None:
        cfg = DASAConfig(use_shard_backend=True, shard_db_path=str(db),
                         shard_num_shards=meta.get("num_shards", NUM_SHARDS))
        pipe = DASAPipeline(cfg)
        pipe.load(str(db))
        _PIPELINES[dataset] = pipe

    return run_oregano_test(pipe, dataset)


@app.get("/datasets/{dataset}/export")
def export_dataset(dataset: str):
    """Export a dataset as a .kamvex file (portable zip of shards + index + meta)."""
    import io
    import zipfile
    db = DATA_DIR / dataset
    if not (db / "meta.json").exists():
        raise HTTPException(404, f"dataset desconocido: {dataset}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in db.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(db))
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={dataset}.kamvex"},
    )


# ── OpenAI-compatible API out (Kamvex as backend for other apps) ────────────

class CompareReq(BaseModel):
    dataset: str
    query: str
    mode_a: str = "statistical"
    mode_b: str = "grounded"
    temperature: float = 0.1
    top_p: float = 0.95
    top_k: int = 40
    repeat_penalty: float = 1.0


@app.post("/compare")
def compare_models(req: CompareReq):
    _require_dasa()
    """Run the same query with two Agent B modes and return both answers for A/B comparison."""
    results = {}
    for label, mode in [("a", req.mode_a), ("b", req.mode_b)]:
        pipe = _load_pipeline(req.dataset)

        if mode == "statistical":
            pipe.agent_b._llm_callable = None
        elif mode in ("grounded", "free"):
            if _LLAMA_CONNECTOR is None:
                results[label] = {"answer": "(sin motor de inferencia)", "mode": mode, "fragments": []}
                continue
            _LLAMA_CONNECTOR.set_samplers(req.temperature, req.top_p, req.top_k, req.repeat_penalty)
            pipe.agent_b._llm_callable = _LLAMA_CONNECTOR

        fragments = pipe.agent_a.search(req.query)
        answer = pipe.agent_b.synthesize(req.query, fragments) or "(sin respuesta)"
        results[label] = {
            "answer": answer,
            "mode": mode,
            "fragments": [
                {"text": f.text, "score": float(f.score), "source_id": f.source_id}
                for f in fragments
            ],
        }
    return results


# ── OpenAI-compatible API out (Kamvex as backend for other apps) ────────────

class OAIMessage(BaseModel):
    role: str
    content: str


class OAIRequest(BaseModel):
    model: str = "kamvex"
    messages: list[OAIMessage] = []
    stream: bool = False
    temperature: float = 0.1


@app.get("/v1/models", tags=["openai-compatible"])
def v1_models():
    """List available 'models' — each dataset is a model in OpenAI terms."""
    out = []
    for d in sorted(DATA_DIR.iterdir()) if DATA_DIR.exists() else []:
        meta = d / "meta.json"
        if d.is_dir() and meta.exists():
            try:
                m = json.loads(meta.read_text(encoding="utf-8"))
                out.append({
                    "id": m["name"],
                    "object": "model",
                    "created": 0,
                    "owned_by": "kamvex",
                })
            except (json.JSONDecodeError, KeyError):
                continue
    if not out:
        out.append({"id": "kamvex", "object": "model", "created": 0, "owned_by": "kamvex"})
    return {"object": "list", "data": out}


@app.post("/v1/chat/completions", tags=["openai-compatible"])
def v1_chat_completions(req: OAIRequest):
    _require_dasa()
    """
    OpenAI-compatible endpoint. Other apps (Jan, Open WebUI, etc.) can use
    Kamvex as a backend. The `model` field maps to a dataset name.
    Supports stream=true (SSE) and stream=false (JSON).
    """
    # Extract user message and system prompt
    user_content = ""
    system_content = ""
    for msg in reversed(req.messages):
        if msg.role == "user" and not user_content:
            user_content = msg.content.strip()
        elif msg.role == "system" and not system_content:
            system_content = msg.content.strip()

    if not user_content:
        raise HTTPException(400, "No se encontró mensaje con role='user'.")

    # Map model → dataset; default to first available
    dataset_name = req.model
    if dataset_name == "kamvex" or not (DATA_DIR / dataset_name / "meta.json").exists():
        # Fall back to first available dataset
        for d in sorted(DATA_DIR.iterdir()) if DATA_DIR.exists() else []:
            if d.is_dir() and (d / "meta.json").exists():
                dataset_name = d.name
                break

    if not (DATA_DIR / dataset_name / "meta.json").exists():
        raise HTTPException(404, f"No hay datasets disponibles. Construye uno en Knowledge.")

    db = DATA_DIR / dataset_name
    meta = json.loads((db / "meta.json").read_text(encoding="utf-8"))

    pipe = _PIPELINES.get(dataset_name)
    if pipe is None:
        cfg = DASAConfig(use_shard_backend=True, shard_db_path=str(db),
                         shard_num_shards=meta.get("num_shards", NUM_SHARDS))
        pipe = DASAPipeline(cfg)
        pipe.load(str(db))
        _PIPELINES[dataset_name] = pipe

    # Apply client's system prompt to free mode
    if system_content and hasattr(pipe.agent_b, "_free_system_prompt"):
        pipe.agent_b._free_system_prompt = system_content

    # Use statistical mode by default; grounded/free if LLM is connected
    if _LLAMA_CONNECTOR is not None and _LLAMA_CONNECTOR.is_alive():
        _LLAMA_CONNECTOR.set_samplers(req.temperature, 0.95, 40, 1.0)
        pipe.agent_b._llm_callable = _LLAMA_CONNECTOR
    else:
        pipe.agent_b._llm_callable = None

    fragments = pipe.agent_a.search(user_content)
    response_text = pipe.agent_b.synthesize(user_content, fragments) or \
        "No se encontró información relevante en el corpus para esta consulta."

    req_id = f"chatcmpl-kamvex-{int(time.time() * 1000)}"
    created = int(time.time())

    if req.stream:
        def _stream():
            words = response_text.split(" ")
            for i, word in enumerate(words):
                chunk_content = word + (" " if i < len(words) - 1 else "")
                chunk = {
                    "id": req_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": req.model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": chunk_content},
                        "finish_reason": None,
                    }],
                }
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            final_chunk = {
                "id": req_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": req.model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }],
            }
            yield f"data: {json.dumps(final_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            _stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return {
        "id": req_id,
        "object": "chat.completion",
        "created": created,
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": response_text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(user_content.split()),
            "completion_tokens": len(response_text.split()),
            "total_tokens": len(user_content.split()) + len(response_text.split()),
        },
        "system_fingerprint": "kamvex-local",
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data", default=None, help="datasets dir (overrides DASA_UI_DATA)")
    args = ap.parse_args()
    if args.data:
        global DATA_DIR
        DATA_DIR = Path(args.data)
        DATA_DIR.mkdir(parents=True, exist_ok=True)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
