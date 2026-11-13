from dataclasses import dataclass, field


@dataclass
class ExtractedPage:
    """A unit of text with a trustworthy location. page_number is None when the format has no pages."""
    text: str
    page_number: int | None = None
    section_hint: str | None = None  # e.g. "Rows 1-10" for CSV
    ocr_used: bool = False


@dataclass
class ExtractionResult:
    pages: list[ExtractedPage]
    page_count: int | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class Chunk:
    index: int
    text: str
    page_number: int | None
    section_heading: str | None
    language: str


class ExtractionError(Exception):
    """Raised with a user-safe message when a file cannot be processed."""
