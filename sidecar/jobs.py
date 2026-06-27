"""
Dataset build job: JSON/JSONL/CSV -> embeddings -> SHARD shards -> IVF-PQ index.

Runs in a background thread and reports progress through a queue so the HTTP
layer can stream Server-Sent Events. All heavy lifting reuses DASA + SHARD;
this file only orchestrates and reports progress.
"""

import csv
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


def read_records(file_path: str) -> list[dict]:
    """Read records from a JSON array, JSONL, or CSV file."""
    p = Path(file_path)
    ext = p.suffix.lower()

    if ext == ".jsonl":
        records = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
        if not records:
            raise ValueError("El archivo JSONL no contiene registros válidos.")
        return records

    if ext == ".csv":
        records = []
        with p.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records.append(dict(row))
        if not records:
            raise ValueError("El archivo CSV no contiene registros (¿tiene cabecera?).")
        return records

    # Default: JSON array
    records = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError("El JSON debe ser un array no vacío de objetos.")
    return records


def compute_num_shards(n_records: int) -> int:
    """Auto-compute num_shards using SHARD's ShardRouter.recommended_shards."""
    from shard.core.sharding import ShardRouter
    return ShardRouter.recommended_shards(n_records)


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
        job.emit("read", 2, f"Leyendo {Path(json_path).suffix.upper()}")
        records = read_records(json_path)
        n = len(records)

        # Auto-compute num_shards if not explicitly set
        if num_shards is None or num_shards <= 0:
            num_shards = compute_num_shards(n)
            job.emit("read", 5, f"num_shards auto: {num_shards}")

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
