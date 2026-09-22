"""
Build a `.kamvex` bundle (SHARD shards + IVF-PQ index + meta + source records) from a
JSON array of records, using the exact pipeline the app uses (sidecar/jobs.py) and the
GGUF MiniLM embedding engine, so the bundle is compatible with what the installed app
computes for queries.

Usage:
    python scripts/datasets/build_kamvex.py datasets-src/constitucion-peru-1993.json \
        [--profile low-ram] [--out datasets-out]
    python scripts/datasets/build_kamvex.py --all          # every datasets-src/*.json

Output: datasets-out/<id>.kamvex, datasets-out/<id>.json (source copy) and an updated
datasets-out/manifest.json with sizes and sha256 for the release / in-app catalog.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIDECAR = REPO / "sidecar"
sys.path.insert(0, str(SIDECAR))

import paths  # noqa: E402

_SIB = paths.siblings_dir()
if _SIB:
    for sib in ("DASA-main", "SHARD-main"):
        p = _SIB / sib
        if p.is_dir() and str(p) not in sys.path:
            sys.path.insert(0, str(p))

from embedding_gguf import DEFAULT_FILE, LlamaEmbeddingEngine  # noqa: E402
from jobs import BuildJob, run_build  # noqa: E402
from shard.index.ivfpq_builder import build_ivfpq  # noqa: E402
from shard.storage.shard_writer import ShardWriter  # noqa: E402

KAMVEX_FORMAT = 1


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def embedding_engine() -> LlamaEmbeddingEngine:
    server_bin = paths.llama_server_binary()
    model = Path(str(paths.models_dir() / "embeddings" / DEFAULT_FILE))
    if server_bin is None or not model.is_file():
        raise SystemExit(f"need llama-server ({server_bin}) and {model}")
    return LlamaEmbeddingEngine(server_bin, model, threads=6)


def build_one(source: Path, out_dir: Path, profile: str, engine: LlamaEmbeddingEngine) -> dict:
    dataset_id = source.stem
    meta_src = source.with_suffix(".meta.json")
    extra = json.loads(meta_src.read_text(encoding="utf-8")) if meta_src.exists() else {}
    name = dataset_id

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
        data_dir = Path(td)
        job = BuildJob()
        t0 = time.time()
        import threading
        th = threading.Thread(target=run_build, args=(job,), kwargs=dict(
            name=name, json_path=str(source), profile=profile, data_dir=data_dir, num_shards=None,
            embedding_engine=engine, shard_writer_cls=ShardWriter, build_ivfpq_fn=build_ivfpq,
            extra_meta={
                "display_name": extra.get("name"), "description": extra.get("description"),
                "language": extra.get("language", "es"), "license": extra.get("license"),
                "source_url": extra.get("source_url"), "kamvex_format": KAMVEX_FORMAT,
            }), daemon=True)
        th.start()
        last = None
        while th.is_alive() or not job.q.empty():
            try:
                ev = job.q.get(timeout=1)
            except Exception:  # noqa: BLE001
                continue
            if ev["stage"] != last or ev["stage"] == "embed":
                print(f"  [{dataset_id}] {ev['stage']:6} {ev['pct']:3}% {ev['msg']}", flush=True)
                last = ev["stage"]
            if ev["stage"] in ("done", "error"):
                break
        th.join()
        if job.error:
            raise SystemExit(f"build failed for {dataset_id}: {job.error}")
        elapsed = time.time() - t0

        db = data_dir / name
        shutil.copy2(source, db / "records.json")
        meta = json.loads((db / "meta.json").read_text(encoding="utf-8"))

        out_dir.mkdir(parents=True, exist_ok=True)
        bundle = out_dir / f"{dataset_id}.kamvex"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for f in sorted(db.rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(db).as_posix())
        shutil.copy2(source, out_dir / f"{dataset_id}.json")

    entry = {
        "id": dataset_id,
        "name": extra.get("name") or dataset_id,
        "description": extra.get("description", ""),
        "language": extra.get("language", "es"),
        "license": extra.get("license", ""),
        "source_url": extra.get("source_url", ""),
        "records": meta["n_records"],
        "profile": profile,
        "dim": meta["dim"],
        "embedding_model": meta.get("embedding_model"),
        "file": bundle.name,
        "size_bytes": bundle.stat().st_size,
        "sha256": sha256_of(bundle),
        "source_file": f"{dataset_id}.json",
        "source_size_bytes": source.stat().st_size,
        "built_at": int(time.time()),
        "build_seconds": round(elapsed, 1),
        "kamvex_format": KAMVEX_FORMAT,
    }
    print(f"  [{dataset_id}] {entry['records']} records, {entry['size_bytes'] / 1e6:.1f} MB, {elapsed:.0f}s", flush=True)
    return entry


def update_manifest(out_dir: Path, entries: list[dict]) -> Path:
    mpath = out_dir / "manifest.json"
    manifest = {"version": 1, "datasets": []}
    if mpath.exists():
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
    by_id = {d["id"]: d for d in manifest.get("datasets", [])}
    for e in entries:
        by_id[e["id"]] = e
    manifest["datasets"] = sorted(by_id.values(), key=lambda d: d["id"])
    manifest["updated_at"] = int(time.time())
    mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return mpath


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="*", help="datasets-src/<id>.json files")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--profile", default="low-ram", choices=["low-ram", "medium", "fast"])
    ap.add_argument("--out", default=str(REPO / "datasets-out"))
    args = ap.parse_args()

    sources = [Path(s) for s in args.sources]
    if args.all:
        sources = sorted(p for p in (REPO / "datasets-src").glob("*.json") if not p.name.endswith(".meta.json"))
    if not sources:
        raise SystemExit("no sources given")

    engine = embedding_engine()
    entries = []
    try:
        for src in sources:
            print(f"== {src.name}", flush=True)
            entries.append(build_one(src, Path(args.out), args.profile, engine))
    finally:
        engine.stop()
    mpath = update_manifest(Path(args.out), entries)
    print(f"manifest: {mpath}")


if __name__ == "__main__":
    main()
