import re
import unicodedata

# \w alone would split Telugu/Hindi words at vowel signs (they are combining marks, not alphanumerics),
# so the Devanagari and Telugu blocks are added explicitly.
_TOKEN = re.compile(r"[\w\u0900-\u097f\u0c00-\u0c7f]+", re.UNICODE)
_STOP_EN = frozenset("a an and are as at be by for from has have in is it its of on or that the to was were will with".split())


def tokenize(text: str) -> list[str]:
    """Lowercase, NFC-normalise, split into word tokens. English stopwords are dropped; Hindi/Telugu
    are not stemmed (documented limitation: agglutinative suffixes reduce exact-match recall)."""
    text = unicodedata.normalize("NFC", text).lower()
    return [t for t in _TOKEN.findall(text) if t not in _STOP_EN and t != "_"]
