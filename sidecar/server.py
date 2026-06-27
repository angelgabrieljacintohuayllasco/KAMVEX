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

from dasa.config import DASAConfig
from dasa.pipeline import DASAPipeline
from dasa.agent_a.embeddings import EmbeddingEngine
from shard.storage.shard_writer import ShardWriter
from shard.index.ivfpq_builder import build_ivfpq

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
_PIPELINES: "dict[str, DASAPipeline]" = {}
_embedding_engine = EmbeddingEngine(DASAConfig())   # model loads lazily on first use
_LLAMA_CONNECTOR: LlamaCppConnector | None = None


# ── Models ──────────────────────────────────────────────────────────────────
class BuildReq(BaseModel):
    name: str
    json_path: str
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


@app.post("/datasets/build")
def build_dataset(req: BuildReq):
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
                    embedding_engine=_embedding_engine,
                    shard_writer_cls=ShardWriter, build_ivfpq_fn=build_ivfpq),
        daemon=True,
    ).start()
    return {"job_id": jid}


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


@app.get("/inference/metrics")
def inference_metrics():
    """Fetch live metrics from llama-server (tokens/s, active slots, etc.)."""
    if _LLAMA_CONNECTOR is None:
        return {"connected": False, "active_slots": 0, "total_decoded": 0, "slots": []}
    return {"connected": True, **_LLAMA_CONNECTOR.get_metrics()}


# ── HuggingFace model hub (curated GGUF list) ──────────────────────────────

_HF_CURATED = [
    {"repo": "Qwen/Qwen2.5-0.5B-Instruct-GGUF", "file": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
     "name": "Qwen2.5 0.5B Q4", "size_mb": 400, "desc": "Ultralight, ideal for CPU/low-RAM"},
    {"repo": "Qwen/Qwen2.5-1.5B-Instruct-GGUF", "file": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
     "name": "Qwen2.5 1.5B Q4", "size_mb": 1000, "desc": "Small, fast, good quality"},
    {"repo": "Qwen/Qwen2.5-3B-Instruct-GGUF", "file": "qwen2.5-3b-instruct-q4_k_m.gguf",
     "name": "Qwen2.5 3B Q4", "size_mb": 2000, "desc": "Balanced quality/speed"},
    {"repo": "Qwen/Qwen2.5-7B-Instruct-GGUF", "file": "qwen2.5-7b-instruct-q4_k_m.gguf",
     "name": "Qwen2.5 7B Q4", "size_mb": 4500, "desc": "High quality, needs GPU or 16GB RAM"},
    {"repo": "Qwen/Qwen3-MoE-30B-A3B-GGUF", "file": "qwen3-moe-30b-a3b-q4_k_m.gguf",
     "name": "Qwen3-MoE 30B Q4", "size_mb": 18000, "desc": "MoE, needs 24GB VRAM"},
    {"repo": "google/gemma-3-4b-it-GGUF", "file": "gemma-3-4b-it-q4_k_m.gguf",
     "name": "Gemma 3 4B Q4", "size_mb": 2600, "desc": "Google, good multilingual"},
    {"repo": "meta-llama/Llama-3.2-3B-Instruct-GGUF", "file": "Llama-3.2-3B-Instruct-Q4_K_M.gguf",
     "name": "Llama 3.2 3B Q4", "size_mb": 2000, "desc": "Meta, balanced"},
    {"repo": "TheBloke/TinyLlama-1.1B-Chat-v1.0-GGUF", "file": "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf",
     "name": "TinyLlama 1.1B Q4", "size_mb": 700, "desc": "Minimal, for testing"},
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
