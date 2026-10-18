import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from poker.new import create
from poker.relay import serve
from poker.seal import commitment

ROOT = Path(__file__).resolve().parent.parent
ACTIVITY = json.loads((ROOT / "examples" / "demo-activity.json").read_text(encoding="utf-8"))


class RelayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.httpd = serve("127.0.0.1", 0, sessions=cls.tmp.name, quiet=True)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.tmp.cleanup()

    def setUp(self):
        login = f"u{self._testMethodName[-12:]}".replace("_", "")
        self.session, _, _, _, url = create(
            ACTIVITY, login=login, role="developer", name="Алексей", manager="Ирина",
            date_from="2026-09-01", date_to="2026-09-30", relay_url=f"http://127.0.0.1:{self.port}",
            sessions=self.tmp.name)
        self.room = urlparse(url["host"]).path.split("/")[2]
        self.tok = {r: parse_qs(urlparse(url[r]).fragment)["t"][0] for r in ("host", "guest")}
        self.half = {r: parse_qs(urlparse(url[r]).fragment)["k"][0] for r in ("host", "guest")}

    def call(self, role, method="GET", path="events?wait=0", body=None, token=None):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/r/{self.room}/{path}", method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"X-Poker-Token": token if token is not None else self.tok[role], "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def ev(self, role, type_, **data):
        return self.call(role, "POST", "events", {"type": type_, "data": data})

    def vote(self, role, card, vote, why="пример", salt="s"):
        self.assertEqual(self.ev(role, "commit", card=card, hash=commitment(card, role, vote, why, salt))[0], 200)

    def test_bad_token_and_host_only_actions(self):
        self.assertEqual(self.call("host", token="nope")[0], 401)
        self.assertEqual(self.ev("guest", "nav", card=2)[0], 403)
        self.assertEqual(self.ev("host", "nav", card=2)[0], 200)

    def test_deck_is_served_sealed(self):
        status, blob = self.call("guest", path="deck")
        self.assertEqual(status, 200)
        self.assertEqual(blob["alg"], "sha256-ctr+hmac-sha256")
        self.assertNotIn("Алексей", json.dumps(blob, ensure_ascii=False))

    def test_blind_protocol(self):
        self.vote("host", 1, 8, "секрет")
        self.assertEqual(self.ev("host", "reveal", card=1, vote=8, why="секрет", salt="s")[0], 409, "рано вскрывать")
        self.assertEqual(self.ev("host", "commit", card=1, hash="0" * 64)[0], 409, "перекладывать нельзя")
        log = (self.session / "room-log.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("секрет", log)
        self.vote("guest", 1, 3)
        self.assertEqual(self.ev("guest", "reveal", card=1, vote=5, why="пример", salt="s")[0], 409, "подмена оценки")
        self.assertEqual(self.ev("guest", "reveal", card=1, vote=3, why="пример", salt="s")[0], 200)
        self.assertEqual(self.ev("host", "reveal", card=1, vote=8, why="секрет", salt="s")[0], 200)

    def test_hello_half_cannot_be_replaced(self):
        self.assertEqual(self.ev("guest", "hello", name="А", half=self.half["guest"])[0], 200)
        self.assertEqual(self.ev("guest", "hello", name="А", half=self.half["guest"])[0], 200)
        self.assertEqual(self.ev("guest", "hello", name="А", half="AAAA")[0], 409)

    def test_close_requires_both_confirmations_and_writes_results(self):
        self.assertEqual(self.ev("host", "close")[0], 409)
        self.ev("host", "summary_ok")
        self.ev("guest", "summary_ok")
        self.assertEqual(self.ev("host", "close")[0], 409, "без итогов закрыть нельзя")
        self.assertEqual(self.ev("guest", "export", md="x")[0], 403)
        self.ev("host", "export", md="# Итоги", summary={"covered": ["feedback"], "agreements": []})
        self.assertEqual(self.ev("host", "close")[0], 200)
        self.assertEqual((self.session / "results.md").read_text(encoding="utf-8"), "# Итоги")
        self.assertEqual(json.loads((self.session / "results.json").read_text())["period"], "2026-09")
        self.assertEqual(self.ev("guest", "read", card=1)[0], 409, "закрытая встреча только для чтения")
        status, body = self.call("guest")
        self.assertEqual(status, 200)
        self.assertTrue(any(e["type"] == "close" for e in body["events"]))

    def test_events_are_ordered_and_incremental(self):
        self.ev("host", "hello", name="Ирина", half=self.half["host"])
        self.ev("guest", "hello", name="Алексей", half=self.half["guest"])
        _, body = self.call("guest", path="events?since=1&wait=0")
        self.assertEqual([e["seq"] for e in body["events"]], [2])
        self.assertEqual(body["role"], "guest")


if __name__ == "__main__":
    unittest.main()
