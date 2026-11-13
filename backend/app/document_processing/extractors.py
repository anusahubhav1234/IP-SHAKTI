import csv
import io
import logging
import zipfile

from app.core.config import get_settings
from app.document_processing.types import ExtractedPage, ExtractionError, ExtractionResult

logger = logging.getLogger("sakti.extract")

MIN_TEXT_CHARS_PER_PAGE = 20  # below this a PDF page is treated as scanned


def _ocr_page(page) -> str:
    """OCR for a PDF page with no text layer. Requires the tesseract binary + language packs."""
    import pytesseract
    from PIL import Image

    pix = page.get_pixmap(dpi=220)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img, lang=get_settings().ocr_languages)


def extract_pdf(path: str) -> ExtractionResult:
    import pymupdf

    try:
        doc = pymupdf.open(path)
    except Exception as exc:
        raise ExtractionError("The PDF could not be opened (corrupt or unsupported).") from exc
    if doc.needs_pass:
        raise ExtractionError("Password-protected PDFs are not supported.")

    s = get_settings()
    pages, warnings, ocr_failed = [], [], False
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text") or ""
        ocr_used = False
        if len(text.strip()) < MIN_TEXT_CHARS_PER_PAGE and s.ocr_enabled:
            try:
                text = _ocr_page(page)
                ocr_used = True
            except Exception as exc:  # tesseract missing / language pack missing
                ocr_failed = True
                logger.warning("OCR failed on page %s: %s", i, exc)
        pages.append(ExtractedPage(text=text, page_number=i, ocr_used=ocr_used))
    n = len(doc)
    doc.close()
    if ocr_failed:
        warnings.append("Some pages had no text layer and OCR was unavailable.")
    if not any(p.text.strip() for p in pages):
        raise ExtractionError("No extractable text found (scanned PDF and OCR produced nothing).")
    return ExtractionResult(pages=pages, page_count=n, warnings=warnings)


def extract_docx(path: str) -> ExtractionResult:
    import docx

    try:
        d = docx.Document(path)
    except Exception as exc:
        raise ExtractionError("The DOCX file could not be opened (corrupt or unsupported).") from exc
    parts = []
    for block in d.element.body.iterchildren():
        tag = block.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = docx.text.paragraph.Paragraph(block, d)
            t = para.text.strip()
            if not t:
                parts.append("")
            elif para.style is not None and para.style.name.lower().startswith(("heading", "title")):
                parts.append(f"\n{t}\n")  # blank lines let the chunker see it as a heading
            else:
                parts.append(t)
        elif tag == "tbl":
            table = docx.table.Table(block, d)
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                parts.append(" | ".join(cells))
    text = "\n".join(parts)
    if not text.strip():
        raise ExtractionError("The DOCX file contains no text.")
    # DOCX has no fixed pages; page_number stays None (citations show the section instead).
    return ExtractionResult(pages=[ExtractedPage(text=text, page_number=None)], page_count=None)


def _decode(data: bytes) -> str:
    """UTF-8 (with or without BOM), or UTF-16 only when a BOM says so. Guessing UTF-16 without a BOM
    would 'successfully' decode arbitrary binary files into garbage."""
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            text = data.decode("utf-16")
        else:
            text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ExtractionError("Text files must be UTF-8 encoded.")
    if "\x00" in text:
        raise ExtractionError("The file looks like binary data, not text.")
    return text


def extract_txt(path: str) -> ExtractionResult:
    with open(path, "rb") as f:
        text = _decode(f.read())
    if not text.strip():
        raise ExtractionError("The text file is empty.")
    return ExtractionResult(pages=[ExtractedPage(text=text, page_number=None)], page_count=None)


def extract_csv(path: str, as_faq: bool = False) -> ExtractionResult:
    """Generic CSV: rows are grouped N at a time, each row rendered as 'header: value' pairs so a chunk
    is self-describing. FAQ mode (columns 'question','answer'): one page-unit per Q/A pair."""
    s = get_settings()
    with open(path, "rb") as f:
        text = _decode(f.read())
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except csv.Error as exc:
        raise ExtractionError("The CSV file could not be parsed.") from exc
    if not rows:
        raise ExtractionError("The CSV file has no data rows.")
    fields = [h.strip() for h in (rows[0].keys() or []) if h]
    lower = {h.lower(): h for h in fields}

    if as_faq:
        if "question" not in lower or "answer" not in lower:
            raise ExtractionError("FAQ CSV needs 'question' and 'answer' columns.")
        q, a = lower["question"], lower["answer"]
        pages = []
        for n, r in enumerate(rows, start=2):  # row 1 is the header
            question, answer = (r.get(q) or "").strip(), (r.get(a) or "").strip()
            if question and answer:
                pages.append(ExtractedPage(f"Question: {question}\nAnswer: {answer}", None, f"FAQ row {n}"))
        if not pages:
            raise ExtractionError("FAQ CSV has no complete question/answer rows.")
        return ExtractionResult(pages=pages, page_count=None)

    pages, n = [], s.csv_rows_per_chunk
    for start in range(0, len(rows), n):
        group = rows[start:start + n]
        lines = []
        for r in group:
            lines.append("; ".join(f"{k}: {(v or '').strip()}" for k, v in r.items() if k and (v or "").strip()))
        pages.append(ExtractedPage("\n".join(lines), None, f"Rows {start + 1}-{start + len(group)}"))
    return ExtractionResult(pages=pages, page_count=None)


def extract(path: str, source_type: str) -> ExtractionResult:
    if source_type == "pdf":
        return extract_pdf(path)
    if source_type == "docx":
        return extract_docx(path)
    if source_type == "txt":
        return extract_txt(path)
    if source_type == "csv":
        return extract_csv(path)
    if source_type == "faq":
        return extract_csv(path, as_faq=True)
    raise ExtractionError(f"Unsupported source type: {source_type}")
