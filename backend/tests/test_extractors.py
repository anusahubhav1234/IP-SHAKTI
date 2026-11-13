import pytest

from app.document_processing.extractors import extract_csv, extract_docx, extract_pdf, extract_txt
from app.document_processing.types import ExtractionError
from tests.helpers import make_docx, make_pdf, make_scanned_pdf
from tests.test_text_pipeline import TELUGU


def _w(tmp_path, name, data):
    p = tmp_path / name
    p.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    return str(p)


def test_pdf_pages_are_numbered_correctly(tmp_path):
    r = extract_pdf(_w(tmp_path, "a.pdf", make_pdf(["alpha page one text here", "bravo page two text here",
                                                    "charlie page three text here"])))
    assert r.page_count == 3
    assert [p.page_number for p in r.pages] == [1, 2, 3]
    assert "bravo" in r.pages[1].text and "alpha" not in r.pages[1].text


def test_corrupt_pdf_raises_user_safe_error(tmp_path):
    with pytest.raises(ExtractionError):
        extract_pdf(_w(tmp_path, "bad.pdf", b"%PDF-1.4 this is not really a pdf"))


def test_scanned_pdf_uses_ocr(tmp_path):
    r = extract_pdf(_w(tmp_path, "scan.pdf", make_scanned_pdf("Minimum attendance required 75 percent")))
    assert r.pages[0].ocr_used is True
    assert "attendance" in r.pages[0].text.lower()


def test_docx_text_headings_and_tables(tmp_path):
    r = extract_docx(_w(tmp_path, "a.docx", make_docx()))
    text = r.pages[0].text
    assert "Examination Regulations" in text and "75 percent" in text
    assert "Exam fee | 15 March" in text
    assert r.pages[0].page_number is None and r.page_count is None


def test_txt_utf8_telugu_and_binary_rejected(tmp_path):
    assert TELUGU in extract_txt(_w(tmp_path, "t.txt", TELUGU)).pages[0].text
    with pytest.raises(ExtractionError):
        extract_txt(_w(tmp_path, "b.txt", b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"))
    with pytest.raises(ExtractionError):  # even-length binary must not be 'decoded' as UTF-16
        extract_txt(_w(tmp_path, "b2.txt", b"\x81\x82\x83\x84\x85\x86"))
    assert "hello" in extract_txt(_w(tmp_path, "u16.txt", "hello".encode("utf-16"))).pages[0].text
    with pytest.raises(ExtractionError):
        extract_txt(_w(tmp_path, "e.txt", "   \n"))


def test_csv_grouping_and_hints(tmp_path, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "csv_rows_per_chunk", 2)
    data = "Company,Eligibility\nA,60%\nB,70%\nC,65%\n"
    r = extract_csv(_w(tmp_path, "c.csv", data))
    assert [p.section_hint for p in r.pages] == ["Rows 1-2", "Rows 3-3"]
    assert "Company: A; Eligibility: 60%" in r.pages[0].text


def test_faq_csv(tmp_path):
    r = extract_csv(_w(tmp_path, "f.csv", "Question,Answer\nWhat is the fee deadline?,15 March\n,\n"), as_faq=True)
    assert len(r.pages) == 1 and "Answer: 15 March" in r.pages[0].text and r.pages[0].section_hint == "FAQ row 2"
    with pytest.raises(ExtractionError):
        extract_csv(_w(tmp_path, "g.csv", "a,b\n1,2\n"), as_faq=True)
