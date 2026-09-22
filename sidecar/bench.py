"""
KAMVEX benchmark — measures the real stack through the sidecar HTTP API.

For every dataset it samples records, asks a question about each one and scores:

  retrieval   hit@1 / hit@5   the record itself is the top-1 / in the top-5 fragments
  statistical exact           answer equals the record text (definition datasets) or
                              contains ≥ 80 % of the record's content terms
  grounded    groundedness    lexical coverage of the LLM answer by the fragments
              fallback rate   how often the guardrail replaced the LLM answer
              recall          share of the record's content terms present in the answer
  latency     p50 / p95 ms per mode, tokens/s from llama-server metrics
  oregano     score of the built-in anti-hallucination audit

Usage:
    python sidecar/bench.py --sidecar http://127.0.0.1:PORT --datasets a,b --modes statistical,grounded
        [--n 40] [--seed 1] [--label "qwen2.5-1.5b cpu"] [--out docs/benchmarks/2026-09-22.md]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from grounding import content_terms, coverage, normalize  # noqa: E402

DEF_FIELDS = ("lemma", "term", "title", "name")
BODY_FIELDS = ("definition", "content", "text")


def http(method: str, url: str, body: dict | None = None, timeout: float = 600):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def record_key_body(rec: dict) -> tuple[str, str]:
    key = next((str(rec[f]) for f in DEF_FIELDS if rec.get(f)), "")
    body = next((str(rec[f]) for f in BODY_FIELDS if rec.get(f)), "")
    return key, body


def question_for(rec: dict, dataset: str) -> str:
    key, _ = record_key_body(rec)
    if key.lower().startswith("artículo"):
        return f"¿Qué dice el {key} de la Constitución?"
    if dataset.startswith("medline") or dataset.startswith("wikipedia"):
        return f"¿Qué es {key}?"
    return f"¿Qué significa {key}?"


def pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def p(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    i = min(len(s) - 1, int(round(q * (len(s) - 1))))
    return s[i]


def bench_dataset(base: str, dataset: str, records: list[dict], modes: list[str], n: int, rng: random.Random) -> dict:
    sample = rng.sample(records, min(n, len(records)))
    per_mode: dict[str, dict] = {}
    for mode in modes:
        hits1 = hits5 = exact = 0
        cov_vals: list[float] = []
        recall_vals: list[float] = []
        fallbacks = 0
        not_covered = 0
        lat: list[float] = []
        errors = 0
        cases = []
        for rec in sample:
            key, body = record_key_body(rec)
            q = question_for(rec, dataset)
            t0 = time.perf_counter()
            try:
                resp = http("POST", f"{base}/chat", {"dataset": dataset, "query": q, "agent_b_mode": mode, "max_tokens": 256})
            except Exception as e:  # noqa: BLE001
                errors += 1
                cases.append({"q": q, "error": str(e)[:200]})
                continue
            ms = (time.perf_counter() - t0) * 1000
            lat.append(ms)
            frags = resp.get("fragments", [])
            ids = [normalize(str(f.get("source_id") or "").split("#")[0]) for f in frags]
            nk = normalize(key)
            hit1 = bool(ids) and ids[0] == nk
            hit5 = nk in ids[:5]
            hits1 += hit1
            hits5 += hit5
            answer = resp.get("answer", "")
            meta = resp.get("meta", {})
            body_terms = content_terms(body)
            ans_terms = content_terms(answer)
            recall = (len(body_terms & ans_terms) / len(body_terms)) if body_terms else 1.0
            recall_vals.append(recall)
            is_exact = normalize(answer).strip() == normalize(f"{key}: {body}").strip() or recall >= 0.8
            exact += is_exact
            if mode == "grounded":
                cov = meta.get("coverage")
                if cov is None:
                    cov, _ = coverage(answer, [type("F", (), {"text": f["text"], "source_id": f.get("source_id")})() for f in frags])
                cov_vals.append(float(cov))
                fallbacks += bool(meta.get("fallback"))
                not_covered += "no cubre este tema" in answer.lower()
            cases.append({"q": q, "hit1": hit1, "hit5": hit5, "exact": is_exact, "recall": round(recall, 3),
                          "coverage": meta.get("coverage"), "fallback": meta.get("fallback"),
                          "engine": meta.get("engine"), "ms": round(ms), "answer": answer[:160]})
        total = max(1, len(sample) - errors)
        per_mode[mode] = {
            "n": len(sample), "errors": errors,
            "hit1": hits1 / total, "hit5": hits5 / total, "exact": exact / total,
            "recall_mean": statistics.fmean(recall_vals) if recall_vals else 0.0,
            "coverage_mean": statistics.fmean(cov_vals) if cov_vals else None,
            "fallback_rate": fallbacks / total if mode == "grounded" else None,
            "not_covered_rate": not_covered / total if mode == "grounded" else None,
            "p50_ms": p(lat, 0.5), "p95_ms": p(lat, 0.95),
            "cases": cases,
        }
    oregano = None
    try:
        oregano = http("POST", f"{base}/oregano/{dataset}")
    except Exception as e:  # noqa: BLE001
        oregano = {"error": str(e)[:200]}
    return {"dataset": dataset, "records": len(records), "modes": per_mode, "oregano": oregano}


def markdown(results: list[dict], label: str, metrics: dict | None) -> str:
    lines = [f"# KAMVEX benchmark — {label}", ""]
    if metrics:
        lines.append(f"Engine metrics at the end: {metrics.get('tokens_per_second', 0)} tok/s, "
                     f"TTFT {metrics.get('ttft_ms', 0)} ms, ctx {metrics.get('context_total', 0)}.")
        lines.append("")
    lines.append("| dataset | records | mode | n | hit@1 | hit@5 | exact/recall≥0.8 | recall | groundedness | fallback | no-cubre | p50 ms | p95 ms |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        for mode, m in r["modes"].items():
            lines.append(
                f"| {r['dataset']} | {r['records']} | {mode} | {m['n']} | {pct(m['hit1'])} | {pct(m['hit5'])} | "
                f"{pct(m['exact'])} | {pct(m['recall_mean'])} | "
                f"{pct(m['coverage_mean']) if m['coverage_mean'] is not None else '—'} | "
                f"{pct(m['fallback_rate']) if m['fallback_rate'] is not None else '—'} | "
                f"{pct(m['not_covered_rate']) if m['not_covered_rate'] is not None else '—'} | "
                f"{m['p50_ms']:.0f} | {m['p95_ms']:.0f} |")
        o = r.get("oregano") or {}
        if "score" in o:
            lines.append(f"| {r['dataset']} | | oregano | {o['total']} | | | score {o['score']} | | | | halluc. {o['hallucinations']} | | |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidecar", required=True)
    ap.add_argument("--datasets", required=True, help="comma separated dataset names")
    ap.add_argument("--modes", default="statistical,grounded")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--label", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    base = args.sidecar.rstrip("/")
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    rng = random.Random(args.seed)
    listed = {d["name"]: d for d in http("GET", f"{base}/datasets")}
    results = []
    for name in [d.strip() for d in args.datasets.split(",") if d.strip()]:
        if name not in listed:
            print(f"skip {name}: not installed", file=sys.stderr)
            continue
        rec_path = Path(listed[name]["path"]) / "records.json"
        if not rec_path.exists():
            print(f"skip {name}: no records.json", file=sys.stderr)
            continue
        records = json.loads(rec_path.read_text(encoding="utf-8"))
        print(f"== {name}: {len(records)} records", file=sys.stderr, flush=True)
        r = bench_dataset(base, name, records, modes, args.n, rng)
        for mode, m in r["modes"].items():
            print(f"   {mode:11} hit@1 {pct(m['hit1'])} hit@5 {pct(m['hit5'])} exact {pct(m['exact'])} "
                  f"recall {pct(m['recall_mean'])} ground {m['coverage_mean']} fallback {m['fallback_rate']} "
                  f"p50 {m['p50_ms']:.0f}ms", file=sys.stderr, flush=True)
        results.append(r)

    metrics = None
    try:
        metrics = http("GET", f"{base}/inference/metrics")
    except Exception:  # noqa: BLE001
        pass
    md = markdown(results, args.label or "run", metrics)
    print(md)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps({"label": args.label, "results": results, "metrics": metrics},
                                              ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
