#!/usr/bin/env python3
"""Ретранслятор комнаты: журнал событий двух игроков + запечатанная колода. Только stdlib.

  python -m poker.relay [--host 0.0.0.0] [--port 8765]

Что он знает: кто вошёл, печати оценок (хеши), раскрытые оценки — только после того, как
обе печати положены. Колоду он отдаёт в запечатанном виде; ключ собирают браузеры из двух
половин в ссылках. Комнаты берутся из sessions/*/room.json (создаёт python -m poker.new).
Развёртывание — docs/deploy-local.md, модель доверия — docs/spec-online.md.
"""
import argparse
import hashlib
import json
import re
import threading
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from poker.config import ROOT, SESSIONS

WEB = Path(__file__).resolve().parent / "web"
TYPES = {"hello", "ready", "rec", "nav", "read", "drop", "commit", "reveal", "draft", "agree",
         "pause", "back", "summary_ok", "close", "export"}
HOST_ONLY = {"rec", "nav", "drop", "close", "export"}
MAX_EVENT, MAX_EXPORT, POLL_SECONDS = 4096, 512 * 1024, 25
ROOM_RE = re.compile(r"^[A-Za-z0-9_-]{6,40}$")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class RoomError(Exception):
    def __init__(self, status, text):
        super().__init__(text)
        self.status = status


