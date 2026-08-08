#!/usr/bin/env python3
"""Copy personal state between two Higher Education Tracker databases.

    python3 deploy/migrate_state.py --from local.db --to server.db          # plan
    python3 deploy/migrate_state.py --from local.db --to server.db --apply

Why this exists instead of copying the file: `programs.id` is a local
autoincrement, so the same programme has different ids in two databases built
by different ingests. Copying `shortlist` rows verbatim would attach the
shortlist to whichever unrelated programmes happen to hold those ids. Rows are
therefore matched on `(source, source_id)`, which is stable across databases.

Only state the user created is copied — shortlist entries and their statuses
and notes, ticked or hand-added checklist items, and manually entered
deadlines. Auto-generated checklist items that were never touched are left
behind on purpose: the target regenerates them from its own copy of the
requirements, so copying them would just risk carrying over stale suggestions.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path


def connect(path: Path, *, read_only: bool) -> sqlite3.Connection:
    if not path.exists():
        sys.exit(f"veritabanı yok: {path}")
    uri = f"file:{path.as_posix()}?mode={'ro' if read_only else 'rw'}"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def build_index(conn: sqlite3.Connection) -> dict[tuple[str, str], int]:
    """Map (source, source_id) -> local programme id in the target."""
    return {(r["source"], r["source_id"]): r["id"]
            for r in conn.execute("SELECT id, source, source_id FROM programs")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", required=True, type=Path)
    ap.add_argument("--to", dest="dst", required=True, type=Path)
    ap.add_argument("--apply", action="store_true",
                    help="actually write; without it the run is a dry run")
    ap.add_argument("--with-details", action="store_true",
                    help="also carry over already-fetched requirement text, so "
                         "the target need not re-fetch those detail pages")
    args = ap.parse_args()

    src = connect(args.src, read_only=True)
    dst = connect(args.dst, read_only=not args.apply)
    index = build_index(dst)
    print(f"kaynak: {args.src}\nhedef : {args.dst}  ({len(index)} program)\n")

    planned: list[str] = []
    skipped: list[str] = []

    def resolve(row) -> int | None:
        key = (row["source"], row["source_id"])
        target_id = index.get(key)
        if target_id is None:
            skipped.append(f"  hedefte yok: {row['name']} ({key[0]}/{key[1]})")
        return target_id

    # -- shortlist ---------------------------------------------------------
    for row in src.execute(
        """SELECT s.status, s.priority, s.notes, s.added_at,
                  p.source, p.source_id, p.name
           FROM shortlist s JOIN programs p ON p.id = s.program_id"""
    ):
        target_id = resolve(row)
        if target_id is None:
            continue
        planned.append(f"  kısa liste: {row['name']}  [{row['status']}]")
        if args.apply:
            dst.execute(
                """INSERT INTO shortlist (program_id, status, priority, notes, added_at)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT (program_id) DO UPDATE SET
                       status   = excluded.status,
                       priority = excluded.priority,
                       notes    = COALESCE(excluded.notes, shortlist.notes)""",
                (target_id, row["status"], row["priority"], row["notes"],
                 row["added_at"]),
            )

    # -- checklist: only what the user touched ------------------------------
    for row in src.execute(
        """SELECT c.label, c.detail, c.done, c.auto, c.created_at,
                  p.source, p.source_id, p.name
           FROM checklist_items c JOIN programs p ON p.id = c.program_id
           WHERE c.done = 1 OR c.auto = 0"""
    ):
        target_id = resolve(row)
        if target_id is None:
            continue
        mark = "işaretli" if row["done"] else "kullanıcı maddesi"
        planned.append(f"  checklist ({mark}): {row['name']} — {row['label']}")
        if args.apply:
            dst.execute(
                """INSERT INTO checklist_items
                       (program_id, label, detail, done, auto, created_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT (program_id, label) DO UPDATE SET
                       done = excluded.done""",
                (target_id, row["label"], row["detail"], row["done"], row["auto"],
                 row["created_at"]),
            )

    # -- manually entered deadlines ----------------------------------------
    for row in src.execute(
        """SELECT d.label, d.date, d.source_text, p.source, p.source_id, p.name
           FROM deadlines d JOIN programs p ON p.id = d.program_id
           WHERE d.confidence = 'manual'"""
    ):
        target_id = resolve(row)
        if target_id is None:
            continue
        planned.append(f"  elle girilen tarih: {row['name']} — {row['date']}")
        if args.apply:
            dst.execute(
                """INSERT OR IGNORE INTO deadlines
                       (program_id, label, date, confidence, source_text)
                   VALUES (?,?,?,'manual',?)""",
                (target_id, row["label"], row["date"], row["source_text"]),
            )

    # -- already-fetched requirement text (optional) ------------------------
    if args.with_details:
        for row in src.execute(
            """SELECT id, source, source_id, name, degree, website,
                      deadline_raw, detail_fetched_at
               FROM programs WHERE detail_fetched_at IS NOT NULL"""
        ):
            target_id = resolve(row)
            if target_id is None:
                continue
            already = dst.execute(
                "SELECT detail_fetched_at FROM programs WHERE id = ?", (target_id,)
            ).fetchone()["detail_fetched_at"]
            if already:
                continue
            fields = src.execute(
                "SELECT label, value FROM program_fields WHERE program_id = ?",
                (row["id"],)).fetchall()
            planned.append(f"  detay ({len(fields)} alan): {row['name']}")
            if args.apply:
                dst.execute(
                    """UPDATE programs SET degree = COALESCE(?, degree),
                                           website = COALESCE(?, website),
                                           deadline_raw = ?,
                                           detail_fetched_at = ?
                       WHERE id = ?""",
                    (row["degree"], row["website"], row["deadline_raw"],
                     row["detail_fetched_at"], target_id))
                dst.executemany(
                    """INSERT OR REPLACE INTO program_fields (program_id, label, value)
                       VALUES (?,?,?)""",
                    [(target_id, f["label"], f["value"]) for f in fields])

    # -- report -------------------------------------------------------------
    print("aktarılacak:" if not args.apply else "aktarıldı:")
    print("\n".join(planned) if planned else "  (yok)")
    if skipped:
        print("\natlandı (hedef katalogda bulunamadı):")
        print("\n".join(sorted(set(skipped))))

    if args.apply:
        dst.commit()
        print(f"\n{len(planned)} kayıt yazıldı.")
    else:
        print(f"\nkuru çalışma — {len(planned)} kayıt yazılacak. "
              f"Uygulamak için --apply ekle.")
    src.close()
    dst.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
