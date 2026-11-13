import pytest

from app.document_processing.chunking import chunk_pages, is_heading
from app.document_processing.cleaning import clean_text, strip_repeated_headers_footers
from app.document_processing.types import ExtractedPage
from app.multilingual.detect import detect_language

TELUGU = "విద్యార్థులు పరీక్షలకు హాజరు కావడానికి కనీసం 75 శాతం హాజరు కలిగి ఉండాలి"
HINDI = "परीक्षा में बैठने के लिए छात्रों की न्यूनतम उपस्थिति 75 प्रतिशत होनी चाहिए"


def test_detect_language():
    assert detect_language("Minimum attendance is 75 percent") == "en"
    assert detect_language(TELUGU) == "te"
    assert detect_language(HINDI) == "hi"
    assert detect_language("") == "en" and detect_language("1234 !!!") == "en"
    assert detect_language("Attendance 75% " + TELUGU) == "te"


def test_clean_text_normalises_and_keeps_indic_text():
    assert clean_text("exami-\nnation   rules\u00a0apply\x00") == "examination rules apply"
    decomposed = "\u0c15\u0c3e"  # Telugu letter + vowel sign
    assert clean_text(decomposed) == decomposed
    assert TELUGU in clean_text(f"\n\n{TELUGU}\n\n\n\n")
    assert "\n\n\n" not in clean_text("a\n\n\n\n\nb")


def test_repeated_headers_and_page_numbers_removed_only_for_long_docs():
    pages = [ExtractedPage(f"MLRITM Academic Regulations\nBody text of page {i} is unique.\n{i}", i)
             for i in range(1, 7)]
    out = strip_repeated_headers_footers(pages)
    for p in out:
        assert "MLRITM Academic Regulations" not in p.text
        assert p.text.strip().endswith("is unique.")
    short = strip_repeated_headers_footers(pages[:3])
    assert "MLRITM Academic Regulations" in short[0].text  # <4 pages: left alone


def test_is_heading():
    assert is_heading("1. ATTENDANCE") and is_heading("Section 4 Examination Rules") and is_heading("FEE STRUCTURE")
    assert not is_heading("Students must attend 75% of classes.") and not is_heading("")


def test_chunks_never_cross_pages_and_keep_page_numbers():
    pages = [ExtractedPage(f"Page {n} content about topic{n}. " * 40, n) for n in (1, 2, 3)]
    chunks = chunk_pages(pages, size=300, overlap=50)
    assert {c.page_number for c in chunks} == {1, 2, 3}
    for c in chunks:
        n = c.page_number
        assert f"topic{n}" in c.text
        assert all(f"topic{m}" not in c.text for m in (1, 2, 3) if m != n)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunk_size_and_overlap():
    text = " ".join(f"Sentence number {i} says something useful." for i in range(80))
    chunks = chunk_pages([ExtractedPage(text, 1)], size=400, overlap=80)
    assert len(chunks) > 3
    assert all(len(c.text) <= 400 + 80 + 1 for c in chunks)
    # overlap: the start of chunk N+1 repeats words from the end of chunk N
    for a, b in zip(chunks, chunks[1:]):
        assert b.text.split()[0] in a.text.split()[-20:]


def test_heading_is_carried_to_chunks_and_across_pages():
    pages = [ExtractedPage("1. ATTENDANCE\n\nStudents need 75 percent attendance.", 1),
             ExtractedPage("More details about condonation and shortage rules.", 2)]
    chunks = chunk_pages(pages, size=500, overlap=0)
    assert chunks[0].section_heading == "1. ATTENDANCE" and "1. ATTENDANCE" not in chunks[0].text
    assert chunks[1].section_heading == "1. ATTENDANCE"


def test_indic_chunking_splits_on_danda_and_sets_language():
    hi = " ".join(f"{HINDI} क्रमांक {i}।" for i in range(30))
    chunks = chunk_pages([ExtractedPage(hi, 1)], size=300, overlap=0)
    assert len(chunks) > 2 and all(c.language == "hi" for c in chunks)
    assert all(len(c.text) <= 300 for c in chunks)
    assert chunk_pages([ExtractedPage(TELUGU * 3, 1)], size=1000, overlap=0)[0].language == "te"


def test_empty_pages_skipped_and_huge_unbroken_text_is_split():
    chunks = chunk_pages([ExtractedPage("   ", 1), ExtractedPage("word " * 500, 2)], size=200, overlap=0)
    assert chunks and all(c.page_number == 2 and len(c.text) <= 200 for c in chunks)


def test_row_group_mode_keeps_section_hint():
    pages = [ExtractedPage("a: 1\nb: 2", None, "Rows 1-2"), ExtractedPage("a: 3", None, "Rows 3-3")]
    chunks = chunk_pages(pages, one_chunk_per_page=True)
    assert [c.section_heading for c in chunks] == ["Rows 1-2", "Rows 3-3"]


def test_running_header_with_embedded_page_number_is_removed():
    pages = [ExtractedPage(f"Academic Regulations | Page {i} of 6\nUnique body line {i} stays.\nConfidential {i}", i)
             for i in range(1, 7)]
    out = strip_repeated_headers_footers(pages)
    for p in out:
        assert "Academic Regulations" not in p.text and "Confidential" not in p.text
        assert "stays." in p.text
