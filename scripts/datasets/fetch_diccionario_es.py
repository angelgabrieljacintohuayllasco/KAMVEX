"""
Diccionario español (66k lemas) — exported from the author's DASA SHARD database.

Source: ../DASA-main/data/spanish_bff_shard (records {"id","lemma","definition"}).
The definitions were generated for the DASA project (Apache 2.0). One record per lemma.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from common import REPO, clean_text, log, save_records

DASA_DB = REPO.parent / "DASA-main" / "data" / "spanish_bff_shard"
SHARD_ROOT = REPO.parent / "SHARD-main"


def main() -> None:
    sys.path.insert(0, str(SHARD_ROOT))
    from shard.storage.mmap_reader import MMapReader  # noqa: E402

    keys = json.loads((DASA_DB / "embedding_keys.json").read_text(encoding="utf-8"))
    meta = json.loads((DASA_DB / "index.meta.json").read_text(encoding="utf-8"))
    num_shards = int(meta.get("num_shards", 256))
    log(f"{len(keys)} keys, {num_shards} shards")

    records: list[dict] = []
    missing = 0
    with MMapReader(str(DASA_DB), num_shards=num_shards) as reader:
        for i, key in enumerate(keys):
            raw = reader.find(key)
            if not raw:
                missing += 1
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                missing += 1
                continue
            lemma = clean_text(str(rec.get("lemma") or key))
            definition = clean_text(str(rec.get("definition") or ""))
            if not lemma or len(definition) < 10:
                missing += 1
                continue
            records.append({"id": rec.get("id") or f"lemma-{i}", "lemma": lemma, "definition": definition})
            if (i + 1) % 10000 == 0:
                log(f"  {i + 1}/{len(keys)}")
    log(f"missing/invalid: {missing}")
    if len(records) < 60000:
        raise SystemExit(f"only {len(records)} records read")
    save_records("diccionario-es", records, {
        "name": "Diccionario español (66 mil lemas)",
        "description": "Definiciones breves en español de 66 mil lemas, del proyecto DASA. Ideal para consultas «¿qué significa X?» con respuesta exacta.",
        "language": "es",
        "license": "Apache 2.0 (datos del proyecto DASA, definiciones generadas)",
        "source_url": "https://github.com/angelgabrieljacintohuayllasco/DASA",
    })


if __name__ == "__main__":
    main()
