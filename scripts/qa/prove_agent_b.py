"""
Prueba que el Agente B (el LLM) funciona, sobre la pila real y con las preguntas que fallaron.

Replica las conversaciones de las capturas del usuario contra `/experts/{id}/chat`, con
historial, y para cada turno guarda las dos respuestas lado a lado:

    Exacto   (mode=statistical) → solo Agente A: el registro del corpus, en crudo.
    Anclado  (mode=grounded)    → Agente A + Agente B: el LLM elige un candidato y redacta.

Así se ve, turno a turno, qué aporta el LLM: qué predictores votaron, si la pregunta se
reescribió contra la conversación, qué candidato usó la respuesta y si el guardarraíl la aceptó.

Uso (desde la raíz del repo, dentro del venv):
    python scripts/qa/prove_agent_b.py --model sidecar/models/gemma-2-2b-it-Q4_K_M.gguf \
        --label "Gemma 2 2B" --out docs/benchmarks/2026-09-26-agente-b-gemma.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from stack import Stack, http  # noqa: E402

# Las conversaciones tal como las escribió el usuario en la app (acentos incluidos y omitidos).
CONVERSATIONS = [
    {
        "expert": "lengua",
        "title": "Lengua española — diccionario",
        "turns": ["explicame que es Pene",
                  "dame mas explicacion",
                  "hazme una explicacion muy larga de la palabra pene",
                  "dame una explicacion detallada"],
    },
    {
        "expert": "leyes-peru",
        "title": "Leyes del Perú — Constitución de 1993",
        "turns": ["explicame mis derechos",
                  "y el articulo 35?",
                  "¿Qué dice el Artículo 2?",
                  "dame más explicación"],
    },
]


def ask(base: str, expert: str, query: str, mode: str, history: list[dict]) -> dict:
    t0 = time.perf_counter()
    try:
        r = http("POST", f"{base}/experts/{expert}/chat",
                 {"expert": expert, "query": query, "mode": mode, "history": history})
    except Exception as e:  # noqa: BLE001
        return {"answer": f"<<ERROR: {e}>>", "meta": {}, "fragments": [], "ms": 0}
    r["ms"] = round((time.perf_counter() - t0) * 1000)
    return r


def run(base: str) -> list[dict]:
    out = []
    for conv in CONVERSATIONS:
        history: list[dict] = []
        turns = []
        for query in conv["turns"]:
            # Agente A solo: el mismo historial, pero sin LLM.
            solo = ask(base, conv["expert"], query, "statistical", history)
            # Agente A + Agente B.
            full = ask(base, conv["expert"], query, "grounded", history)
            turns.append({"query": query, "agent_a": solo, "agent_a_b": full,
                          "decision": (full.get("meta") or {}).get("decision")})
            # La conversación avanza con la respuesta buena, que es la que ve el usuario.
            history = history + [{"role": "user", "content": query},
                                 {"role": "assistant", "content": full["answer"]}]
        out.append({**conv, "results": turns})
    return out


def md(results: list[dict], label: str, model: Path, backend: str) -> str:
    L = [f"# Agente A + Agente B con {label}", "",
         f"- Modelo: `{model.name}` ({backend})",
         f"- Fecha: {time.strftime('%Y-%m-%d %H:%M')}",
         "- Pila real: sidecar + llama-server + corpus instalados desde `.kamvex`.",
         "- **Exacto** = solo Agente A (el registro del corpus). "
         "**Anclado** = Agente A propone y Agente B (el LLM) elige y redacta.", ""]
    for conv in results:
        L += [f"## {conv['title']}", ""]
        for i, t in enumerate(conv["results"], start=1):
            a, b = t["agent_a"], t["agent_a_b"]
            meta = b.get("meta", {})
            rw = meta.get("rewrite") or {}
            preds = meta.get("predictors") or {}
            votes = {}
            for ds, per in preds.items():
                for name, info in (per or {}).items():
                    votes[name] = votes.get(name, 0) + (info or {}).get("n", 0)
            L += [f"### Turno {i}: «{t['query']}»", ""]
            dec = (meta.get("decision") or {})
            if dec.get("picked") is not None:
                L.append(f"- Elegido por {dec.get('source', '?')}: opción {dec['picked'] + 1}"
                         + (f" (`{dec['key']}`)" if dec.get("key") else "")
                         + f", {dec['ms']} ms")
            if rw.get("rewritten"):
                L.append(f"- Reescrito para buscar: «{rw['topic']}» "
                         f"(la pregunta sola no tenía tema)")
            L += [f"- Predictores que propusieron: "
                  f"{', '.join(f'{k}×{v}' for k, v in sorted(votes.items())) or '—'}",
                  f"- Motor: `{meta.get('engine', '?')}`"
                  + (f", candidato elegido: #{meta.get('picked') + 1}"
                     if isinstance(meta.get("picked"), int) else "")
                  + (f", cobertura léxica {meta['coverage']:.2f}" if isinstance(meta.get("coverage"), float) else "")
                  + (f", detalle: {'amplio' if meta.get('detail') else 'breve'}"
                     if "detail" in meta else ""),
                  f"- Latencia: Exacto {a.get('ms', 0)} ms · Anclado {b.get('ms', 0)} ms", "",
                  "**Exacto (solo Agente A)**", "", "> " + _q(a.get("answer", "")), "",
                  "**Anclado (Agente A + Agente B)**", "", "> " + _q(b.get("answer", "")), ""]
            cands = b.get("fragments") or []
            if cands:
                L.append("<details><summary>Candidatos que recibió el LLM</summary>\n")
                for j, c in enumerate(cands[:4], start=1):
                    src = ", ".join(f"{k} {v}" for k, v in (c.get("predictors") or {}).items())
                    L.append(f"{j}. `{c.get('source_id')}` (score {c.get('score')}"
                             + (f"; {src}" if src else "") + ")"
                             + f" — {_q(c.get('text', ''))[:220]}")
                L += ["", "</details>", ""]
    return "\n".join(L) + "\n"


def _q(text: str) -> str:
    return " ".join((text or "").split())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--label", default=None)
    ap.add_argument("--backend", default="cpu", choices=["cpu", "vulkan", "cuda"])
    ap.add_argument("--home", default=str(REPO / "qa-home-agentb"))
    ap.add_argument("--ctx", type=int, default=4096)
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--bundles", nargs="*",
                    default=[str(REPO / "datasets-out" / "diccionario-es.kamvex"),
                             str(REPO / "datasets-out" / "constitucion-peru-1993.kamvex")])
    ap.add_argument("--out", default=None)
    ap.add_argument("--chooser", default="logit", choices=["logit", "off"],
                    help="capa de decisión entre Agente A y Agente B (SemIf sobre llama-server)")
    args = ap.parse_args()

    # El Stack hereda el entorno: así se mide con y sin electores.
    os.environ["KAMVEX_CHOOSER"] = args.chooser

    model = Path(args.model).resolve()
    if not model.is_file():
        raise SystemExit(f"modelo no encontrado: {model}")
    label = args.label or model.stem

    st = Stack(Path(args.home).resolve(), model, args.backend, args.ctx, args.threads)
    try:
        st.start_sidecar()
        home_ds = Path(args.home).resolve() / "datasets"
        pending = [Path(b) for b in args.bundles
                   if not (home_ds / Path(b).stem / "meta.json").exists()]
        if pending:
            print(f"instalando {len(pending)} corpus…", flush=True)
            st.install_bundles(pending)
        st.start_llama()
        print(f"pila lista: {st.base} · llama {st.llama_port}", flush=True)
        results = run(st.base)
    finally:
        st.stop()

    report = md(results, label, model, args.backend)
    out = Path(args.out) if args.out else None
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        (out.with_suffix(".json")).write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
        print(f"informe: {out}")
    print(report)


if __name__ == "__main__":
    main()
