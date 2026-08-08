"""Command line interface.

    python -m het ingest de --subject "computer science"
    python -m het search robotics --free
    python -m het show 4722
    python -m het shortlist add 4722
    python -m het deadlines
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap

from . import db
from .adapters import ADAPTERS, DaadAdapter, StudyInNlAdapter
from .adapters.daad_de import LANG_ENGLISH
from .deadlines import parse_deadlines
from .models import STATUSES
from .service import ensure_detail

# Labels worth printing first; everything else follows. Sources overlap only
# partly, so this is the union across countries.
KEY_LABELS = [
    "Degree",
    "Academic admission requirements",
    "Admission information",
    "English language skills",
    "German language skills",
    "Application periods",
    "Submit application via",
    "Tuition fees",
    "Tuition fees per semester",
    "Semester contribution",
    "Costs of living",
    "Programme duration",
    "ECTS credits",
    "Beginning",
    "Scholarships",
]


def _wrap(text: str, indent: str = "      ") -> str:
    out = []
    for para in (text or "").split("\n"):
        para = para.strip()
        if para:
            out.append(textwrap.fill(para, width=100, initial_indent=indent,
                                     subsequent_indent=indent))
    return "\n".join(out)


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_ingest(args, conn) -> int:
    if args.country not in ADAPTERS:
        print(f"unknown country '{args.country}'. available: {', '.join(ADAPTERS)}")
        return 1
    adapter = ADAPTERS[args.country]()
    max_age = None if args.refresh else 24 * 3600

    kwargs: dict[str, object] = {
        "subject_query": args.subject or "",
        "max_age": max_age,
        "limit": args.limit,
    }
    # Only send switches the source actually understands. Both of these APIs
    # accept unknown parameters and ignore them silently, so a misdirected
    # option would look like it worked.
    if isinstance(adapter, DaadAdapter):
        kwargs["language"] = None if args.all_languages else LANG_ENGLISH
    elif isinstance(adapter, StudyInNlAdapter):
        kwargs["degree"] = None if args.all_degrees else "Master"
        if args.wo_only:
            kwargs["sector"] = "Research university"

    count = 0
    for listing in adapter.list_programs(**kwargs):
        program_id = db.upsert_program(conn, listing.program)
        if listing.fields:
            db.replace_fields(conn, program_id, listing.fields)
        # A source that publishes real dates supplies them; otherwise fall back
        # to reading them out of the prose.
        found = (listing.deadlines if listing.deadlines is not None
                 else parse_deadlines(listing.program.deadline_raw))
        db.replace_deadlines(conn, program_id, found)
        count += 1
        if count % 100 == 0:
            conn.commit()
            print(f"  ... {count}", file=sys.stderr)
    conn.commit()
    print(f"{count} programmes ingested from {adapter.id} ({adapter.country}).")
    return 0


def cmd_search(args, conn) -> int:
    rows = db.search(conn, args.query, country=args.country, city=args.city,
                     free_only=args.free, limit=args.limit)
    if not rows:
        print("no matches.")
        return 0
    for r in rows:
        langs = ", ".join(json.loads(r["languages"] or "[]"))
        print(f"[{r['id']:>5}] {r['name']}")
        print(f"        {r['university']} — {r['city']} ({r['country']})")
        print(f"        {r['subject'] or '-'} | {r['duration'] or '-'} | {langs} | {r['tuition'] or '-'}")
        if r["deadline_raw"]:
            print(f"        deadline: {r['deadline_raw'][:90]}")
        print()
    print(f"{len(rows)} result(s).")
    return 0


def cmd_show(args, conn) -> int:
    if not conn.execute("SELECT 1 FROM programs WHERE id = ?", (args.id,)).fetchone():
        print(f"no programme with id {args.id}. run `search` first.")
        return 1
    if args.refresh or not conn.execute(
            "SELECT detail_fetched_at FROM programs WHERE id = ?", (args.id,)
    ).fetchone()["detail_fetched_at"]:
        print("fetching detail page ...", file=sys.stderr)

    row = ensure_detail(conn, args.id, refresh=args.refresh)
    fields = db.get_fields(conn, args.id)

    print(f"\n{row['name']}")
    print(f"{row['university']} — {row['city']}, {row['country']}")
    print("=" * 100)
    for label in KEY_LABELS:
        if label in fields:
            print(f"\n  {label}")
            print(_wrap(fields[label]))
    if args.all:
        for label, value in fields.items():
            if label not in KEY_LABELS:
                print(f"\n  {label}")
                print(_wrap(value))

    deadline_rows = conn.execute(
        "SELECT * FROM deadlines WHERE program_id = ? ORDER BY date", (args.id,)
    ).fetchall()
    if deadline_rows:
        print("\n  Parsed deadlines (verify against the official page)")
        for d in deadline_rows:
            print(f"      {d['date']}  {d['label']}   [{d['confidence']}]")

    print(f"\n  Source page : {row['detail_url']}")
    if row["website"]:
        print(f"  Official    : {row['website']}")
    print()
    return 0


def cmd_reparse(args, conn) -> int:
    """Re-run deadline parsing over already-stored text — no network access.

    The parser improves over time; this replays it without re-fetching anything.
    """
    # Skip programmes whose dates the source published outright: re-deriving
    # them from prose would replace exact dates with guesses.
    rows = conn.execute(
        """SELECT id, deadline_raw FROM programs p
           WHERE deadline_raw IS NOT NULL
             AND NOT EXISTS (SELECT 1 FROM deadlines d
                             WHERE d.program_id = p.id AND d.confidence = 'exact')"""
    ).fetchall()
    total = 0
    for r in rows:
        found = parse_deadlines(r["deadline_raw"])
        db.replace_deadlines(conn, r["id"], found)
        total += len(found)
    conn.commit()
    print(f"re-parsed {len(rows)} programme(s), {total} deadline(s).")
    return 0


def cmd_shortlist(args, conn) -> int:
    if args.action == "add":
        conn.execute("SELECT 1")
        row = conn.execute("SELECT id, name FROM programs WHERE id = ?", (args.id,)).fetchone()
        if not row:
            print(f"no programme with id {args.id}.")
            return 1
        db.add_to_shortlist(conn, args.id, args.status or "interested", args.notes)
        conn.commit()
        print(f"added: {row['name']}")
        return 0

    rows = conn.execute(
        """SELECT s.status, s.notes, p.* FROM shortlist s
           JOIN programs p ON p.id = s.program_id
           ORDER BY s.status, p.university""").fetchall()
    if not rows:
        print("shortlist is empty. add one with:  python -m het shortlist add <id>")
        return 0
    for r in rows:
        print(f"[{r['id']:>5}] {r['status']:<11} {r['name']}")
        print(f"        {r['university']} — {r['city']}")
        if r["notes"]:
            print(f"        note: {r['notes']}")
    return 0


def cmd_serve(args, conn) -> int:
    # The server opens its own connection per request; close this one first.
    conn.close()
    from .server import serve
    serve(port=args.port, db_path=args.db, open_browser=not args.no_browser,
          host=args.host)
    return 0


def cmd_deadlines(args, conn) -> int:
    rows = db.upcoming_deadlines(conn, shortlist_only=not args.all, limit=args.limit)
    if not rows:
        scope = "" if args.all else " on your shortlist"
        print(f"no upcoming deadlines{scope}.")
        return 0
    parsed = 0
    for r in rows:
        mark = "exact " if r["confidence"] == "exact" else "parsed"
        parsed += r["confidence"] != "exact"
        print(f"{r['date']}  [{mark}] [{r['id']:>5}] {r['name'][:48]}")
        print(f"                     {r['university']} — {r['label']}")
    print(f"\n{len(rows)} deadline(s).")
    if parsed:
        print(f"{parsed} of them were read out of prose rather than published as "
              f"dates — confirm those on the official page before relying on them.")
    return 0


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="het", description="Higher Education Tracker")
    p.add_argument("--db", help="path to the sqlite file")
    sub = p.add_subparsers(dest="command", required=True)

    ing = sub.add_parser("ingest", help="pull the programme catalogue for a country")
    ing.add_argument("country", choices=sorted(ADAPTERS))
    ing.add_argument("--subject", help="free-text subject filter passed to the source")
    ing.add_argument("--limit", type=int, help="stop after N programmes")
    ing.add_argument("--all-languages", action="store_true",
                     help="[de] include programmes not taught in English")
    ing.add_argument("--all-degrees", action="store_true",
                     help="[nl] include bachelors and short courses, not just masters")
    ing.add_argument("--wo-only", action="store_true",
                     help="[nl] research universities only, excluding hogescholen")
    ing.add_argument("--refresh", action="store_true", help="bypass the HTTP cache")
    ing.set_defaults(func=cmd_ingest)

    se = sub.add_parser("search", help="search ingested programmes")
    se.add_argument("query", nargs="?")
    se.add_argument("--country")
    se.add_argument("--city")
    se.add_argument("--free", action="store_true", help="only tuition-free programmes")
    se.add_argument("--limit", type=int, default=30)
    se.set_defaults(func=cmd_search)

    sh = sub.add_parser("show", help="show full requirements for one programme")
    sh.add_argument("id", type=int)
    sh.add_argument("--all", action="store_true", help="print every field, not just key ones")
    sh.add_argument("--refresh", action="store_true")
    sh.set_defaults(func=cmd_show)

    sv = sub.add_parser("serve", help="open the local web UI")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--host", default="127.0.0.1",
                    help="interface to bind (default: loopback only). There is no "
                         "authentication, so only widen this on a private network.")
    sv.add_argument("--no-browser", action="store_true")
    sv.set_defaults(func=cmd_serve)

    rp = sub.add_parser("reparse", help="re-run deadline parsing on stored data (offline)")
    rp.set_defaults(func=cmd_reparse)

    sl = sub.add_parser("shortlist", help="track programmes you are applying to")
    sl.add_argument("action", nargs="?", choices=["add", "list"], default="list")
    sl.add_argument("id", nargs="?", type=int)
    sl.add_argument("--status", choices=STATUSES)
    sl.add_argument("--notes")
    sl.set_defaults(func=cmd_shortlist)

    dl = sub.add_parser("deadlines", help="upcoming deadlines")
    dl.add_argument("--all", action="store_true", help="not just the shortlist")
    dl.add_argument("--limit", type=int, default=40)
    dl.set_defaults(func=cmd_deadlines)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    conn = db.connect(args.db)
    try:
        return args.func(args, conn)
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
