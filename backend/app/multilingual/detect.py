"""Script-based language detection for English / Hindi / Telugu.

Deliberately simple and deterministic: Telugu and Devanagari have disjoint Unicode blocks, so a
letter-ratio check is reliable for these three languages. Romanised Hindi/Telugu (e.g. "attendance
kitna chahiye") is NOT detected and is reported as 'en'. That is a documented limitation.
"""

SUPPORTED = ("en", "hi", "te")


def _script_counts(text: str) -> tuple[int, int, int]:
    te = hi = letters = 0
    for ch in text:
        if not ch.isalpha() and not ("\u0900" <= ch <= "\u097f") and not ("\u0c00" <= ch <= "\u0c7f"):
            continue
        letters += 1
        if "\u0c00" <= ch <= "\u0c7f":
            te += 1
        elif "\u0900" <= ch <= "\u097f":
            hi += 1
    return te, hi, letters


def detect_language(text: str, default: str = "en") -> str:
    te, hi, letters = _script_counts(text)
    if letters == 0:
        return default
    if te / letters >= 0.3 and te >= hi:
        return "te"
    if hi / letters >= 0.3:
        return "hi"
    return "en"
