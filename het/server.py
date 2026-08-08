"""Local web UI.

A single-user tool on localhost, so there is no auth and no framework: the
stdlib HTTP server plus a JSON API is enough, and it keeps the project at zero
dependencies. The socket is bound to 127.0.0.1 only.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import sqlite3
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import db
from .checklist import suggest
from .models import STATUSES
from .service import ensure_detail

WEB_ROOT = Path(__file__).resolve().parent / "web"


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _program_json(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "university": row["university"],
        "city": row["city"],
        "country": row["country"],
        "degree": row["degree"],
        "subject": row["subject"],
        "languages": json.loads(row["languages"] or "[]"),
        "duration": row["duration"],
        "start_terms": row["start_terms"],
        "tuition": row["tuition"],
        "deadline_raw": row["deadline_raw"],
        "detail_url": row["detail_url"],
        "website": row["website"],
        "has_detail": bool(row["detail_fetched_at"]),
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "HigherEducationTracker"
    db_path: str | None = None
    # Drop connections that stall mid-request instead of pinning a thread.
    timeout = 30
    # Exception text is useful while developing locally but should not be
    # served to anything beyond the loopback interface.
    expose_errors = True

    # -- plumbing --------------------------------------------------------
    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            raise ApiError(400, "gövde geçerli JSON değil")

    def _serve_static(self, path: str) -> None:
        rel = path.lstrip("/") or "index.html"
        target = (WEB_ROOT / rel).resolve()
        if not target.is_relative_to(WEB_ROOT) or not target.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        if not parsed.path.startswith("/api/"):
            if method == "GET":
                self._serve_static(parsed.path)
            else:
                self.send_error(405)
            return

        conn = db.connect(self.db_path)
        try:
            segments = [s for s in parsed.path[len("/api/"):].split("/") if s]
            query = parse_qs(parsed.query)
            payload = self.route(method, segments, query, conn)
            conn.commit()
            self._send_json(payload)
        except ApiError as exc:
            self._send_json({"error": exc.message}, exc.status)
        except Exception as exc:  # surface failures in the UI rather than a blank page
            print(f"[hata] {self.path}: {type(exc).__name__}: {exc}", file=sys.stderr)
            detail = f"{type(exc).__name__}: {exc}" if self.expose_errors else "sunucu hatası"
            self._send_json({"error": detail}, 500)
        finally:
            conn.close()

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_PATCH(self):
        self._dispatch("PATCH")

    def do_DELETE(self):
        self._dispatch("DELETE")

    # -- routes ----------------------------------------------------------
    def route(self, method: str, seg: list[str], query: dict, conn) -> object:
        head = seg[0] if seg else ""

        if head == "programs" and method == "GET":
            if len(seg) == 1:
                return self._list_programs(query, conn)
            return self._get_program(int(seg[1]), query, conn)

        if head == "shortlist":
            if method == "GET":
                return self._get_shortlist(conn)
            if method == "POST":
                body = self._read_json()
                status = body.get("status") or "interested"
                if status not in STATUSES:
                    raise ApiError(400, f"geçersiz durum: {status}")
                db.add_to_shortlist(conn, int(body["program_id"]), status,
                                    body.get("notes"))
                return {"ok": True}
            if method == "DELETE" and len(seg) > 1:
                db.remove_from_shortlist(conn, int(seg[1]))
                return {"ok": True}

        if head == "deadlines" and method == "GET":
            rows = db.upcoming_deadlines(
                conn,
                shortlist_only=query.get("all", ["0"])[0] != "1",
                limit=int(query.get("limit", ["200"])[0]),
            )
            return [{
                "date": r["date"], "label": r["label"], "confidence": r["confidence"],
                "source_text": r["source_text"], "program_id": r["id"],
                "name": r["name"], "university": r["university"],
            } for r in rows]

        if head == "checklist":
            if method == "POST":
                body = self._read_json()
                db.add_checklist_item(conn, int(body["program_id"]), body["label"].strip())
                return {"ok": True}
            if method == "PATCH" and len(seg) > 1:
                db.set_checklist_done(conn, int(seg[1]), bool(self._read_json().get("done")))
                return {"ok": True}
            if method == "DELETE" and len(seg) > 1:
                db.delete_checklist_item(conn, int(seg[1]))
                return {"ok": True}

        if head == "stats" and method == "GET":
            return {
                "programs": conn.execute("SELECT COUNT(*) c FROM programs").fetchone()["c"],
                "shortlist": conn.execute("SELECT COUNT(*) c FROM shortlist").fetchone()["c"],
                "countries": [r["country"] for r in conn.execute(
                    "SELECT DISTINCT country FROM programs ORDER BY country")],
                "statuses": STATUSES,
            }

        raise ApiError(404, f"bilinmeyen uç nokta: /{'/'.join(seg)}")

    # -- handlers --------------------------------------------------------
    def _list_programs(self, query: dict, conn) -> list[dict]:
        def one(key, default=None):
            return query.get(key, [default])[0]

        rows = db.search(
            conn, one("q"),
            country=one("country") or None,
            city=one("city") or None,
            free_only=one("free") == "1",
            limit=int(one("limit", "60")),
        )
        shortlisted = {r["program_id"] for r in
                       conn.execute("SELECT program_id FROM shortlist")}
        out = []
        for r in rows:
            item = _program_json(r)
            item["shortlisted"] = r["id"] in shortlisted
            out.append(item)
        return out

    def _get_program(self, program_id: int, query: dict, conn) -> dict:
        refresh = query.get("refresh", ["0"])[0] == "1"
        row = ensure_detail(conn, program_id, refresh=refresh)
        if row is None:
            raise ApiError(404, f"{program_id} numaralı program yok")

        fields = db.get_fields(conn, program_id)
        # Re-sync on every open so improvements to the generator show up. This
        # is safe: seed_checklist only touches untouched auto-generated items.
        if fields:
            db.seed_checklist(conn, program_id, suggest(fields))

        deadlines = conn.execute(
            "SELECT * FROM deadlines WHERE program_id = ? ORDER BY date", (program_id,)
        ).fetchall()
        shortlist = conn.execute(
            "SELECT * FROM shortlist WHERE program_id = ?", (program_id,)
        ).fetchone()

        payload = _program_json(row)
        payload.update({
            "fields": fields,
            "deadlines": [{"date": d["date"], "label": d["label"],
                           "confidence": d["confidence"],
                           "source_text": d["source_text"]} for d in deadlines],
            "checklist": [{"id": c["id"], "label": c["label"], "detail": c["detail"],
                           "done": bool(c["done"]), "auto": bool(c["auto"])}
                          for c in db.get_checklist(conn, program_id)],
            "shortlist": ({"status": shortlist["status"], "notes": shortlist["notes"]}
                          if shortlist else None),
        })
        return payload

    def _get_shortlist(self, conn) -> list[dict]:
        rows = conn.execute(
            """SELECT s.status, s.notes, p.* FROM shortlist s
               JOIN programs p ON p.id = s.program_id
               ORDER BY s.status, p.university""").fetchall()
        out = []
        for r in rows:
            # Seed here too, so a shortlisted programme whose requirements are
            # already known shows a real document count instead of 0/0 until
            # someone happens to open it.
            fields = db.get_fields(conn, r["id"])
            if fields and not db.get_checklist(conn, r["id"]):
                db.seed_checklist(conn, r["id"], suggest(fields))
            done, total = db.checklist_progress(conn, r["id"])
            next_deadline = conn.execute(
                "SELECT date, label FROM deadlines WHERE program_id = ? AND date >= date('now') "
                "ORDER BY date LIMIT 1", (r["id"],)).fetchone()
            item = _program_json(r)
            item.update({
                "status": r["status"],
                "notes": r["notes"],
                "checklist_done": done,
                "checklist_total": total,
                "next_deadline": (dict(next_deadline) if next_deadline else None),
            })
            out.append(item)
        return out


def _describe_binding(host: str) -> tuple[bool, str | None]:
    """Return (is_loopback, warning) for the interface we are about to bind.

    There is no authentication anywhere in this app: whoever can reach the
    socket has full read/write access. That is fine on loopback, and fine on a
    private overlay network such as Tailscale where the network itself is the
    access control. It is not fine on a public interface, so say so loudly.
    """
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        return False, (f"'{host}' bir IP değil; ne dinlediğini doğrula. "
                       "Uygulamada kimlik doğrulama yok.")
    if addr.is_loopback:
        return True, None
    # Tailscale hands out addresses from the 100.64.0.0/10 CGNAT range.
    if addr in ipaddress.ip_network("100.64.0.0/10"):
        return False, ("tailnet arayüzü dinleniyor — erişim Tailscale ile sınırlı. "
                       "Tailnet'indeki her cihaz tam yetkiyle erişebilir.")
    if addr.is_unspecified:
        return False, ("TÜM arayüzler dinleniyor (public IP dahil). "
                       "Bu uygulamada kimlik doğrulama YOK. Güvenlik duvarıyla "
                       "kapatmadıysan bunu yapma.")
    if addr.is_private:
        return False, "özel ağ arayüzü dinleniyor. Uygulamada kimlik doğrulama yok."
    return False, ("PUBLIC arayüz dinleniyor ve uygulamada kimlik doğrulama YOK. "
                   "Bunu yapma — tailnet ya da loopback + reverse proxy kullan.")


def serve(port: int = 8765, db_path: str | None = None, open_browser: bool = True,
          host: str = "127.0.0.1") -> None:
    is_loopback, warning = _describe_binding(host)
    Handler.db_path = db_path
    Handler.expose_errors = is_loopback
    db.connect(db_path).close()          # create the schema before first request
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}/"
    print(f"Higher Education Tracker — {url}  (durdurmak için Ctrl+C)")
    if warning:
        print(f"  UYARI: {warning}", file=sys.stderr)
    if open_browser and is_loopback:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nkapatıldı.")
    finally:
        httpd.server_close()
