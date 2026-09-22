"""
Expert benchmark — does the expert profile actually answer better than the bare model?

For each case (question + terms the right answer must contain) it asks three ways:

    expert     POST /experts/{id}/chat   corpus + mode + prompt + samplers of the expert
    corpus     POST /chat (grounded)     same corpus, generic prompt
    modelo     POST /chat/free           the model alone, no corpus

and reports how many answers contain the expected terms, plus latency. That is the
number that backs "KAMVEX makes a small local model smarter at X".

Usage:
    python sidecar/bench_experts.py --sidecar http://127.0.0.1:PORT --experts programacion,salud
        [--out docs/benchmarks/experts-2026-09-22.md]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.request
from pathlib import Path

CASES: dict[str, list[tuple[str, list[str]]]] = {
    "programacion": [
        ("¿Qué hace functools.lru_cache?", ["caché", "cache", "memoriz", "llamadas"]),
        ("¿Qué hace json.dumps?", ["serializa", "json", "cadena", "str"]),
        ("¿Para qué sirve os.path.join?", ["une", "ruta", "componentes"]),
        ("¿Qué devuelve Array.prototype.reduce?", ["único valor", "valor único", "reductora", "acumulador"]),
        ("¿Qué hace la declaración let en JavaScript?", ["bloque", "ámbito", "variable"]),
        ("¿Qué hace itertools.chain?", ["iterador", "iterables", "consumido"]),
        ("¿Qué hace re.sub?", ["reemplaz", "patrón", "cadena"]),
        ("¿Qué es fetch() en JavaScript?", ["solicitud", "red", "promesa", "recurso"]),
        # Fine detail: a model answering from memory tends to get the exact wording wrong
        ("¿Qué parámetros acepta functools.lru_cache?", ["maxsize", "typed"]),
        ("¿Qué hace el parámetro ensure_ascii de json.dumps?", ["ascii", "escap", "no-ascii", "caracteres"]),
        ("¿Qué devuelve os.path.splitext?", ["par", "extensión", "raíz", "root", "ext"]),
        ("¿Qué hace Array.prototype.flatMap?", ["aplanar", "aplana", "map", "profundidad", "nivel"]),
    ],
    "salud": [
        ("¿Qué es la diabetes?", ["glucosa", "azúcar", "sangre"]),
        ("¿Qué es la anemia?", ["glóbulos rojos", "hemoglobina", "hierro"]),
        ("¿Qué es el asma?", ["vías respiratorias", "pulmones", "respirar"]),
        ("¿Qué es la hipertensión?", ["presión arterial", "presión", "sangre"]),
        ("¿Qué es la migraña?", ["dolor de cabeza", "cefalea", "cabeza"]),
    ],
    "leyes-peru": [
        ("¿Qué dice el Artículo 1 de la Constitución?", ["dignidad", "persona humana", "fin supremo"]),
        ("¿Qué establece el Artículo 2 sobre la igualdad?", ["igualdad", "discriminado"]),
        ("¿Qué dice el Artículo 139?", ["jurisdiccional", "justicia", "proceso"]),
    ],
    "peru": [
        ("¿Cuál es la capital del departamento de Amazonas?", ["Chachapoyas"]),
        ("¿Qué es el ceviche?", ["pescado", "plato", "limón"]),
        ("¿Qué es Machu Picchu?", ["inca", "ciudadela", "Cusco", "santuario"]),
    ],
    "lengua": [
        ("¿Qué significa efímero?", ["breve", "poco tiempo", "pasajero"]),
        ("¿Qué significa abanico?", ["aire", "instrumento", "abanicar"]),
    ],
}


def http(method: str, url: str, body: dict | None = None, timeout: float = 900):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def hit(answer: str, expected: list[str]) -> bool:
    a = answer.lower()
    return any(e.lower() in a for e in expected)


def run(base: str, expert_id: str, cases: list[tuple[str, list[str]]], datasets: list[str]) -> dict:
    rows = []
    for q, expected in cases:
        row = {"q": q, "expected": expected}
        # 1) through the expert
        t0 = time.perf_counter()
        try:
            r = http("POST", f"{base}/experts/{expert_id}/chat", {"expert": expert_id, "query": q, "max_tokens": 220})
            row["expert"] = {"answer": r["answer"], "hit": hit(r["answer"], expected),
                             "ms": round((time.perf_counter() - t0) * 1000), "meta": r.get("meta", {})}
        except Exception as e:  # noqa: BLE001
            row["expert"] = {"answer": f"ERROR {e}", "hit": False, "ms": 0, "meta": {}}
        # 2) same corpus, generic grounded prompt
        if datasets:
            t0 = time.perf_counter()
            try:
                r = http("POST", f"{base}/chat", {"dataset": datasets[0], "query": q,
                                                  "agent_b_mode": "grounded", "max_tokens": 220})
                row["corpus"] = {"answer": r["answer"], "hit": hit(r["answer"], expected),
                                 "ms": round((time.perf_counter() - t0) * 1000)}
            except Exception as e:  # noqa: BLE001
                row["corpus"] = {"answer": f"ERROR {e}", "hit": False, "ms": 0}
        # 3) the model alone
        t0 = time.perf_counter()
        try:
            r = http("POST", f"{base}/chat/free", {"query": q, "max_tokens": 220, "temperature": 0.0})
            row["modelo"] = {"answer": r["answer"], "hit": hit(r["answer"], expected),
                             "ms": round((time.perf_counter() - t0) * 1000)}
        except Exception as e:  # noqa: BLE001
            row["modelo"] = {"answer": f"ERROR {e}", "hit": False, "ms": 0}
        rows.append(row)
        marks = "".join("+" if row.get(k, {}).get("hit") else "." for k in ("expert", "corpus", "modelo"))
        print(f"  [{marks}] {q[:60]}", file=sys.stderr, flush=True)
    return {"expert": expert_id, "rows": rows}


def summarize(result: dict) -> dict:
    out = {}
    for key in ("expert", "corpus", "modelo"):
        rows = [r[key] for r in result["rows"] if key in r]
        if not rows:
            continue
        out[key] = {
            "hits": sum(r["hit"] for r in rows),
            "n": len(rows),
            "p50_ms": statistics.median([r["ms"] for r in rows]) if rows else 0,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sidecar", required=True)
    ap.add_argument("--experts", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--json", default="")
    ap.add_argument("--label", default="")
    args = ap.parse_args()
    base = args.sidecar.rstrip("/")

    catalog = {e["id"]: e for e in http("GET", f"{base}/experts")["experts"]}
    wanted = [e.strip() for e in args.experts.split(",") if e.strip()] or list(catalog)
    results = []
    for eid in wanted:
        e = catalog.get(eid)
        if not e:
            print(f"skip {eid}: unknown", file=sys.stderr)
            continue
        if e["status"]["missing_datasets"]:
            print(f"skip {eid}: missing {e['status']['missing_datasets']}", file=sys.stderr)
            continue
        cases = CASES.get(eid)
        if not cases:
            continue
        print(f"== {e['name']}", file=sys.stderr, flush=True)
        r = run(base, eid, cases, e["status"]["installed_datasets"])
        r["name"] = e["name"]
        r["summary"] = summarize(r)
        results.append(r)

    lines = [f"# KAMVEX — expertos vs. modelo solo{(' — ' + args.label) if args.label else ''}", "",
             "`experto` = corpus + modo + prompt + samplers del experto · `corpus` = mismo corpus con prompt genérico · `modelo` = el LLM solo.", "",
             "| experto | casos | experto | corpus | modelo | p50 experto |", "|---|---|---|---|---|---|"]
    for r in results:
        s = r["summary"]
        lines.append(
            f"| {r['name']} | {s['expert']['n']} | {s['expert']['hits']}/{s['expert']['n']} | "
            f"{s.get('corpus', {}).get('hits', '—')}/{s.get('corpus', {}).get('n', '—')} | "
            f"{s['modelo']['hits']}/{s['modelo']['n']} | {s['expert']['p50_ms']:.0f} ms |")
    lines.append("")
    for r in results:
        lines.append(f"## {r['name']}")
        lines.append("")
        for row in r["rows"]:
            mark = lambda k: "✅" if row.get(k, {}).get("hit") else "❌"  # noqa: E731
            lines.append(f"**{row['q']}**")
            lines.append(f"- {mark('expert')} experto: {row['expert']['answer'][:220]}")
            if "corpus" in row:
                lines.append(f"- {mark('corpus')} corpus: {row['corpus']['answer'][:220]}")
            lines.append(f"- {mark('modelo')} modelo solo: {row['modelo']['answer'][:220]}")
            lines.append("")
    md = "\n".join(lines)
    print(md)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8")
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
