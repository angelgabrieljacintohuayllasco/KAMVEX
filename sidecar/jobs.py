"""
Dataset build job: JSON -> embeddings -> SHARD shards -> IVF-PQ index.

Runs in a background thread and reports progress through a queue so the HTTP
layer can stream Server-Sent Events. All heavy lifting reuses DASA + SHARD;
this file only orchestrates and reports progress.
"""

import json
import queue
from pathlib import Path

import numpy as np

# Fields DASA's RetrievalAgent._record_to_text recognizes, in order.
_TEXT_FIELDS = ("lemma", "term", "title", "name", "content", "text", "definition")
_KEY_FIELDS = ("lemma", "term", "title", "name", "id")


def record_to_text(record: dict) -> str:
    """Mirror of dasa.agent_a.retrieval_agent.RetrievalAgent._record_to_text."""
    parts = [str(record[f]) for f in _TEXT_FIELDS if record.get(f)]
    return ": ".join(parts) if parts else str(record)


def _record_key(record: dict, idx: int) -> str:
    for f in _KEY_FIELDS:
        if record.get(f):
            return str(record[f])
    return f"record_{idx}"


def _unique_keys(keys):
    """Disambiguate duplicate keys so each record stays individually retrievable."""
    seen, out = {}, []
    for k in keys:
        if k in seen:
            seen[k] += 1
            out.append(f"{k}#{seen[k]}")
        else:
            seen[k] = 0
            out.append(k)
    return out


class BuildJob:
    def __init__(self):
        self.q: "queue.Queue[dict]" = queue.Queue()
        self.done = False
        self.error = None

    def emit(self, stage, pct, msg=""):
        self.q.put({"stage": stage, "pct": pct, "msg": msg})


def run_build(job: BuildJob, *, name, json_path, profile, data_dir, num_shards,
              embedding_engine, shard_writer_cls, build_ivfpq_fn):
    """Execute the full build pipeline, emitting progress on `job`."""
    try:
        job.emit("read", 2, "Leyendo JSON")
        records = json.loads(Path(json_path).read_text(encoding="utf-8"))
        if not isinstance(records, list) or not records:
            raise ValueError("El JSON debe ser un array no vacío de objetos.")
        n = len(records)

        db = Path(data_dir) / name
        db.mkdir(parents=True, exist_ok=True)

        job.emit("embed", 10, f"Calculando embeddings de {n} registros")
        texts = [record_to_text(r) for r in records]
        keys = _unique_keys([_record_key(r, i) for i, r in enumerate(records)])
        emb = np.asarray(embedding_engine.encode_batch(texts), dtype=np.float32)

        job.emit("shard", 50, "Escribiendo shards binarios")
        with shard_writer_cls(str(db), num_shards=num_shards, estimated_total_records=n) as w:
            for k, r in zip(keys, records):
                w.write(k, json.dumps(r, ensure_ascii=False))

        job.emit("index", 70, f"Construyendo índice IVF-PQ (perfil {profile})")
        build_ivfpq_fn(emb, keys, str(db / "ivf"), profile=profile)

        meta = {"name": name, "n_records": n, "profile": profile,
                "num_shards": num_shards, "dim": int(emb.shape[1])}
        (db / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
        job.emit("done", 100, "Índice listo")
    except Exception as e:  # noqa: BLE001 — report any failure to the UI
        job.error = str(e)
        job.emit("error", 100, str(e))
    finally:
        job.done = True
