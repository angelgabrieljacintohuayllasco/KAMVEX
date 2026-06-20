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


# ── Models ──────────────────────────────────────────────────────────────────
class BuildReq(BaseModel):
    name: str
    json_path: str
    profile: str = "low-ram"


class ChatReq(BaseModel):
    dataset: str
    query: str


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
        raise HTTPException(404, f"JSON no encontrado: {req.json_path}")
    if req.profile not in ("low-ram", "medium", "fast"):
        raise HTTPException(400, f"perfil inválido: {req.profile}")
    job = BuildJob()
    jid = uuid.uuid4().hex
    _JOBS[jid] = job
    _PIPELINES.pop(req.name, None)   # invalidate any cached pipeline for this name
    threading.Thread(
        target=run_build, args=(job,),
        kwargs=dict(name=req.name, json_path=req.json_path, profile=req.profile,
                    data_dir=DATA_DIR, num_shards=NUM_SHARDS,
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
    answer = pipe.agent_b.synthesize(req.query, fragments) or \
        "No se encontró información relevante en el corpus para esta consulta."
    return {
        "answer": answer,
        "fragments": [
            {"text": f.text, "score": float(f.score), "source_id": f.source_id}
            for f in fragments
        ],
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
