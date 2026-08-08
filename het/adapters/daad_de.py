"""Germany — DAAD "International Programmes in Germany" database.

The public search UI is backed by a JSON endpoint that accepts the same filter
parameters as the website, so the bulk listing needs no HTML parsing at all.
Detail pages are HTML, but DAAD renders every attribute as a <dt>/<dd> pair in
a description list, which parses cleanly and without heuristics.

Filter codes (discovered from the endpoint's own facet output):
    degree[]  1=Bachelor  2=Master  3=PhD  8=Language course  10=Short course
    lang[]    1=German  2=English  3=German and English  4=other
"""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Iterator

from ..http import build_url, fetch
from ..models import Field, Listing, Program, utcnow
from ..text import strip_html

ROOT = "https://www2.daad.de/deutschland/studienangebote/international-programmes"
SEARCH_API = f"{ROOT}/api/solr/en/search.json"
SITE = "https://www2.daad.de"

DEGREE_MASTER = 2
LANG_ENGLISH = 2

PAGE_SIZE = 100

# Detail-page labels that carry no information for us (contact widget leftovers).
_SKIP_LABELS = {"", "E-Mail:", "Web:", "Phone:"}


class _DescriptionListParser(HTMLParser):
    """Collect every <dt>/<dd> pair on the page, plus the course website URL."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.pairs: list[tuple[str, str]] = []
        self.course_website: str | None = None
        self._mode: str | None = None       # 'dt' | 'dd' | None
        self._buf: list[str] = []
        self._label: str | None = None
        self._suppress = 0                  # inside <script>/<style>

    # -- helpers ---------------------------------------------------------
    def _text(self) -> str:
        text = "".join(self._buf)
        text = re.sub(r"[ \t\r\f\v]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text)
        return text.strip()

    # -- HTMLParser hooks ------------------------------------------------
    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._suppress += 1
            return
        attrd = dict(attrs)
        if tag == "a" and "visitCourseWebsite" in (attrd.get("class") or ""):
            self.course_website = attrd.get("href")
        if tag == "dt":
            self._mode, self._buf = "dt", []
        elif tag == "dd":
            self._mode, self._buf = "dd", []
        elif tag in ("br", "p", "li", "div", "tr") and self._mode:
            self._buf.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._suppress = max(0, self._suppress - 1)
            return
        if tag == "dt" and self._mode == "dt":
            self._label = self._text()
            self._mode = None
        elif tag == "dd" and self._mode == "dd":
            if self._label is not None:
                self.pairs.append((self._label, self._text()))
            self._label, self._mode = None, None
        elif tag in ("p", "li", "ul", "ol") and self._mode:
            self._buf.append("\n")

    def handle_data(self, data):
        if self._mode and not self._suppress:
            self._buf.append(data)


def _clean_fields(pairs: list[tuple[str, str]]) -> list[Field]:
    """Deduplicate labels, keeping the most informative value for each."""
    best: dict[str, str] = {}
    for label, value in pairs:
        label = label.strip()
        if label in _SKIP_LABELS or not value:
            continue
        if len(value) > len(best.get(label, "")):
            best[label] = value
    return [Field(label=k, value=v) for k, v in best.items()]


class DaadAdapter:
    id = "daad"
    country = "DE"

    def list_programs(self, *, degree: int = DEGREE_MASTER,
                      language: int | None = LANG_ENGLISH,
                      subject_query: str = "",
                      max_age: float | None = 24 * 3600,
                      limit: int | None = None) -> Iterator[Listing]:
        """Page through the search API, yielding one Listing per result.

        Listings carry no fields or dates: DAAD's search results hold only
        summary data, so requirements come from the detail page and deadlines
        have to be parsed out of prose.

        Paging is by `offset`. A `page` parameter is accepted by the endpoint
        but silently ignored, which looks like it works — every request returns
        200 with a full page of results — while actually returning the first
        page forever. Results are therefore de-duplicated by id, and a page
        that yields nothing new ends the walk instead of looping.
        """
        params: dict[str, object] = {
            "q": subject_query,
            "degree[]": degree,
            "limit": PAGE_SIZE,
            "display": "list",
        }
        if language is not None:
            params["lang[]"] = language

        offset = 0
        seen_ids: set[str] = set()
        while True:
            params["offset"] = offset
            payload = json.loads(fetch(build_url(SEARCH_API, params), max_age=max_age))
            courses = payload.get("courses") or []
            if not courses:
                break

            fresh = 0
            for course in courses:
                course_id = str(course["id"])
                if course_id in seen_ids:
                    continue
                seen_ids.add(course_id)
                fresh += 1
                yield Listing(program=self._to_program(course))
                if limit and len(seen_ids) >= limit:
                    return
            if fresh == 0:
                break

            offset += PAGE_SIZE
            if offset >= payload.get("numResults", 0):
                break

    def _to_program(self, c: dict) -> Program:
        link = c.get("link") or ""
        # Some records carry raw markup inside nominally plain-text fields.
        return Program(
            source=self.id,
            source_id=str(c["id"]),
            country=self.country,
            name=strip_html(c.get("courseName")) or "",
            university=strip_html(c.get("academy")),
            city=strip_html(c.get("city")),
            degree=None,                    # only exact on the detail page
            subject=strip_html(c.get("subject")),
            languages=c.get("languages") or [],
            duration=strip_html(c.get("programmeDuration")),
            start_terms=strip_html(c.get("beginning")),
            tuition=strip_html(c.get("tuitionFees")),
            deadline_raw=strip_html(c.get("applicationDeadline")),
            detail_url=SITE + link if link.startswith("/") else link or None,
            fetched_at=utcnow(),
        )

    def fetch_detail(self, program: Program,
                     max_age: float | None = 7 * 24 * 3600) -> tuple[Program, list[Field]]:
        if not program.detail_url:
            return program, []
        parser = _DescriptionListParser()
        parser.feed(fetch(program.detail_url, max_age=max_age))
        fields = _clean_fields(parser.pairs)
        by_label = {f.label: f.value for f in fields}

        program.degree = by_label.get("Degree") or program.degree
        program.website = parser.course_website or program.website
        # The detail page states application periods far more precisely than
        # the search-result summary ("Register by 31 October 2026 + 1 more").
        program.deadline_raw = by_label.get("Application periods") or program.deadline_raw
        program.detail_fetched_at = utcnow()
        return program, fields