class Room:
    def __init__(self, session):
        self.dir = session
        self.meta = json.loads((session / "room.json").read_text(encoding="utf-8"))
        self.log = session / "room-log.jsonl"
        self.events = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines() if line.strip()] \
            if self.log.exists() else []
        self.cond = threading.Condition()
        self.state = {"halves": {}, "commits": {}, "reveals": {}, "summary_ok": set(), "closed": False, "export": None}
        for e in self.events:
            self._apply(e)

    def role_for(self, token):
        h = hashlib.sha256((token or "").encode()).hexdigest()
        return next((r for r, v in self.meta["tokens"].items() if v == h), None)

    def expired(self):
        return datetime.fromisoformat(self.meta["expires"]) < datetime.now(timezone.utc)

    def _apply(self, e):
        st, d, r, t = self.state, e.get("data") or {}, e["role"], e["type"]
        if t == "hello":
            st["halves"].setdefault(r, d.get("half"))
        elif t == "commit":
            st["commits"].setdefault(str(d["card"]), {}).setdefault(r, d["hash"])
        elif t == "reveal":
            st["reveals"].setdefault(str(d["card"]), set()).add(r)
        elif t == "summary_ok":
            st["summary_ok"].add(r)
        elif t == "export":
            st["export"] = d
        elif t == "close":
            st["closed"] = True

    def validate(self, role, t, d):
        st = self.state
        if st["closed"]:
            raise RoomError(HTTPStatus.CONFLICT, "встреча закрыта")
        if t not in TYPES:
            raise RoomError(HTTPStatus.BAD_REQUEST, f"неизвестное событие {t}")
        if t in HOST_ONLY and role != "host":
            raise RoomError(HTTPStatus.FORBIDDEN, "это действие ведущего")
        if not isinstance(d, dict):
            raise RoomError(HTTPStatus.BAD_REQUEST, "data должно быть объектом")
        card = str(d.get("card"))
        if t == "hello":
            half = d.get("half")
            if not isinstance(half, str) or len(half) > 64:
                raise RoomError(HTTPStatus.BAD_REQUEST, "нет половины ключа")
            if st["halves"].get(role) not in (None, half):
                raise RoomError(HTTPStatus.CONFLICT, "другая половина ключа для этой роли")
        if t == "commit":
            if not re.fullmatch(r"[0-9a-f]{64}", str(d.get("hash", ""))):
                raise RoomError(HTTPStatus.BAD_REQUEST, "печать — 64 hex-символа")
            if role in st["commits"].get(card, {}):
                raise RoomError(HTTPStatus.CONFLICT, "карта уже положена")
        if t == "reveal":
            if set(st["commits"].get(card, {})) != {"host", "guest"}:
                raise RoomError(HTTPStatus.CONFLICT, "вскрытие — только когда положили оба")
            if role in st["reveals"].get(card, set()):
                raise RoomError(HTTPStatus.CONFLICT, "оценка уже вскрыта")
            want = st["commits"][card][role]
            got = hashlib.sha256(f"{d.get('card')}|{role}|{d.get('vote')}|{d.get('salt')}|{d.get('why', '')}".encode()).hexdigest()
            if got != want:
                raise RoomError(HTTPStatus.CONFLICT, "оценка не совпадает с печатью")
        if t == "close":
            if st["summary_ok"] != {"host", "guest"}:
                raise RoomError(HTTPStatus.CONFLICT, "оба должны подтвердить итоги")
            if not st["export"]:
                raise RoomError(HTTPStatus.CONFLICT, "нет итогов для сохранения")

    def append(self, role, t, d):
        with self.cond:
            self.validate(role, t, d)
            e = {"seq": len(self.events) + 1, "ts": now(), "role": role, "type": t, "data": d}
            self.events.append(e)
            self._apply(e)
            with self.log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
            if t == "close":
                self._write_results()
            self.cond.notify_all()
            return e

    def _write_results(self):
        ex = self.state["export"]
        (self.dir / "results.md").write_text(ex.get("md", ""), encoding="utf-8")
        summary = dict(ex.get("summary") or {}, period=self.meta["period"], date=now()[:10])
        (self.dir / "results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    def since(self, n, wait):
        with self.cond:
            if len(self.events) <= n and wait:
                self.cond.wait(timeout=wait)
            return self.events[n:]


class Rooms:
    def __init__(self, sessions):
        self.sessions, self.rooms, self.lock = Path(sessions), {}, threading.Lock()

    def get(self, room_id):
        if not ROOM_RE.match(room_id or ""):
            return None
        with self.lock:
            if room_id not in self.rooms:
                for p in self.sessions.glob("*/room.json"):
                    try:
                        if json.loads(p.read_text(encoding="utf-8")).get("room_id") == room_id:
                            self.rooms[room_id] = Room(p.parent)
                            break
                    except (OSError, ValueError):
                        continue
            return self.rooms.get(room_id)


def make_handler(rooms, quiet=False):
    class Handler(BaseHTTPRequestHandler):
        server_version = "mgmt-poker"

        def log_message(self, fmt, *args):  # без токенов и тел запросов
            if not quiet:
                print(f"{self.address_string()} {self.command} {urlparse(self.path).path} → {args[1] if len(args) > 1 else ''}")

        def _send(self, status, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(data)

        def _room(self, room_id):
            room = rooms.get(room_id)
            if not room:
                raise RoomError(HTTPStatus.NOT_FOUND, "комната не найдена")
            if room.expired():
                raise RoomError(HTTPStatus.GONE, "срок комнаты истёк")
            role = room.role_for(self.headers.get("X-Poker-Token"))
            if not role:
                raise RoomError(HTTPStatus.UNAUTHORIZED, "ссылка недействительна")
            return room, role

        def do_GET(self):
            u = urlparse(self.path)
            parts = [p for p in u.path.split("/") if p]
            try:
                if u.path == "/health":
                    return self._send(200, {"ok": True})
                if len(parts) == 2 and parts[0] == "r":
                    return self._send(200, (WEB / "room.html").read_bytes(), "text/html; charset=utf-8")
                if u.path == "/static/core.js":
                    return self._send(200, (WEB / "core.js").read_bytes(), "text/javascript; charset=utf-8")
                if len(parts) == 4 and parts[:2] == ["api", "r"]:
                    room, role = self._room(parts[2])
                    if parts[3] == "deck":
                        return self._send(200, json.loads((room.dir / "deck.sealed.json").read_text(encoding="utf-8")))
                    if parts[3] == "events":
                        q = parse_qs(u.query)
                        n = max(0, int(q.get("since", ["0"])[0]))
                        wait = POLL_SECONDS if q.get("wait", ["1"])[0] == "1" else 0
                        return self._send(200, {"role": role, "events": room.since(n, wait)})
                self._send(404, {"error": "не найдено"})
            except RoomError as e:
                self._send(e.status, {"error": str(e)})
            except ValueError:
                self._send(400, {"error": "неверный запрос"})

        def do_POST(self):
            parts = [p for p in urlparse(self.path).path.split("/") if p]
            try:
                if not (len(parts) == 4 and parts[:2] == ["api", "r"] and parts[3] == "events"):
                    return self._send(404, {"error": "не найдено"})
                room, role = self._room(parts[2])
                size = int(self.headers.get("Content-Length", "0"))
                if size > MAX_EXPORT:
                    raise RoomError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "слишком большое событие")
                body = json.loads(self.rfile.read(size) or b"{}")
                t = body.get("type")
                if t != "export" and size > MAX_EVENT:
                    raise RoomError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "слишком большое событие")
                e = room.append(role, t, body.get("data") or {})
                self._send(200, {"seq": e["seq"]})
            except RoomError as e:
                self._send(e.status, {"error": str(e)})
            except (ValueError, KeyError, TypeError):
                self._send(400, {"error": "неверное событие"})

    return Handler


def serve(host="127.0.0.1", port=8765, sessions=SESSIONS, quiet=False):
    httpd = ThreadingHTTPServer((host, port), make_handler(Rooms(sessions), quiet))
    httpd.daemon_threads = True
    return httpd


def main():
    cfg_path = ROOT / "config" / "relay.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=cfg.get("host", "127.0.0.1"), help="0.0.0.0 — чтобы комната была видна в VPN")
    ap.add_argument("--port", type=int, default=cfg.get("port", 8765))
    args = ap.parse_args()
    httpd = serve(args.host, args.port)
    print(f"Комната слушает http://{args.host}:{args.port} · сессии: {SESSIONS} · Ctrl+C — остановить")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nостановлено")


if __name__ == "__main__":
    main()
