"""
Junta las corridas de `prove_agent_b.py` en un informe comparativo.

Uso:
    python scripts/qa/summarize_agent_b.py docs/benchmarks/2026-09-26-agente-b-*.json \
        --out docs/benchmarks/2026-09-26-agente-a-mas-b.md
"""

from __future__ import annotations

import argparse
import glob
import json
import time
from pathlib import Path

REFUSAL = "no cubre este tema"


def classify(turn: dict) -> str:
    """Qué pasó en este turno: redactó el LLM, se frenó el guardarraíl, o se negó."""
    b = turn["agent_a_b"]
    meta = b.get("meta", {})
    answer = (b.get("answer") or "").lower()
    if REFUSAL in answer:
        return "negó"
    if meta.get("fallback"):
        return "guardarraíl"
    if meta.get("engine") == "llm":
        return "redactó"
    return "otro"


def stats(runs: dict[str, list]) -> list[dict]:
    rows = []
    for label, convs in runs.items():
        turns = [t for c in convs for t in c["results"]]
        kinds = [classify(t) for t in turns]
        covs = [t["agent_a_b"]["meta"]["coverage"] for t in turns
                if isinstance(t["agent_a_b"].get("meta", {}).get("coverage"), float)]
        picked = sum(1 for t in turns if t["agent_a_b"].get("meta", {}).get("picked"))
        ms = [t["agent_a_b"].get("ms", 0) for t in turns]
        rows.append({
            "modelo": label,
            "turnos": len(turns),
            "redactó": kinds.count("redactó"),
            "guardarraíl": kinds.count("guardarraíl"),
            "negó": kinds.count("negó"),
            "candidato elegido": picked,
            "cobertura media": round(sum(covs) / len(covs), 3) if covs else None,
            "latencia mediana (ms)": sorted(ms)[len(ms) // 2] if ms else 0,
        })
    return rows


def table(rows: list[dict]) -> str:
    if not rows:
        return ""
    cols = list(rows[0])
    out = ["| " + " | ".join(cols) + " |",
           "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows:
        out.append("| " + " | ".join("—" if r[c] is None else str(r[c]) for c in cols) + " |")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    files = sorted({p for pat in args.inputs for p in glob.glob(pat)})
    runs: dict[str, list] = {}
    reports: dict[str, str] = {}
    for f in files:
        p = Path(f)
        md = p.with_suffix(".md")
        label = p.stem.replace("2026-09-26-agente-b-", "")
        if md.exists():
            first = md.read_text(encoding="utf-8").splitlines()[0]
            label = first.removeprefix("# Agente A + Agente B con ").strip() or label
        runs[label] = json.loads(p.read_text(encoding="utf-8"))
        reports[label] = md.name

    rows = stats(runs)
    L = ["# Agente A + Agente B: la prueba", "",
         f"Medido el {time.strftime('%Y-%m-%d')} sobre la pila real (sidecar + llama-server + "
         "corpus instalados desde `.kamvex`), en CPU con 4 hilos.", "",
         "Las ocho preguntas son las que el usuario escribió en la app y que solo devolvían "
         "el texto crudo del Agente A. Cada turno se hace dos veces con el mismo historial: "
         "en **Exacto** (solo Agente A) y en **Anclado** (Agente A propone, Agente B redacta).", "",
         "## Qué hizo el LLM en cada turno", "",
         table(rows), "",
         "- **redactó**: Agente B eligió un candidato y escribió la respuesta. Es lo que faltaba.",
         "- **guardarraíl**: el LLM se salió del corpus y se devolvió la fuente. No es un fallo: "
         "es el sistema negándose a que un modelo de 1-2 B invente.",
         "- **negó**: el LLM dijo que los candidatos no responden la pregunta.",
         "- **cobertura media**: fracción del vocabulario de la respuesta que está en el corpus.", "",
         "## Qué cambió respecto a las capturas", "", ]

    # Ejemplo concreto: el primer turno de cada modelo.
    for label, convs in runs.items():
        t = convs[0]["results"][0]
        L += [f"**{label}** · «{t['query']}»", "",
              f"- Exacto (Agente A): {' '.join(t['agent_a']['answer'].split())[:200]}",
              f"- Anclado (A+B): {' '.join(t['agent_a_b']['answer'].split())[:200]}", ""]

    L += ["## Detalle turno a turno", ""]
    for label, name in reports.items():
        L.append(f"- [{label}]({name})")
    L += ["", "## Cómo reproducirlo", "", "```", "python scripts/qa/prove_agent_b.py \\",
          "    --model sidecar/models/gemma-2-2b-it-Q4_K_M.gguf \\",
          "    --label \"Gemma 2 2B\" --out docs/benchmarks/agente-b-gemma2b.md", "```", ""]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"informe: {out}")
    print(table(rows))


if __name__ == "__main__":
    main()
