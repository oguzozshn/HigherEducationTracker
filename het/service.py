"""Operations shared by the CLI and the web server."""

from __future__ import annotations

import json
import sqlite3

from . import db
from .adapters import ADAPTERS
from .checklist import suggest
from .deadlines import parse_deadlines
from .models import Program


def _row_to_program(row: sqlite3.Row) -> Program:
    return Program(
        source=row["source"], source_id=row["source_id"], country=row["country"],
        name=row["name"], university=row["university"], city=row["city"],
        degree=row["degree"], subject=row["subject"],
        languages=json.loads(row["languages"] or "[]"),
        duration=row["duration"], start_terms=row["start_terms"],
        tuition=row["tuition"], deadline_raw=row["deadline_raw"],
        detail_url=row["detail_url"], website=row["website"],
    )


def ensure_detail(conn: sqlite3.Connection, program_id: int, *,
                  refresh: bool = False) -> sqlite3.Row | None:
    """Make sure a programme's detail page has been fetched and parsed.

    Fetching is the expensive part of the pipeline, so it happens lazily: only
    when the user actually opens a programme. Already-fetched programmes are
    served from the database untouched unless `refresh` is set.
    """
    row = conn.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone()
    if row is None:
        return None
    if row["detail_fetched_at"] and not refresh:
        return row

    adapter_key = row["country"].lower()
    if adapter_key not in ADAPTERS:
        return row
    adapter = ADAPTERS[adapter_key]()

    program, fields = adapter.fetch_detail(
        _row_to_program(row), max_age=None if refresh else 7 * 24 * 3600
    )
    db.upsert_program(conn, program)
    db.replace_fields(conn, program_id, fields)
    db.replace_deadlines(conn, program_id, parse_deadlines(program.deadline_raw))
    db.seed_checklist(conn, program_id, suggest({f.label: f.value for f in fields}))
    conn.commit()
    return conn.execute("SELECT * FROM programs WHERE id = ?", (program_id,)).fetchone()
