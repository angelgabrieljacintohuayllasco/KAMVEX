"""
Shared helpers for the dataset source fetchers.

Every fetcher writes a JSON array of records to `datasets-src/<id>.json` with the
fields DASA auto-detects (`title` as key, `content` as body) plus provenance
(`source_url`). The array is what `build_kamvex.py` turns into a `.kamvex` bundle.
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC_DIR = REPO / "datasets-src"
UA = "KAMVEX-datasets/0.2 (+https://github.com/angelgabrieljacintohuayllasco/KAMVEX)"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t ]+")


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def http_get(url: str, params: dict | None = None, retries: int = 4, timeout: int = 60) -> bytes:
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as e:  # noqa: PERF203
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"GET {url} failed: {last}")


def http_json(url: str, params: dict | None = None) -> dict:
    return json.loads(http_get(url, params).decode("utf-8"))


def strip_html(text: str) -> str:
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    return clean_text(text)


def clean_text(text: str) -> str:
    text = text.replace("\r", "")
    text = _WS_RE.sub(" ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


def save_records(dataset_id: str, records: list[dict], meta: dict) -> Path:
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    path = SRC_DIR / f"{dataset_id}.json"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=0), encoding="utf-8")
    (SRC_DIR / f"{dataset_id}.meta.json").write_text(
        json.dumps({**meta, "n_records": len(records)}, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"[{dataset_id}] {len(records)} records -> {path} ({path.stat().st_size / 1e6:.1f} MB)")
    return path
