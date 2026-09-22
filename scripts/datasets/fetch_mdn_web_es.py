"""
MDN Web Docs en español — JavaScript, CSS, HTML y Web APIs.

Source: a sparse clone of https://github.com/mdn/translated-content (files/es/web/**),
prose under CC BY-SA 2.5. One record per page: the frontmatter title is the key,
the body is the Markdown with MDN macros resolved to plain text (code blocks kept).

Usage:
    git clone --filter=blob:none --sparse --depth 1 https://github.com/mdn/translated-content.git E:/corpus-src/mdn
    cd E:/corpus-src/mdn && git sparse-checkout set files/es/web files/es/learn
    python scripts/datasets/fetch_mdn_web_es.py --root E:/corpus-src/mdn
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from common import clean_text, log, save_records

MIN_CHARS = 160
MAX_CHARS = 6000

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# {{jsxref("Array.prototype.map()")}} → Array.prototype.map(), {{JSRef}} → ""
MACRO_ARG_RE = re.compile(r"\{\{\s*\w+\s*\(\s*([\"'])(.*?)\1[^}]*\)\s*\}\}")
MACRO_BARE_RE = re.compile(r"\{\{[^{}\n]*\}\}")
LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
BADGE_RE = re.compile(r"^\s*[>|]\s*\[!\w+\]\s*$", re.MULTILINE)
HEADING_RE = re.compile(r"^#{2,6}\s*", re.MULTILINE)


def frontmatter(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, text[m.end():]


def to_plain(md: str) -> str:
    md = MACRO_ARG_RE.sub(r"\2", md)
    md = MACRO_BARE_RE.sub("", md)
    md = LINK_RE.sub(r"\1", md)
    md = BADGE_RE.sub("", md)
    md = HEADING_RE.sub("", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return clean_text(md)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="E:/corpus-src/mdn")
    args = ap.parse_args()
    root = Path(args.root) / "files" / "es"
    if not root.is_dir():
        raise SystemExit(f"not found: {root}")

    records: list[dict] = []
    seen: set[str] = set()
    for path in sorted(root.rglob("index.md")):
        raw = path.read_text(encoding="utf-8", errors="replace")
        meta, body = frontmatter(raw)
        title = meta.get("title", "").strip()
        slug = meta.get("slug", "").strip()
        if not title or not slug:
            continue
        text = to_plain(body)
        if len(text) < MIN_CHARS:
            continue
        if len(text) > MAX_CHARS:
            cut = text.rfind("\n\n", 0, MAX_CHARS)
            text = text[: cut if cut > MAX_CHARS // 2 else MAX_CHARS]
        key = title if title not in seen else f"{title} ({slug.split('/')[-2]})"
        seen.add(key)
        area = slug.split("/")[1] if slug.count("/") >= 1 else "Web"
        records.append({
            "id": slug,
            "title": key,
            "content": text,
            "area": area,
            "source_url": f"https://developer.mozilla.org/es/docs/{slug}",
        })

    records.sort(key=lambda r: r["title"].lower())
    if len(records) < 500:
        raise SystemExit(f"only {len(records)} pages parsed — check the sparse checkout")
    save_records("mdn-web-es", records, {
        "name": "MDN Web Docs en español",
        "description": "Referencia de JavaScript, CSS, HTML y Web APIs de MDN en español: qué hace cada método, propiedad o elemento, con ejemplos.",
        "language": "es",
        "license": "CC BY-SA 2.5 — Mozilla Contributors (MDN Web Docs)",
        "source_url": "https://developer.mozilla.org/es/",
    })


if __name__ == "__main__":
    main()
