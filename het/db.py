"""SQLite storage.

One file, no server, no ORM — this is a single-user tool and the whole dataset
is a few thousand rows.
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from .models import Deadline, Field, Program, utcnow

DEFAULT_DB = Path(os.environ.get("HET_DB")
                  or Path(__file__).resolve().parent.parent / "data" / "het.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS programs (
    id                INTEGER PRIMARY KEY,
    source            TEXT NOT NULL,
    source_id         TEXT NOT NULL,
    country           TEXT NOT NULL,
    name              TEXT NOT NULL,
    university        TEXT,
    city              TEXT,
    degree            TEXT,
    subject           TEXT,
    languages         TEXT,          -- JSON array
    duration          TEXT,
    start_terms       TEXT,
    tuition           TEXT,
    deadline_raw      TEXT,
    detail_url        TEXT,
    website           TEXT,
    fetched_at        TEXT NOT NULL,
    detail_fetched_at TEXT,
    UNIQUE (source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_programs_country ON programs (country);
CREATE INDEX IF NOT EXISTS idx_programs_subject ON programs (subject);

-- Detail-page attributes, kept as raw label/value pairs (see models.py).
CREATE TABLE IF NOT EXISTS program_fields (
    program_id INTEGER NOT NULL REFERENCES programs (id) ON DELETE CASCADE,
    label      TEXT NOT NULL,
    value      TEXT,
    PRIMARY KEY (program_id, label)
);

CREATE TABLE IF NOT EXISTS deadlines (
    id          INTEGER PRIMARY KEY,
    program_id  INTEGER NOT NULL REFERENCES programs (id) ON DELETE CASCADE,
    label       TEXT,
    date        TEXT NOT NULL,      -- ISO YYYY-MM-DD
    confidence  TEXT NOT NULL,      -- parsed | manual
    source_text TEXT,
    UNIQUE (program_id, label, date)
);

CREATE INDEX IF NOT EXISTS idx_deadlines_date ON deadlines (date);

-- The user's own shortlist / application tracker.
CREATE TABLE IF NOT EXISTS shortlist (
    program_id INTEGER PRIMARY KEY REFERENCES programs (id) ON DELETE CASCADE,
    status     TEXT NOT NULL DEFAULT 'interested',
    priority   INTEGER,
    notes      TEXT,
    added_at   TEXT NOT NULL
);

-- Per-programme document checklist. Items are seeded from the extracted
-- requirements (auto=1) but the user can tick, add and delete freely; a
-- re-seed never touches anything the user has changed.
CREATE TABLE IF NOT EXISTS checklist_items (
    id         INTEGER PRIMARY KEY,
    program_id INTEGER NOT NULL REFERENCES programs (id) ON DELETE CASCADE,
    label      TEXT NOT NULL,
    detail     TEXT,
    done       INTEGER NOT NULL DEFAULT 0,
    auto       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE (program_id, label)
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    p = Path(path) if path else DEFAULT_DB
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # The web server opens one connection per request across threads, so a
    # write can find the database briefly locked; wait rather than error out.
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_program(conn: sqlite3.Connection, prog: Program) -> int:
    """Insert or update a programme, returning its local id.

    Detail-only columns (website, detail_fetched_at) are left alone when the
    incoming record does not carry them, so a cheap list-refresh never wipes
    data gathered by an expensive detail fetch.
    """
    cur = conn.execute(
        """
        INSERT INTO programs (source, source_id, country, name, university, city,
                              degree, subject, languages, duration, start_terms,
                              tuition, deadline_raw, detail_url, website,
                              fetched_at, detail_fetched_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT (source, source_id) DO UPDATE SET
            country           = excluded.country,
            name              = excluded.name,
            university        = excluded.university,
            city              = excluded.city,
            degree            = excluded.degree,
            subject           = excluded.subject,
            languages         = excluded.languages,
            duration          = excluded.duration,
            start_terms       = excluded.start_terms,
            tuition           = excluded.tuition,
            deadline_raw      = excluded.deadline_raw,
            detail_url        = excluded.detail_url,
            website           = COALESCE(excluded.website, programs.website),
            fetched_at        = excluded.fetched_at,
            detail_fetched_at = COALESCE(excluded.detail_fetched_at,
                                         programs.detail_fetched_at)
        RETURNING id
        """,
        (
            prog.source, prog.source_id, prog.country, prog.name, prog.university,
            prog.city, prog.degree, prog.subject, json.dumps(prog.languages),
            prog.duration, prog.start_terms, prog.tuition, prog.deadline_raw,
            prog.detail_url, prog.website, prog.fetched_at, prog.detail_fetched_at,
        ),
    )
    return cur.fetchone()[0]


def replace_fields(conn: sqlite3.Connection, program_id: int, fields: list[Field]) -> None:
    conn.execute("DELETE FROM program_fields WHERE program_id = ?", (program_id,))
    conn.executemany(
        "INSERT OR REPLACE INTO program_fields (program_id, label, value) VALUES (?,?,?)",
        [(program_id, f.label, f.value) for f in fields],
    )


def replace_deadlines(conn: sqlite3.Connection, program_id: int,
                      deadlines: list[Deadline]) -> None:
    """Replace source-derived deadlines, never touching manual ones.

    Anything not marked 'manual' came from an ingest and is safe to regenerate;
    what the user typed themselves survives every refresh.
    """
    conn.execute(
        "DELETE FROM deadlines WHERE program_id = ? AND confidence <> 'manual'",
        (program_id,),
    )
    conn.executemany(
        """INSERT OR IGNORE INTO deadlines (program_id, label, date, confidence, source_text)
           VALUES (?,?,?,?,?)""",
        [(program_id, d.label, d.date, d.confidence, d.source_text) for d in deadlines],
    )


def get_fields(conn: sqlite3.Connection, program_id: int) -> dict[str, str]:
    rows = conn.execute(
        "SELECT label, value FROM program_fields WHERE program_id = ?", (program_id,)
    ).fetchall()
    return {r["label"]: r["value"] for r in rows}


def add_to_shortlist(conn: sqlite3.Connection, program_id: int,
                     status: str = "interested", notes: str | None = None) -> None:
    conn.execute(
        """INSERT INTO shortlist (program_id, status, notes, added_at) VALUES (?,?,?,?)
           ON CONFLICT (program_id) DO UPDATE SET
               status = excluded.status,
               notes  = COALESCE(excluded.notes, shortlist.notes)""",
        (program_id, status, notes, utcnow()),
    )


def remove_from_shortlist(conn: sqlite3.Connection, program_id: int) -> None:
    conn.execute("DELETE FROM shortlist WHERE program_id = ?", (program_id,))


# -- checklist ---------------------------------------------------------------

def seed_checklist(conn: sqlite3.Connection, program_id: int,
                   suggestions: list[tuple[str, str]]) -> None:
    """Sync generated items, leaving the user's own rows and ticks alone.

    Suggestions change as the generator improves, so items it no longer
    proposes are withdrawn — but only while they are untouched. Anything the
    user added or already ticked off stays put.
    """
    labels = [label for label, _ in suggestions]
    placeholders = ",".join("?" * len(labels)) or "NULL"
    conn.execute(
        f"""DELETE FROM checklist_items
            WHERE program_id = ? AND auto = 1 AND done = 0
              AND label NOT IN ({placeholders})""",
        [program_id, *labels],
    )
    conn.executemany(
        """INSERT OR IGNORE INTO checklist_items
               (program_id, label, detail, done, auto, created_at)
           VALUES (?,?,?,0,1,?)""",
        [(program_id, label, detail, utcnow()) for label, detail in suggestions],
    )


def get_checklist(conn: sqlite3.Connection, program_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM checklist_items WHERE program_id = ? ORDER BY auto DESC, id",
        (program_id,),
    ).fetchall()


def add_checklist_item(conn: sqlite3.Connection, program_id: int, label: str) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO checklist_items
               (program_id, label, detail, done, auto, created_at)
           VALUES (?,?,NULL,0,0,?)""",
        (program_id, label, utcnow()),
    )


