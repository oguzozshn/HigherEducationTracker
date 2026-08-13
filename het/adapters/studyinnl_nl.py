"""Netherlands — Nuffic "Study in NL" Studyfinder.

The public Studyfinder is backed by a JSON endpoint returning complete
programme records: not just titles and links but structured language
requirements, tuition broken down by fee type, and — unusually — real
application deadline *dates*, given separately for EU and non-EU applicants.

That changes the shape of this adapter compared to the German one. Nothing is
scraped, no prose is parsed, and no per-programme detail request is needed:
one bulk pass yields finished records, deadlines included, at `exact`
confidence.

Two traps this endpoint sets:

  * **Filter parameters are accepted and ignored.** `type=Master` returns 200
    with bachelors mixed in and an unchanged `totalAmount`. All filtering is
    therefore done here, client-side, and no filter is ever sent.
  * **`limit` will serve the whole catalogue in one response.** We page anyway,
    so a change in that generosity cannot turn into one enormous request.

Note for non-EU applicants (which includes Turkey): `application_deadline` is
the general/EU date and `application_deadline_non_eu` is typically months
earlier. Both are kept, labelled explicitly, so the wrong one is never picked
by accident.
"""

from __future__ import annotations

import calendar
import json
from datetime import date
from typing import Iterator

from ..http import build_url, fetch
from ..models import Deadline, Field, Listing, Program, utcnow
from ..text import strip_html

SITE = "https://www.studyinnl.org"
API = f"{SITE}/api/programs"
PROGRAM_PATH = "/dutch-education/studies/"

PAGE_SIZE = 500

# Fee types as the source names them, in the order most useful to read.
_FEE_LABELS = {
    "statutory": "EU/EEA (statutory)",
    "institutional": "Institutional",
    "international": "Non-EU (international)",
}
_FEE_ORDER = ["statutory", "institutional", "international"]

# Certificates the reader is most likely to hold, first.
_CERT_PRIORITY = ["ielts", "toefl internet", "toefl", "cambridge", "duolingo"]


def _money(amount) -> str | None:
    try:
        return f"{float(amount):,.0f} EUR"
    except (TypeError, ValueError):
        return None


def _fee_types(tuitions: list[dict] | None) -> set[str]:
    return {(t.get("tuition_fee_type") or "").lower() for t in tuitions or []}


def _only_eu_rate(tuitions: list[dict] | None) -> bool:
    """True when the source published the EU/EEA rate and nothing else.

    A third of the Dutch catalogue is like this. The statutory rate is around
    €2,700 while the non-EU rate is often eight times that, so presenting the
    lone figure without qualification reads as "the price" to exactly the
    reader it does not apply to.
    """
    types = _fee_types(tuitions)
    return bool(types) and types <= {"statutory"}


def _tuition_lines(tuitions: list[dict] | None) -> list[str]:
    if not tuitions:
        return []
    seen: dict[tuple, str] = {}
    for t in tuitions:
        money = _money(t.get("amount"))
        if not money:
            continue
        fee_type = (t.get("tuition_fee_type") or "").lower()
        label = _FEE_LABELS.get(fee_type, fee_type or "Tuition")
        period = t.get("period") or "year"
        key = (label, money, period)
        seen[key] = f"{label}: {money}/{period}"

    def sort_key(k):
        label = k[0]
        for i, name in enumerate(_FEE_ORDER):
            if _FEE_LABELS.get(name) == label:
                return (i, k[1])
        return (len(_FEE_ORDER), k[1])

    lines = [seen[k] for k in sorted(seen, key=sort_key)]
    if lines and _only_eu_rate(tuitions):
        lines.append("Non-EU rate not published by this source — "
                     "check the programme page.")
    return lines


def _tuition_summary(tuitions: list[dict] | None) -> str | None:
    """Short form for the programme row: the span of fees.

    The period is not always yearly — some programmes are priced per course —
    so it is read from the data and dropped entirely when a programme mixes
    periods, rather than assumed.
    """
    amounts: list[float] = []
    periods: set[str] = set()
    for t in tuitions or []:
        try:
            amounts.append(float(t["amount"]))
        except (KeyError, TypeError, ValueError):
            continue
        periods.add(t.get("period") or "year")
    if not amounts:
        return None
    suffix = f"/{next(iter(periods))}" if len(periods) == 1 else ""
    low, high = min(amounts), max(amounts)
    summary = (f"{low:,.0f} EUR{suffix}" if low == high
               else f"{low:,.0f}–{high:,.0f} EUR{suffix}")
    # Qualify a lone statutory figure so the row never reads as the price a
    # non-EU applicant would pay.
    if _only_eu_rate(tuitions):
        summary += " (EU/EEA only)"
    return summary


