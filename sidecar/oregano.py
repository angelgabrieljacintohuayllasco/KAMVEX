"""
Oregano Test — anti-hallucination quality audit for DASA datasets.

Runs a set of test queries through the DASA pipeline and checks whether
forbidden terms (terms NOT present in the corpus) appear in the output.
This is the differential feature: no other desktop LLM app audits quality.

The canonical "Oregano Test" from DASA: if a recipe dataset entry omits
"oregano" and the query asks for that recipe, "oregano" should NOT appear
in the answer. If it does, that's a hallucination.
"""

import json
from pathlib import Path


def run_oregano_test(pipeline, dataset_name: str) -> dict:
    """
    Run the anti-hallucination test suite on a dataset.

    Auto-generates test cases from the dataset records by:
    1. Picking queries that should match specific records
    2. Selecting terms that are NOT in the corpus as "forbidden"
    3. Checking that the pipeline output doesn't contain forbidden terms

    Returns a result dict with score 0-100, passed/total, hallucinations count.
    """
    db_path = Path(pipeline.agent_a._db_path) if hasattr(pipeline.agent_a, '_db_path') else None

    # Collect all vocabulary from the dataset to identify forbidden terms
    corpus_text = _collect_corpus_text(pipeline)
    corpus_words = set(_tokenize(corpus_text))

    # Common cooking/herb terms that are likely NOT in a small dataset
    # This is the "oregano" principle: terms that sound plausible but aren't in the corpus
    common_forbidden = [
        "oregano", "tomillo", "romero", "albahaca", "cilantro",
        "pimentón", "comino", "cúrcuma", "azafrán", "wasabi",
    ]

    # Filter to terms that are NOT in the corpus (these are the real forbidden terms)
    forbidden_terms = [t for t in common_forbidden if t.lower() not in corpus_words]

    # If all common terms are in corpus, use synthetic forbidden terms
    if not forbidden_terms:
        forbidden_terms = ["zzzfake_ingredient_1", "zzzfake_ingredient_2"]

    # Generate test queries from the dataset
    test_cases = _generate_test_cases(pipeline, forbidden_terms)

    if not test_cases:
        return {
            "dataset": dataset_name,
            "score": 100,
            "total": 0,
            "passed": 0,
            "hallucinations": 0,
            "details": [],
        }

    results = []
    hallucinations = 0

    for case in test_cases:
        query = case["query"]
        forbidden = case["forbidden"]

        # Run through the pipeline in statistical mode (the anti-hallucination mode)
        pipeline.agent_b._llm_callable = None
        fragments = pipeline.agent_a.search(query)
        answer = pipeline.agent_b.synthesize(query, fragments) or ""

        # Check if any forbidden term appears in the answer
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


def _collect_corpus_text(pipeline) -> str:
    """Collect all text from the pipeline's cached fragments/pipeline."""
    # Try to read the raw records from the SHARD DB
    try:
        from shard.storage.mmap_reader import MMapReader
        db_path = pipeline.agent_a._shard_db_path if hasattr(pipeline.agent_a, '_shard_db_path') else None
        if db_path is None:
            # Try to get it from the config
            db_path = pipeline.agent_a._cfg.shard_db_path if hasattr(pipeline.agent_a, '_cfg') else None

        if db_path and Path(db_path).exists():
            meta_path = Path(db_path) / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                num_shards = meta.get("num_shards", 64)

                texts = []
                reader = MMapReader(str(db_path), num_shards=num_shards)
                # We can't easily iterate all keys, so use the embedding cache keys
                keys_path = Path(db_path) / "embedding_keys.json"
                if keys_path.exists():
                    keys = json.loads(keys_path.read_text(encoding="utf-8"))
                    for key in keys[:500]:  # sample first 500 for speed
                        val = reader.find(key)
                        if val:
                            texts.append(val)
                reader.close()
                return " ".join(texts)
    except Exception:
        pass

    # Fallback: use whatever fragments we can get from a simple search
    try:
        fragments = pipeline.agent_a.search("a b c d e f g h i j k l m n o p")
        return " ".join(f.text for f in fragments)
    except Exception:
        return ""


def _tokenize(text: str) -> set[str]:
    """Split text into lowercase word tokens."""
    import re
    return set(re.findall(r'\w+', text.lower()))


def _generate_test_cases(pipeline, forbidden_terms: list[str]) -> list[dict]:
    """Generate test queries from the dataset."""
    test_cases = []

    # Get some sample queries by reading the dataset records
    try:
        from shard.storage.mmap_reader import MMapReader
        db_path = pipeline.agent_a._shard_db_path if hasattr(pipeline.agent_a, '_shard_db_path') else None
        if db_path is None:
            db_path = pipeline.agent_a._cfg.shard_db_path if hasattr(pipeline.agent_a, '_cfg') else None

        if db_path and Path(db_path).exists():
            meta_path = Path(db_path) / "meta.json"
            if meta_path.exists():
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                num_shards = meta.get("num_shards", 64)

                reader = MMapReader(str(db_path), num_shards=num_shards)
                keys_path = Path(db_path) / "embedding_keys.json"
                if keys_path.exists():
                    keys = json.loads(keys_path.read_text(encoding="utf-8"))
                    # Take up to 5 sample records to generate queries
                    for key in keys[:5]:
                        val = reader.find(key)
                        if val:
                            record = json.loads(val)
                            # Generate a query from the record's key field
                            for field in ("lemma", "term", "title", "name"):
                                if record.get(field):
                                    query = f"¿Qué es {record[field]}?"
                                    test_cases.append({
                                        "query": query,
                                        "forbidden": forbidden_terms[:3],  # check first 3 forbidden terms
                                    })
                                    break
                reader.close()
    except Exception:
        pass

    # If we couldn't generate from records, add a generic test
    if not test_cases:
        test_cases.append({
            "query": "test query",
            "forbidden": forbidden_terms[:3],
        })

    return test_cases
