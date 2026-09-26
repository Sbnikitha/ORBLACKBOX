"""Find and mask patient identifiers before anything can leave the building."""
import re

_PATTERNS = [
    (re.compile(r"\bDOB\s*\d{1,2}/\d{1,2}/\d{2,4}", re.I), "<DATE_TIME>"),
    (re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}"), "<DATE_TIME>"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}"), "<DATE_TIME>"),
    (re.compile(r"\bMRN\s*#?\s*\d+\b", re.I), "<MEDICAL_RECORD>"),
    (re.compile(r"\bage\s+\d+\b", re.I), "<AGE>"),
    (re.compile(r"\bPatient\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+"), "<PERSON>"),
    (re.compile(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b"), "<PERSON>"),
]

_DETECTORS = [pat for pat, _ in _PATTERNS]
_DETECTORS.append(re.compile(r"\bDOB\b", re.I))


def has(text):
    return any(det.search(text or "") for det in _DETECTORS)


def strip(text):
    """Replace names, dates, record numbers, and ages with tags."""
    clean = text or ""
    for pat, token in _PATTERNS:
        clean = pat.sub(token, clean)
    return clean
