"""Internet Archive API helpers — search, metadata, file filtering."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

TEXT_PDF_FORMATS = {
    "Text PDF", "PDF with Text", "PDF WITH TEXT", "Additional Text PDF"
}
EXTRA_FORMATS = {
    "JPEG", "JPEG Thumb", "JP2", "JP2 ZIP",
    "Single Page Processed JP2 ZIP", "Animated GIF", "PNG", "TIFF",
    "EPUB", "DAISY", "Kindle", "Word Document", "Microsoft Word",
}


def is_text_file(f: dict) -> bool:
    name = (f.get("name") or "").lower()
    return name.endswith(".txt")


def is_pdf_file(f: dict) -> bool:
    fmt = f.get("format") or ""
    if fmt in TEXT_PDF_FORMATS:
        return True
    fl = fmt.lower()
    return "text" in fl and "pdf" in fl


def is_extra_file(f: dict) -> bool:
    fmt = f.get("format") or ""
    if fmt in EXTRA_FORMATS:
        return True
    fl = fmt.lower()
    return any(x in fl for x in ("jpeg", "jp2", "epub", "daisy"))


def search_items(
    query: str,
    *,
    mediatype: str | None = None,
    rows: int = 20,
    page: int = 1,
) -> list[dict[str, str]]:
    """Search archive.org via advancedsearch.php."""
    q = query.strip()
    if not q:
        return []
    if mediatype:
        q = f"({q}) AND mediatype:{mediatype}"

    params = urllib.parse.urlencode({
        "q": q,
        "fl[]": ["identifier", "title", "mediatype"],
        "rows": max(1, min(rows, 100)),
        "page": max(1, page),
        "output": "json",
    }, doseq=True)

    url = f"https://archive.org/advancedsearch.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "BatchinCamaro/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    docs = data.get("response", {}).get("docs", [])
    results = []
    for doc in docs:
        ident = doc.get("identifier", "")
        if not ident:
            continue
        title = doc.get("title", ident)
        if isinstance(title, list):
            title = title[0] if title else ident
        mt = doc.get("mediatype", "")
        if isinstance(mt, list):
            mt = mt[0] if mt else ""
        results.append({
            "identifier": ident,
            "title": str(title),
            "mediatype": str(mt),
        })
    return results


def get_metadata(item_id: str) -> dict[str, Any]:
    """Fetch item metadata from archive.org."""
    item_id = item_id.strip()
    url = f"https://archive.org/metadata/{urllib.parse.quote(item_id)}"
    req = urllib.request.Request(url, headers={"User-Agent": "BatchinCamaro/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        if resp.status != 200:
            raise ValueError(f"Metadata HTTP {resp.status}")
        return json.loads(resp.read().decode("utf-8"))


def filter_downloadable_files(
    metadata: dict[str, Any],
    *,
    want_text: bool = True,
    want_pdf: bool = True,
    want_extra: bool = False,
) -> list[dict[str, Any]]:
    """Return file entries matching download preferences."""
    files = metadata.get("files") or []
    out = []
    for f in files:
        if want_text and is_text_file(f):
            out.append(f)
        elif want_pdf and is_pdf_file(f):
            out.append(f)
        elif want_extra and is_extra_file(f):
            out.append(f)
    return out


def is_restricted(metadata: dict[str, Any]) -> bool:
    if metadata.get("is_dark") is True:
        return True
    meta = metadata.get("metadata") or {}
    return meta.get("access-restricted-item") == "true"


def summarize_metadata(metadata: dict[str, Any], *, want_text: bool = True, want_pdf: bool = True) -> dict[str, Any]:
    """Compact summary for agent tool responses."""
    files = filter_downloadable_files(metadata, want_text=want_text, want_pdf=want_pdf)
    meta = metadata.get("metadata") or {}
    title = meta.get("title", metadata.get("identifier", ""))
    if isinstance(title, list):
        title = title[0] if title else ""
    return {
        "identifier": metadata.get("identifier") or meta.get("identifier", ""),
        "title": str(title),
        "restricted": is_restricted(metadata),
        "file_count": len(files),
        "files": [
            {"name": f.get("name"), "format": f.get("format"), "size": f.get("size")}
            for f in files[:30]
        ],
    }
