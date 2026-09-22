"""
Constitución Política del Perú (1993) — one record per article, from Wikisource.

Source: https://es.wikisource.org/wiki/Constitución_del_Perú_(1993)  (public domain:
official state text). Records: {"id": "art-N", "title": "Artículo N", "content": ...,
"seccion": "<título/capítulo>", "source_url": ...}.
"""

from __future__ import annotations

import re

from common import clean_text, http_json, log, save_records

API = "https://es.wikisource.org/w/api.php"
PAGE = "Constitución del Perú (1993)"
SOURCE_URL = "https://es.wikisource.org/wiki/Constituci%C3%B3n_del_Per%C3%BA_(1993)"

ART_RE = re.compile(r"^'*\s*Art[íi]culo\s+(\d+)\s*[°º]?\s*\.?\s*[-–—]*\s*'*\s*(.*)$", re.IGNORECASE)
HEADING_RE = re.compile(r"^(=+)\s*(.+?)\s*=+\s*$")
LINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
TEMPLATE_RE = re.compile(r"\{\{[^{}]*\}\}")


def wikitext(title: str) -> str:
    data = http_json(API, {"action": "parse", "page": title, "prop": "wikitext", "format": "json", "formatversion": 2})
    return data["parse"]["wikitext"]


def subpages(text: str) -> list[str]:
    return sorted({m for m in re.findall(r"\[\[(" + re.escape(PAGE) + r"/[^|\]]+)", text)})


def markup_to_text(line: str) -> str:
    line = TEMPLATE_RE.sub("", line)
    line = LINK_RE.sub(r"\1", line)
    line = line.replace("'''", "").replace("''", "")
    line = re.sub(r"<ref[^>]*>.*?</ref>", "", line)
    line = re.sub(r"<[^>]+>", "", line)
    return line.strip()


def parse_articles(text: str) -> list[dict]:
    records: list[dict] = []
    section = ""
    current: dict | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        h = HEADING_RE.match(line)
        if h:
            section = markup_to_text(h.group(2))
            continue
        m = ART_RE.match(markup_to_text(line))
        if m:
            if current and current["content"].strip():
                records.append(current)
            num = int(m.group(1))
            current = {
                "id": f"art-{num}",
                "title": f"Artículo {num}",
                "content": m.group(2).strip(),
                "seccion": section,
                "source_url": SOURCE_URL,
            }
            continue
        if current is not None:
            raw_body = line
            numbered = raw_body.startswith("#")
            body = markup_to_text(raw_body.lstrip("#*: ").strip()) if numbered or raw_body.startswith(("*", ":")) else markup_to_text(raw_body)
            if not body or body.startswith(("{|", "|", "[[Categoría", "[[Category")):
                continue
            if numbered:
                current["_n"] = current.get("_n", 0) + 1
                body = f"{current['_n']}. {body}"
            current["content"] = (current["content"] + "\n" + body).strip()
    if current and current["content"].strip():
        records.append(current)
    for r in records:
        r.pop("_n", None)
        r["content"] = clean_text(r["content"])
    return records


def main() -> None:
    root = wikitext(PAGE)
    pages = [root]
    subs = subpages(root)
    log(f"root wikitext {len(root)} chars, {len(subs)} subpages")
    for sp in subs:
        pages.append(wikitext(sp))
    records: list[dict] = []
    seen: set[str] = set()
    for text in pages:
        for r in parse_articles(text):
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            records.append(r)
    records.sort(key=lambda r: int(r["id"].split("-")[1]))
    if len(records) < 150:
        raise SystemExit(f"only {len(records)} articles parsed — check the page structure")
    save_records("constitucion-peru-1993", records, {
        "name": "Constitución Política del Perú (1993)",
        "description": "Los 206 artículos de la Constitución vigente del Perú, uno por registro, con su título y capítulo.",
        "language": "es",
        "license": "Dominio público (texto oficial del Estado peruano); transcripción de Wikisource",
        "source_url": SOURCE_URL,
    })


if __name__ == "__main__":
    main()
