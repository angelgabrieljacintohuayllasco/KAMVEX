"""
Oregano test runner: real test cases are generated from the dataset records
(keys.json), and the statistical mode never emits forbidden terms.
"""

from __future__ import annotations

import pytest

import server
from conftest import build_dataset

pytestmark = pytest.mark.skipif(not server._DASA_AVAILABLE, reason="DASA/SHARD not importable")


def test_oregano_generates_cases_from_records(sidecar):
    build_dataset(sidecar, "demo")
    r = sidecar.post("/oregano/demo")
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["dataset"] == "demo"
    assert res["total"] >= 3, res
    assert all(d["query"].startswith("¿Qué es") for d in res["details"])
    assert all(len(d["forbidden"]) == 3 for d in res["details"])
    assert res["passed"] == res["total"]
    assert res["score"] == 100
    assert res["hallucinations"] == 0


def test_oregano_unknown_dataset_is_404(sidecar):
    assert sidecar.post("/oregano/nope").status_code == 404
