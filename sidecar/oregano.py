"""
Oregano Test — anti-hallucination quality audit for DASA datasets.

Runs a set of test queries through the DASA pipeline and checks whether
forbidden terms (terms NOT present in the corpus) appear in the output.
This is the differential feature: no other desktop LLM app audits quality.

The canonical "Oregano Test" from DASA: if a recipe dataset entry omits
"oregano" and the query asks for that recipe, "oregano" should NOT appear
in the answer. If it does, that's a hallucination.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Plausible-sounding terms that a model may "helpfully" add. Only those absent
# from the corpus are used as forbidden terms for a given dataset.
COMMON_FORBIDDEN = [
    "orégano", "oregano", "tomillo", "romero", "albahaca", "cilantro",
    "pimentón", "comino", "cúrcuma", "azafrán", "wasabi", "jengibre",
    "aproximadamente", "generalmente", "probablemente", "según expertos",
    "por ejemplo", "además", "sin embargo", "importante destacar",
]
SAMPLE_RECORDS = 8          # queries generated per audit
CORPUS_SAMPLE = 500         # records read to build the corpus vocabulary
KEY_FIELDS = ("lemma", "term", "title", "name")


def run_oregano_test(pipeline, dataset_name: str) -> dict:
    """
    Run the anti-hallucination test suite on a dataset.

    Auto-generates test cases from the dataset records by:
    1. Picking queries that should match specific records
    2. Selecting terms that are NOT in the corpus as "forbidden"
    3. Checking that the pipeline output doesn't contain forbidden terms

    Returns a result dict with score 0-100, passed/total, hallucinations count.
    """
    db_path = _db_path(pipeline)
    keys = _load_keys(db_path)
    records = _read_records(db_path, keys, CORPUS_SAMPLE)

    corpus_words = set(_tokenize(" ".join(_record_text(r) for r in records)))
    forbidden_terms = [t for t in COMMON_FORBIDDEN if t.lower() not in corpus_words]
    if not forbidden_terms:
        forbidden_terms = ["zzzfake_ingredient_1", "zzzfake_ingredient_2"]

    test_cases = _generate_test_cases(records, forbidden_terms)
    if not test_cases:
        return _result(dataset_name, [], 0)

    results = []
    hallucinations = 0
    for case in test_cases:
        query = case["query"]
        forbidden = case["forbidden"]

        # Run through the pipeline in statistical mode (the anti-hallucination mode)
        pipeline.agent_b._llm_callable = None
        fragments = pipeline.agent_a.search(query)
        answer = pipeline.agent_b.synthesize(query, fragments) or ""

        answer_lower = answer.lower()
        forbidden_found = [t for t in forbidden if t.lower() in answer_lower]
        passed = len(forbidden_found) == 0
        if not passed:
            hallucinations += len(forbidden_found)

        results.append({
            "query": query,
            "forbidden": forbidden,
            "forbidden_found": forbidden_found,
            "passed": passed,
            "answer_preview": answer[:120],
        })

    return _result(dataset_name, results, hallucinations)


def _result(dataset_name: str, results: list[dict], hallucinations: int) -> dict:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    score = int((passed / total) * 100) if total > 0 else 100
    return {
        "dataset": dataset_name,
        "score": score,
        "total": total,
        "passed": passed,
        "hallucinations": hallucinations,
        "details": results,
    }


def _db_path(pipeline) -> Path | None:
    cfg = getattr(pipeline, "config", None)
    p = getattr(cfg, "shard_db_path", None)
    return Path(p) if p else None


def _load_keys(db_path: Path | None) -> list[str]:
    """Ordered record keys: keys.json (KAMVEX builds) or embedding_keys.json (legacy)."""
    if db_path is None:
        return []
    for name in ("keys.json", "embedding_keys.json"):
        f = db_path / name
        if f.exists():
            try:
                keys = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(keys, list):
                    return [str(k) for k in keys]
            except (json.JSONDecodeError, OSError):
                continue
    return []


def _read_records(db_path: Path | None, keys: list[str], limit: int) -> list[dict]:
    """Read up to `limit` raw records from the SHARD DB by key."""
    if db_path is None or not keys:
        return []
    try:
        from shard.storage.mmap_reader import MMapReader
        meta = json.loads((db_path / "meta.json").read_text(encoding="utf-8"))
        num_shards = int(meta.get("num_shards", 64))
    except Exception:  # noqa: BLE001 — no DB, no records
        return []

    out: list[dict] = []
    reader = MMapReader(str(db_path), num_shards=num_shards)
    try:
        for key in keys[:limit]:
            raw = reader.find(key)
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                rec = {"text": str(raw)}
            if isinstance(rec, dict):
                out.append(rec)
    finally:
        reader.close()
    return out


def _record_text(record: dict) -> str:
    return " ".join(str(v) for v in record.values() if v)


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase word tokens."""
    return set(re.findall(r"\w+", text.lower()))


def _generate_test_cases(records: list[dict], forbidden_terms: list[str]) -> list[dict]:
    """One '¿Qué es X?' query per sampled record (X = its key field)."""
    forbidden = forbidden_terms[:3]
    cases = []
    for rec in records[:SAMPLE_RECORDS]:
        for field in KEY_FIELDS:
            if rec.get(field):
                cases.append({"query": f"¿Qué es {rec[field]}?", "forbidden": forbidden})
                break
    if not cases:
        cases.append({"query": "test query", "forbidden": forbidden})
    return cases
