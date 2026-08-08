"""Normalised data model shared by every country adapter.

Adapters return `Program` objects plus a flat list of `Field` key/value pairs.
Keeping the detail data as key/value pairs (rather than a fixed set of columns)
is deliberate: every country publishes a different set of attributes, and a
rigid schema would force lossy mapping. The normalised columns on `Program`
are only the ones that are genuinely common across sources.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Program:
    source: str                 # adapter id, e.g. "daad"
    source_id: str              # id within that source
    country: str                # ISO-3166 alpha-2, e.g. "DE"
    name: str
    university: str | None = None
    city: str | None = None
    degree: str | None = None   # "Master of Science", ...
    subject: str | None = None
    languages: list[str] = field(default_factory=list)
    duration: str | None = None
    start_terms: str | None = None
    tuition: str | None = None
    deadline_raw: str | None = None   # unparsed deadline text from the source
    detail_url: str | None = None
    website: str | None = None        # official programme page at the university
    fetched_at: str = field(default_factory=utcnow)
    detail_fetched_at: str | None = None


@dataclass
class Field:
    """One labelled attribute scraped from a programme detail page."""

    label: str
    value: str


@dataclass
class Deadline:
    """A deadline resolved to an actual date.

    `source_text` is always kept so the UI can show what the parse was based on
    and the user can sanity-check it against the official page.

    `confidence` records how the date was arrived at, which matters a great
    deal to whoever is relying on it:

      exact   the source published this as a date field — no interpretation
      parsed  extracted from prose by `deadlines.py`; verify before relying
      manual  entered by the user; never overwritten by an ingest
    """

    label: str          # "Winter semester / non-EU"
    date: str           # ISO date, YYYY-MM-DD
    confidence: str     # "exact" | "parsed" | "manual"
    source_text: str


@dataclass
class Listing:
    """What an adapter produces for one programme during a bulk listing.

    Sources differ in how much they give up front. DAAD's search results carry
    only summary data, so `fields` is empty and the detail page must be fetched
    per programme. Study in NL returns the full record — requirements and real
    deadline dates included — in the listing itself, so it fills all three and
    no detail fetch is ever needed.

    `deadlines is None` means the source published no usable dates and the
    prose in `program.deadline_raw` should be parsed instead.
    """

    program: Program
    fields: list[Field] = field(default_factory=list)
    deadlines: list[Deadline] | None = None


# Application tracking states, in the order they normally occur.
STATUSES = [
    "interested",
    "preparing",
    "submitted",
    "accepted",
    "rejected",
    "withdrawn",
]
