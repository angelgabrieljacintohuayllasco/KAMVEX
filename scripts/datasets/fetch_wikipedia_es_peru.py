"""
Wikipedia en español — Perú (introducciones de artículos).

Uses the MediaWiki search generator + TextExtracts (intro only, plain text).
License: CC BY-SA 4.0 (attribution: Wikipedia contributors; each record keeps its URL).
"""

from __future__ import annotations

import time
import urllib.parse

from common import clean_text, http_json, log, save_records

API = "https://es.wikipedia.org/w/api.php"
QUERIES = [
    "Perú", "departamento del Perú", "provincia del Perú", "distrito del Perú", "ciudad del Perú",
    "historia del Perú", "cultura del Perú", "gastronomía peruana", "río del Perú", "cordillera Perú",
    "presidente del Perú", "sitio arqueológico Perú", "parque nacional Perú", "universidad del Perú",
    "festividad Perú", "música peruana", "escritor peruano", "economía del Perú", "guerra Perú",
    "imperio incaico", "virreinato del Perú", "independencia del Perú", "fútbol peruano",
    "reserva nacional Perú", "lago Perú", "isla Perú", "volcán Perú", "pueblo indígena Perú",
    "plato peruano", "bebida peruana", "danza peruana", "museo Perú", "catedral Perú",
    "región Perú", "Lima", "Cusco", "Arequipa", "Trujillo Perú", "Piura", "Iquitos",
]
MAX_PAGES = 2500
MIN_CHARS = 200
PER_REQUEST = 20  # TextExtracts cap when exintro is used


def search_pages(query: str, seen: set[int], records: list[dict]) -> None:
    offset = 0
    while len(records) < MAX_PAGES:
        data = http_json(API, {
            "action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": PER_REQUEST,
            "gsroffset": offset, "gsrnamespace": 0, "prop": "extracts|info", "exintro": 1,
            "explaintext": 1, "exlimit": PER_REQUEST, "inprop": "url", "format": "json", "formatversion": 2,
        })
        pages = data.get("query", {}).get("pages", [])
        for p in pages:
            pid = p.get("pageid")
            extract = clean_text(p.get("extract") or "")
            if not pid or pid in seen or len(extract) < MIN_CHARS:
                continue
            seen.add(pid)
            records.append({
                "id": f"wp-{pid}",
                "title": p["title"],
                "content": extract,
                "source_url": p.get("fullurl") or f"https://es.wikipedia.org/?curid={pid}",
            })
        cont = data.get("continue", {}).get("gsroffset")
        if cont is None or offset >= 200:
            break
        offset = cont
        time.sleep(0.2)


def main() -> None:
    seen: set[int] = set()
    records: list[dict] = []
    for q in QUERIES:
        before = len(records)
        search_pages(q, seen, records)
        log(f"{q!r}: +{len(records) - before} (total {len(records)})")
        if len(records) >= MAX_PAGES:
            break
    records.sort(key=lambda r: r["title"].lower())
    save_records("wikipedia-es-peru", records, {
        "name": "Wikipedia en español — Perú",
        "description": "Introducciones de artículos de Wikipedia en español sobre el Perú: geografía, historia, cultura, gastronomía, personajes e instituciones.",
        "language": "es",
        "license": "CC BY-SA 4.0 — contribuyentes de Wikipedia (cada registro enlaza su artículo)",
        "source_url": "https://es.wikipedia.org/",
        "queries": QUERIES,
    })
    _ = urllib.parse  # keep import explicit for future URL building


if __name__ == "__main__":
    main()
