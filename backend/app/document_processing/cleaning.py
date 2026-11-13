import re
import unicodedata
from collections import Counter

from app.document_processing.types import ExtractedPage

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Page markers are only normalised at the START or END of a line, so body sentences that merely
# contain "page 3" or a digit are never mistaken for a running header.
_PAGE_MARK_END = re.compile(r"\bpage\s*\d+(\s*(of|/)\s*\d+)?\s*$", re.IGNORECASE)
_PAGE_MARK_START = re.compile(r"^\s*page\s*\d+(\s*(of|/)\s*\d+)?\b", re.IGNORECASE)
_EDGE_NUMBER = re.compile(r"^\d+\s+|\s+\d+$")
_PAGE_NUM_ONLY = re.compile(r"^\s*(page\s*)?\d{1,4}(\s*(of|/)\s*\d{1,4})?\s*$", re.IGNORECASE)


def clean_text(text: str) -> str:
    # NFC matters for Telugu/Hindi: the same visible string can have several byte sequences.
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL.sub(" ", text).replace("\u00a0", " ").replace("\u200b", "")
    # Re-join words hyphenated across line breaks (Latin script only).
    text = re.sub(r"([A-Za-z])-\n([a-z])", r"\1\2", text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]
    out: list[str] = []
    blank = 0
    for ln in lines:
        if not ln:
            blank += 1
            if blank == 1:
                out.append("")
            continue
        blank = 0
        out.append(ln)
    return "\n".join(out).strip()


def _edge_key(line: str) -> str:
    line = _PAGE_MARK_END.sub("page #", line)
    line = _PAGE_MARK_START.sub("page #", line)
    return _EDGE_NUMBER.sub("", line).strip()


def strip_repeated_headers_footers(pages: list[ExtractedPage]) -> list[ExtractedPage]:
    """Drops lines that repeat on most pages (running headers/footers, page numbers).

    Only applied to documents with >= 4 pages, and only to the first/last 2 lines of each page,
    so genuine body text that happens to repeat is not removed."""
    if len(pages) < 4:
        return [ExtractedPage(clean_text(p.text), p.page_number, p.section_hint, p.ocr_used) for p in pages]

    cleaned = [clean_text(p.text) for p in pages]
    edge_counts: Counter[str] = Counter()
    for t in cleaned:
        lines = [ln for ln in t.split("\n") if ln.strip()]
        for ln in set(lines[:2] + lines[-2:]):
            edge_counts[_edge_key(ln)] += 1
    threshold = max(3, int(len(pages) * 0.6))
    repeated = {k for k, v in edge_counts.items() if v >= threshold}

    result = []
    for p, t in zip(pages, cleaned):
        lines = t.split("\n")
        nonblank = [i for i, ln in enumerate(lines) if ln.strip()]
        edge_idx = set(nonblank[:2] + nonblank[-2:])
        kept = [ln for i, ln in enumerate(lines)
                if not (i in edge_idx and (_edge_key(ln) in repeated or _PAGE_NUM_ONLY.match(ln)))]
        result.append(ExtractedPage(clean_text("\n".join(kept)), p.page_number, p.section_hint, p.ocr_used))
    return result