def set_checklist_done(conn: sqlite3.Connection, item_id: int, done: bool) -> None:
    conn.execute("UPDATE checklist_items SET done = ? WHERE id = ?",
                 (1 if done else 0, item_id))


def delete_checklist_item(conn: sqlite3.Connection, item_id: int) -> None:
    conn.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))


def checklist_progress(conn: sqlite3.Connection, program_id: int) -> tuple[int, int]:
    row = conn.execute(
        "SELECT COUNT(*) total, COALESCE(SUM(done), 0) done "
        "FROM checklist_items WHERE program_id = ?", (program_id,)
    ).fetchone()
    return row["done"], row["total"]


def search(conn: sqlite3.Connection, query: str | None = None, *,
           country: str | None = None, city: str | None = None,
           free_only: bool = False, limit: int = 50) -> list[sqlite3.Row]:
    sql = ["SELECT * FROM programs WHERE 1=1"]
    args: list[object] = []
    if query:
        sql.append("AND (name LIKE ? OR subject LIKE ? OR university LIKE ?)")
        args += [f"%{query}%"] * 3
    if country:
        sql.append("AND country = ?")
        args.append(country.upper())
    if city:
        sql.append("AND city LIKE ?")
        args.append(f"%{city}%")
    if free_only:
        sql.append("AND (tuition LIKE '%No tuition%' OR tuition LIKE '%None%')")
    sql.append("ORDER BY university, name LIMIT ?")
    args.append(limit)
    return conn.execute(" ".join(sql), args).fetchall()


def upcoming_deadlines(conn: sqlite3.Connection, *, shortlist_only: bool = True,
                       limit: int = 50) -> list[sqlite3.Row]:
    join = "JOIN shortlist s ON s.program_id = p.id" if shortlist_only else ""
    return conn.execute(
        f"""
        SELECT d.date, d.label, d.confidence, d.source_text,
               p.id, p.name, p.university, p.country
        FROM deadlines d
        JOIN programs p ON p.id = d.program_id
        {join}
        WHERE d.date >= date('now')
        ORDER BY d.date
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
