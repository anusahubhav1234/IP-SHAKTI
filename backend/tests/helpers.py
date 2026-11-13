import io

import docx
import pymupdf


def make_pdf(pages: list[str], fontsize: int = 11) -> bytes:
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(50, 50, 545, 790), text, fontsize=fontsize)
    data = doc.tobytes()
    doc.close()
    return data


def make_scanned_pdf(text: str) -> bytes:
    """A PDF whose only content is an image of text (no text layer)."""
    src = pymupdf.open()
    p = src.new_page()
    p.insert_textbox(pymupdf.Rect(50, 50, 545, 400), text, fontsize=26)
    pix = p.get_pixmap(dpi=200)
    out = pymupdf.open()
    page = out.new_page()
    page.insert_image(page.rect, stream=pix.tobytes("png"))
    data = out.tobytes()
    src.close(); out.close()
    return data


def make_docx() -> bytes:
    d = docx.Document()
    d.add_heading("Examination Regulations", level=1)
    d.add_paragraph("Students must maintain a minimum attendance of 75 percent to appear for examinations.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "Fee", "Deadline"
    t.cell(1, 0).text, t.cell(1, 1).text = "Exam fee", "15 March"
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()