def _language_lines(requirements: list[dict] | None) -> list[str]:
    """Render language requirements, most recognisable certificate first.

    Ordering matters beyond neatness: the checklist generator reads the first
    score it sees per certificate, and the source happens to list TOEFL
    paper-based before internet-based, which would otherwise surface a 575
    where the reader expects a ~90.
    """
    if not requirements:
        return []
    def priority(item):
        text = (item.get("description") or "").lower()
        for i, name in enumerate(_CERT_PRIORITY):
            if all(word in text for word in name.split()):
                return i
        return len(_CERT_PRIORITY)
    lines = []
    for r in sorted(requirements, key=priority):
        desc, score = r.get("description"), r.get("minimum_score")
        if desc and score:
            lines.append(f"{desc}: {score}")
        elif desc:
            lines.append(str(desc))
    return lines


def _intake_label(entry: dict) -> str:
    """"September 2026" from a start_months entry, degrading gracefully."""
    start = entry.get("start_date")
    if start:
        try:
            d = date.fromisoformat(start)
            return f"{calendar.month_name[d.month]} {d.year}"
        except ValueError:
            pass
    month = entry.get("month")
    if isinstance(month, int) and 1 <= month <= 12:
        return calendar.month_name[month]
    return "Intake"


def _valid_date(value) -> str | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def _deadlines(start_months: list[dict] | None) -> list[Deadline]:
    """Build exact deadlines. No parsing — the source publishes date fields."""
    out: list[Deadline] = []
    seen: set[tuple[str, str]] = set()
    for entry in start_months or []:
        intake = _intake_label(entry)
        general = _valid_date(entry.get("application_deadline"))
        non_eu = _valid_date(entry.get("application_deadline_non_eu"))
        start = entry.get("start_date") or "?"

        if general and general == non_eu:
            pairs = [(general, "all applicants")]
        else:
            pairs = [(general, "EU/EEA applicants"), (non_eu, "non-EU applicants")]

        for iso, who in pairs:
            if not iso:
                continue
            label = f"{intake} intake / {who}"
            if (label, iso) in seen:
                continue
            seen.add((label, iso))
            out.append(Deadline(
                label=label,
                date=iso,
                confidence="exact",
                source_text=f"studyinnl.org published this date for the "
                            f"{intake} intake (start {start}), {who}.",
            ))
    return out


def _application_periods_text(start_months: list[dict] | None) -> str | None:
    lines = []
    for entry in start_months or []:
        intake = _intake_label(entry)
        general = _valid_date(entry.get("application_deadline"))
        non_eu = _valid_date(entry.get("application_deadline_non_eu"))
        parts = []
        if general:
            parts.append(f"EU/EEA: {general}")
        if non_eu:
            parts.append(f"non-EU: {non_eu}")
        if parts:
            lines.append(f"{intake} intake — " + ", ".join(parts))
    return "\n".join(lines) if lines else None


