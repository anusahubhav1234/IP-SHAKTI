"""Citation verification: a citation is 'verified' only if its quote really occurs in the retrieved chunk it
points at. Page numbers and titles are never taken from the model; they come from the chunk's DB record."""
import re
import unicodedata
from dataclasses import dataclass

from app.rag.llm import LLMAnswer
from app.rag.types import Hit

_KEEP = re.compile(r"[^\wऀ-ॿఀ-౿]+", re.UNICODE)
MIN_QUOTE_ALNUM = 12  # shorter quotes are too easy to match by accident
_MARKER_GROUP = re.compile(r"\[\s*(S\d+(?:\s*[,;]\s*S\d+)*)\s*\]")
_SID = re.compile(r"S\d+")


def normalise(text: str) -> str:
    """Case-fold and drop everything except letters/digits/Indic marks, so line breaks, punctuation and
    spacing differences from PDF extraction do not cause false negatives."""
    return _KEEP.sub("", unicodedata.normalize("NFC", text).casefold())


def quote_in_source(quote: str, source_text: str) -> bool:
    q = normalise(quote)
    return len(q) >= MIN_QUOTE_ALNUM and q in normalise(source_text)


@dataclass
class VerifiedCitation:
    number: int
    source_id: str
    hit: Hit
    quote: str | None
    verified: bool


@dataclass
class Verification:
    answer: str                      # markers rewritten to [1], [2] ...; unknown markers removed
    citations: list[VerifiedCitation]
    removed_markers: int

    @property
    def verified_count(self) -> int:
        return sum(c.verified for c in self.citations)


def verify_answer(llm: LLMAnswer, sources: dict[str, Hit]) -> Verification:
    text = _MARKER_GROUP.sub(lambda m: "".join(f"[{s}]" for s in _SID.findall(m.group(1))), llm.answer)
    order: list[str] = []
    removed = 0

    def renumber(m: re.Match) -> str:
        nonlocal removed
        sid = m.group(1)
        if sid not in sources:
            removed += 1
            return ""
        if sid not in order:
            order.append(sid)
        return f"[{order.index(sid) + 1}]"

    answer = re.sub(r"\[(S\d+)\]", renumber, text)
    answer = re.sub(r"[ \t]{2,}", " ", answer).strip()

    quotes: dict[str, list[str]] = {}
    for c in llm.citations:
        if c.source_id in sources:
            quotes.setdefault(c.source_id, []).append(c.quote)
    for sid in quotes:  # cited in the list but not inline: still numbered, after the inline ones
        if sid not in order:
            order.append(sid)

    citations = []
    for n, sid in enumerate(order, start=1):
        hit, qs = sources[sid], quotes.get(sid, [])
        good = next((q for q in qs if quote_in_source(q, hit.text)), None)
        citations.append(VerifiedCitation(n, sid, hit, good or (qs[0] if qs else None), good is not None))
    return Verification(answer=answer, citations=citations, removed_markers=removed)
