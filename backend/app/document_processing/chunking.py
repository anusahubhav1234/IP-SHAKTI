import re

from app.document_processing.types import Chunk, ExtractedPage
from app.multilingual.detect import detect_language

# Sentence ends: Latin . ? !  and the Devanagari danda । ॥ (Telugu uses Latin full stops).
_SENTENCE_SPLIT = re.compile(r"(?<=[.?!।॥])\s+")
_HEADING_NUMBERED = re.compile(r"^(\d+(\.\d+)*[.)]?|[IVX]+\.|chapter\s+\d+|section\s+\d+|article\s+\d+)\s+\S", re.I)


def is_heading(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 100 or line.endswith((".", ",", ";", ":", "।")):
        return False
    if _HEADING_NUMBERED.match(line) and len(line.split()) <= 12:
        return True
    letters = [c for c in line if c.isalpha()]
    return len(letters) >= 4 and line.isupper() and len(line.split()) <= 12


def _split_long(text: str, size: int) -> list[str]:
    """Splits text into pieces <= size, preferring sentence then word boundaries."""
    if len(text) <= size:
        return [text]
    pieces, current = [], ""
    for sent in _SENTENCE_SPLIT.split(text):
        if len(sent) > size:  # a single huge "sentence": fall back to words
            if current:
                pieces.append(current)
                current = ""
            words, buf = sent.split(" "), ""
            for w in words:
                if buf and len(buf) + 1 + len(w) > size:
                    pieces.append(buf)
                    buf = w
                else:
                    buf = f"{buf} {w}".strip()
            current = buf
            continue
        if current and len(current) + 1 + len(sent) > size:
            pieces.append(current)
            current = sent
        else:
            current = f"{current} {sent}".strip()
    if current:
        pieces.append(current)
    return pieces


def _tail_overlap(text: str, overlap: int) -> str:
    """Last ~overlap chars, starting at a word boundary."""
    if overlap <= 0 or len(text) <= overlap:
        return text if overlap > 0 else ""
    tail = text[-overlap:]
    sp = tail.find(" ")
    return tail[sp + 1:] if sp != -1 else tail


def chunk_pages(pages: list[ExtractedPage], size: int = 1000, overlap: int = 150,
                one_chunk_per_page: bool = False) -> list[Chunk]:
    """Page-aware chunking. A chunk never spans two pages, so its page_number is always exact.

    Overlap is applied only between chunks of the same page. The most recent heading seen
    (carried across pages) is attached to each chunk as section_heading."""
    assert 0 <= overlap < size
    chunks: list[Chunk] = []
    heading: str | None = None

    for page in pages:
        if not page.text.strip():
            continue
        if one_chunk_per_page:  # CSV/FAQ row groups: already pre-grouped by the extractor
            parts = _split_long(page.text, size * 3)
            for part in parts:
                chunks.append(Chunk(len(chunks), part, page.page_number, page.section_hint or heading,
                                    detect_language(part)))
            continue

        # Build paragraphs, tracking headings.
        units: list[tuple[str, str | None]] = []  # (text, heading_in_effect)
        for para in re.split(r"\n\s*\n", page.text):
            lines = [ln for ln in para.split("\n") if ln.strip()]
            if not lines:
                continue
            if is_heading(lines[0]):
                heading = lines[0].strip()
                lines = lines[1:]
                if not lines:
                    continue
            units.append((" ".join(lines), heading))

        current, current_heading = "", None
        page_chunks: list[tuple[str, str | None]] = []

        def flush():
            nonlocal current, current_heading
            if current.strip():
                page_chunks.append((current.strip(), current_heading))
            current, current_heading = "", None

        for text, h in units:
            for piece in _split_long(text, size):
                if current and len(current) + 1 + len(piece) > size:
                    flush()
                if not current:
                    current_heading = h
                current = f"{current} {piece}".strip()
        flush()

        for i, (text, h) in enumerate(page_chunks):
            if i > 0 and overlap:
                text = f"{_tail_overlap(page_chunks[i - 1][0], overlap)} {text}"
            chunks.append(Chunk(len(chunks), text, page.page_number, h or page.section_hint,
                                detect_language(text)))
    return chunks