class StudyInNlAdapter:
    id = "studyinnl"
    country = "NL"

    def list_programs(self, *, degree: str = "Master",
                      sector: str | None = None,
                      subject_query: str = "",
                      max_age: float | None = 24 * 3600,
                      limit: int | None = None) -> Iterator[Listing]:
        """Walk the catalogue, filtering client-side.

        `degree` matches the source's `type` ("Master", "Bachelor", ...);
        pass None for everything. `sector` optionally narrows to e.g.
        "Research university" (the WO institutions).
        """
        offset = 0
        seen_ids: set[str] = set()
        kept = 0

        while True:
            payload = json.loads(fetch(
                build_url(API, {"limit": PAGE_SIZE, "offset": offset}),
                max_age=max_age))
            data = payload.get("data") or {}
            records = data.get("programs") or []
            if not records:
                break

            fresh = 0
            for record in records:
                record_id = str(record.get("id"))
                if record_id in seen_ids:
                    continue
                seen_ids.add(record_id)
                fresh += 1

                if degree and (record.get("type") or "") != degree:
                    continue
                institution = record.get("institution") or {}
                if sector and (institution.get("sector") or "") != sector:
                    continue
                if subject_query:
                    haystack = " ".join(filter(None, [
                        record.get("name"), record.get("field_of_study"),
                        institution.get("name")])).lower()
                    if subject_query.lower() not in haystack:
                        continue

                yield self._to_listing(record)
                kept += 1
                if limit and kept >= limit:
                    return

            if fresh == 0:      # source stopped advancing; do not spin
                break
            offset += PAGE_SIZE
            if offset >= (data.get("totalAmount") or 0):
                break

    # -- mapping -----------------------------------------------------------
    def _to_listing(self, record: dict) -> Listing:
        institution = record.get("institution") or {}
        locations = record.get("locations") or []
        start_months = record.get("start_months")

        city = institution.get("city")
        if not city and locations:
            city = locations[0].get("name")

        slug = record.get("slug")
        program = Program(
            source=self.id,
            source_id=str(record.get("id")),
            country=self.country,
            name=strip_html(record.get("name")) or "",
            university=strip_html(institution.get("name")),
            city=strip_html(city),
            degree=record.get("qualification") or record.get("type"),
            subject=record.get("field_of_study"),
            languages=[l["name"] for l in (record.get("languages") or [])
                       if l.get("name")],
            duration=record.get("duration"),
            start_terms=", ".join(dict.fromkeys(
                _intake_label(e) for e in (start_months or []))) or None,
            tuition=_tuition_summary(record.get("tuitions")),
            deadline_raw=_application_periods_text(start_months),
            detail_url=f"{SITE}{PROGRAM_PATH}{slug}" if slug else None,
            website=record.get("website"),
            # Everything the source has is already here; nothing left to fetch.
            detail_fetched_at=utcnow(),
        )
        return Listing(program=program,
                       fields=self._fields(record),
                       deadlines=_deadlines(start_months))

    def _fields(self, record: dict) -> list[Field]:
        institution = record.get("institution") or {}
        start_months = record.get("start_months")

        language_lines = _language_lines(record.get("language_requirements"))
        modes = [name for flag, name in (
            (record.get("full_time"), "full-time"),
            (record.get("part_time"), "part-time"),
            (record.get("dual"), "dual"),
        ) if flag]

        scholarships = [s["name"] for s in (record.get("scholarships") or [])
                        if s.get("name")]
        admission_urls = [u for u in (record.get("admission_url") or []) if u]

        candidates: list[tuple[str, str | None]] = [
            ("Degree", record.get("qualification")),
            ("Beginning", ", ".join(dict.fromkeys(
                _intake_label(e) for e in (start_months or []))) or None),
            ("Programme duration", record.get("duration")),
            ("ECTS credits", str(record["ects_credits"])
             if record.get("ects_credits") else None),
            ("Study mode", ", ".join(modes) or None),
            ("Field of study", record.get("field_of_study")),
            ("Institution type", institution.get("sector")),
            ("Location", ", ".join(dict.fromkeys(
                l["name"] for l in (record.get("locations") or [])
                if l.get("name"))) or None),
            ("Application periods", _application_periods_text(start_months)),
            # Stated even when unknown: every one of these programmes is taught
            # in English and will want proof, so an absent field would read as
            # "not required" rather than "not published".
            ("English language skills", "\n".join(language_lines)
             or "Not specified in the source — check the programme page."),
            ("Tuition fees", "\n".join(_tuition_lines(record.get("tuitions"))) or None),
            ("Admission information", "\n".join(admission_urls) or None),
            ("Scholarships", "\n".join(scholarships) or None),
            ("Accreditation", ", ".join(
                a["name"] for a in (record.get("accreditations") or [])
                if a.get("name")) or None),
            ("Description", strip_html(record.get("description"))),
        ]
        return [Field(label=k, value=v) for k, v in candidates if v]

    def fetch_detail(self, program: Program,
                     max_age: float | None = None) -> tuple[Program, list[Field]]:
        """No-op: listings already carry everything the source publishes."""
        return program, []
