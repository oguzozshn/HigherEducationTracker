"""Turn free-text application periods into actual dates.

Sources write deadlines as prose, in wildly varying shapes:

    "Register by 31 October 2026 + 1 more"
    "For the summer semester: until 31 October"
    "non-EU countries: 15.01.2027"

This module finds every date-like token, infers a missing year as the *next*
occurrence of that day/month, and keeps the surrounding text as the label. It
is best-effort by design — every result is stored with the source text next to
it so the UI can show what the parse was based on, and a wrong or missing parse
degrades to "check the official page" rather than to a silently wrong date.
"""

from __future__ import annotations

import re
from datetime import date

from .models import Deadline

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
    # German, since some detail pages mix languages
    "januar": 1, "februar": 2, "märz": 3, "maerz": 3, "mai": 5, "juni": 6,
    "juli": 7, "oktober": 10, "dezember": 12,
}

_MONTH_ALT = "|".join(sorted(MONTHS, key=len, reverse=True))

# "31 October 2026" / "31 October"
_RE_DMY = re.compile(rf"\b(\d{{1,2}})\.?\s+({_MONTH_ALT})\b(?:\s+(\d{{4}}))?", re.I)
# "October 31, 2026" / "October 31"
_RE_MDY = re.compile(rf"\b({_MONTH_ALT})\s+(\d{{1,2}})\b(?:,?\s+(\d{{4}}))?", re.I)
# "15.01.2027" / "15/01/2027"
_RE_NUM = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")

# Words that introduce a deadline; stripped from the end of a label.
_TRAILING = re.compile(
    r"[\s:,\-–]*\b(until|by|till|to|before|no later than|deadline|is|are|from)\b[\s:,\-–]*$",
    re.I,
)

# A label made only of these words says nothing useful on its own.
_GENERIC = {
    "register", "registration", "apply", "application", "applications",
    "submit", "deadline", "deadlines", "period", "periods", "closes",
    "opens", "the", "for", "and", "on", "at", "in",
}

_GENERIC_LABEL = "Application deadline"

# Text joining two dates into a single application window ("1 May - 31 May").
# "and" is deliberately absent: it usually joins two separate deadlines.
_RANGE_SEP = re.compile(r"^\s*(?:-|–|—|to|until|till|through|bis)\s*$", re.I)


def _resolve_year(month: int, day: int, year: int | None, today: date) -> date | None:
    """Build a date, choosing the next future year when none was given."""
    if year is not None:
        try:
            return date(year, month, day)
        except ValueError:
            return None
    for candidate in (today.year, today.year + 1):
        try:
            d = date(candidate, month, day)
        except ValueError:
            return None
        if d >= today:
            return d
    return None


# Keyword groups used to label a date. Within a group the keyword *closest* to
# the date wins — a page that lists several intakes in a row repeats these
# words, so merely finding one somewhere nearby would mislabel every date.
_SEMESTER_KEYWORDS = [
    (r"\bwinter\b", "winter semester"),
    (r"\bsummer\b", "summer semester"),
]
_APPLICANT_KEYWORDS = [
    (r"non[-\s]?eu\b", "non-EU applicants"),
    (r"\beu\b|european union", "EU applicants"),
    (r"\ball countries\b", "all countries"),
]

_WINDOW_BEFORE = 300
_WINDOW_AFTER = 80


def _nearest_keyword(text: str, start: int, end: int,
                     keywords: list[tuple[str, str]]) -> str | None:
    """Return the label of whichever keyword sits closest to the date."""
    lo = max(0, start - _WINDOW_BEFORE)
    window = text[lo:end + _WINDOW_AFTER].lower()
    date_pos = start - lo

    best_label, best_distance = None, None
    for pattern, label in keywords:
        for m in re.finditer(pattern, window):
            # Text before the date describes it; text after usually belongs to
            # the next entry, so weight following matches as further away.
            distance = date_pos - m.end() if m.end() <= date_pos else (m.start() - date_pos) * 3
            if best_distance is None or distance < best_distance:
                best_label, best_distance = label, distance
    return best_label


def _label_from_context(text: str, start: int, end: int) -> str | None:
    """Build a label from the semester / applicant-group keywords near a date.

    This is what actually matters when comparing programmes: the same page
    usually lists several dates that differ only by intake and by whether the
    applicant holds an EU degree.
    """
    tags = [
        _nearest_keyword(text, start, end, _SEMESTER_KEYWORDS),
        _nearest_keyword(text, start, end, _APPLICANT_KEYWORDS),
    ]
    return " / ".join(t for t in tags if t) or None


def _label_before(text: str, start: int, end: int, max_chars: int = 80) -> str:
    """Label a date, preferring semester keywords over raw preceding prose."""
    contextual = _label_from_context(text, start, end)
    if contextual:
        return contextual

    chunk = text[max(0, start - max_chars):start].replace("\n", " ")
    # Start after the last sentence/clause boundary so labels stay short.
    chunk = re.split(r"(?<=[.;•])\s+", chunk)[-1]
    chunk = _TRAILING.sub("", chunk).strip(" :,-–\t")
    chunk = re.sub(r"\s+", " ", chunk)[-60:].strip()

    words = {w.strip("():,.").lower() for w in chunk.split()}
    if not chunk or words <= _GENERIC:
        return _GENERIC_LABEL
    return chunk


def parse_deadlines(text: str | None, *, today: date | None = None) -> list[Deadline]:
    if not text:
        return []
    today = today or date.today()

    # (start, end, resolved date, matched text)
    found: list[tuple[int, int, date, str]] = []

    for m in _RE_NUM.finditer(text):
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        d = _resolve_year(month, day, year, today)
        if d:
            found.append((m.start(), m.end(), d, m.group(0)))

    for regex, order in ((_RE_DMY, "dmy"), (_RE_MDY, "mdy")):
        for m in regex.finditer(text):
            if order == "dmy":
                day, month_name, year = m.group(1), m.group(2), m.group(3)
            else:
                month_name, day, year = m.group(1), m.group(2), m.group(3)
            month = MONTHS[month_name.lower()]
            d = _resolve_year(month, int(day), int(year) if year else None, today)
            if d:
                found.append((m.start(), m.end(), d, m.group(0)))

    found.sort()

    # The three patterns can match overlapping spans of the same date; keep the
    # first match of each span.
    spans: list[tuple[int, int, date, str]] = []
    for item in found:
        if spans and item[0] < spans[-1][1]:
            continue
        spans.append(item)

    # "1 May - 31 May" is one application window, not two deadlines. Only its
    # closing date is a deadline; treating the opening date as one would put a
    # misleading entry at the top of the calendar.
    opening = {
        a[0] for a, b in zip(spans, spans[1:])
        if _RANGE_SEP.match(text[a[1]:b[0]]) and a[2] <= b[2]
    }

    results: dict[tuple[str, str], Deadline] = {}
    for start, _end, d, matched in spans:
        if start in opening:
            continue
        label = _label_before(text, start, start + len(matched))
        iso = d.isoformat()
        key = (label.lower(), iso)
        if key in results:
            continue
        snippet = text[max(0, start - 90):start + len(matched) + 30].replace("\n", " ")
        results[key] = Deadline(
            label=label,
            date=iso,
            confidence="parsed",
            source_text=re.sub(r"\s+", " ", snippet).strip(),
        )
    return list(results.values())
