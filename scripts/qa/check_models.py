"""
Comprueba que cada modelo del catálogo se puede descargar de verdad.

Una entrada con el nombre de fichero mal puesta no se nota hasta que un usuario pulsa
«instalar» y recibe un 404. Esto pregunta por cada `repo`/`file` del catálogo de la UI y
del de expertos, y dice cuáles no existen, cuáles piden autenticación y cuánto pesan de
verdad frente a lo que declara el catálogo.

    python scripts/qa/check_models.py            # todo
    python scripts/qa/check_models.py --fix-size # además corrige los tamaños declarados
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
UI_CATALOG = REPO / "src" / "catalog" / "models.local.ts"
EXPERTS_CATALOG = REPO / "sidecar" / "experts_catalog.json"
TIMEOUT = 25

# Margen: los catálogos declaran tamaños redondeados, no el byte exacto.
SIZE_TOLERANCE = 0.18


def ui_models() -> list[dict]:
    """Los modelos del catálogo de la UI, leídos del TypeScript sin ejecutarlo."""
    texto = UI_CATALOG.read_text(encoding="utf-8")
    out = []
    for linea in texto.splitlines():
        if "repo:" not in linea or "file:" not in linea:
            continue
        campos = {}
        for clave in ("id", "repo", "file"):
            m = re.search(rf'\b{clave}:\s*"([^"]+)"', linea)
            if m:
                campos[clave] = m.group(1)
        m = re.search(r"\bsizeMb:\s*(\d+)", linea)
        if m:
            campos["size_mb"] = int(m.group(1))
        if {"id", "repo", "file"} <= campos.keys():
            campos["origen"] = "ui"
            out.append(campos)
    return out


def expert_models() -> list[dict]:
    data = json.loads(EXPERTS_CATALOG.read_text(encoding="utf-8"))
    out = []
    for e in data.get("experts", []):
        for m in e.get("models", []):
            if m.get("repo") and m.get("file"):
                out.append({"id": m["id"], "repo": m["repo"], "file": m["file"],
                            "size_mb": m.get("size_mb"), "origen": f"experto:{e['id']}"})
    return out


def check(m: dict) -> dict:
    url = f"https://huggingface.co/{m['repo']}/resolve/main/{m['file']}"
    req = urllib.request.Request(url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            tam = r.headers.get("x-linked-size") or r.headers.get("Content-Length")
            return {**m, "estado": 200, "bytes": int(tam) if tam else None}
    except urllib.error.HTTPError as e:
        return {**m, "estado": e.code, "bytes": None}
    except Exception as e:  # noqa: BLE001
        return {**m, "estado": 0, "bytes": None, "error": str(e)[:80]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fix-size", action="store_true",
                    help="corrige en el catálogo los tamaños que no cuadran")
    args = ap.parse_args()

    modelos = ui_models() + expert_models()
    vistos, unicos = set(), []
    for m in modelos:
        clave = (m["repo"], m["file"])
        if clave not in vistos:
            vistos.add(clave)
            unicos.append(m)

    print(f"Comprobando {len(unicos)} modelos ({len(modelos)} entradas en total)...\n")
    with ThreadPoolExecutor(max_workers=8) as pool:
        res = list(pool.map(check, unicos))

    rotos = [r for r in res if r["estado"] != 200]
    desajustados = []
    for r in res:
        if r["estado"] != 200 or not r.get("bytes") or not r.get("size_mb"):
            continue
        real = r["bytes"] / 1e6
        if abs(real - r["size_mb"]) / max(r["size_mb"], 1) > SIZE_TOLERANCE:
            desajustados.append((r, round(real)))

    for r in sorted(res, key=lambda x: (x["estado"] != 200, x["id"])):
        real = f"{r['bytes'] / 1e6:8.0f} MB" if r.get("bytes") else "        ?"
        marca = "ok " if r["estado"] == 200 else f"{r['estado']:<3}"
        print(f"  [{marca}] {r['id']:<26} {real}  {r['repo']}/{r['file']}")

    print()
    if rotos:
        print(f"{len(rotos)} modelo(s) NO se pueden descargar:")
        for r in rotos:
            motivo = {401: "pide autenticación", 403: "acceso restringido",
                      404: "no existe"}.get(r["estado"], r.get("error", "sin respuesta"))
            print(f"  - {r['id']} ({r['origen']}): {motivo}")
    if desajustados:
        print(f"{len(desajustados)} tamaño(s) declarados no cuadran:")
        for r, real in desajustados:
            print(f"  - {r['id']}: catálogo {r['size_mb']} MB, real {real} MB")
        if args.fix_size:
            _fix_sizes(desajustados)

    if not rotos and not desajustados:
        print("Todo el catálogo se puede descargar y los tamaños cuadran.")
    return 1 if rotos else 0


def _fix_sizes(desajustados) -> None:
    ui = UI_CATALOG.read_text(encoding="utf-8")
    exp = EXPERTS_CATALOG.read_text(encoding="utf-8")
    for r, real in desajustados:
        ui = re.sub(rf'(\bid: "{re.escape(r["id"])}".*?\bsizeMb:\s*)\d+',
                    rf"\g<1>{real}", ui, flags=re.S)
        exp = re.sub(rf'("id": "{re.escape(r["id"])}".*?"size_mb":\s*)\d+',
                     rf"\g<1>{real}", exp, flags=re.S)
    UI_CATALOG.write_text(ui, encoding="utf-8")
    EXPERTS_CATALOG.write_text(exp, encoding="utf-8")
    print("  tamaños corregidos en los dos catálogos")


if __name__ == "__main__":
    sys.exit(main())
