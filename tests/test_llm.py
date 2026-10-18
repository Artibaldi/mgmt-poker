import json
import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

from poker.deck import load_model, role_competencies
from poker.llm import build_prompt, find_evidence, parse_json_array, validate

ROOT = Path(__file__).resolve().parent.parent
ACTIVITY = json.loads((ROOT / "examples" / "demo-activity.json").read_text(encoding="utf-8"))
COMMON, ROLES = load_model()
COMPS = [c for c, _ in role_competencies(COMMON, ROLES["team-lead"])]
IDS = {c["id"] for c in COMPS}

GOOD = {"competency": "tl-technical-leadership", "fact": "В PAY-114 подготовил пути проверки для тестирования.",
        "keys": ["PAY-114"], "quote": "пути проверки и тестовые данные", "polarity": "strength"}


class LlmTest(unittest.TestCase):
    def test_parse_tolerates_fences_and_noise(self):
        self.assertEqual(parse_json_array('Вот:\n```json\n[{"a": 1}]\n```'), [{"a": 1}])
        self.assertEqual(parse_json_array('[{"a": 2}] спасибо'), [{"a": 2}])
        self.assertEqual(parse_json_array("нет данных"), [])

    def test_validate_keeps_only_verifiable_episodes(self):
        bad_key = dict(GOOD, competency="feedback", keys=["NOPE-1"])
        bad_quote = dict(GOOD, competency="collaboration", quote="этого текста нет в комментариях")
        bad_comp = dict(GOOD, competency="unknown")
        dup = dict(GOOD)
        ok, rejected = validate([GOOD, bad_key, bad_quote, bad_comp, dup, "мусор"], ACTIVITY, IDS)
        self.assertEqual([e["competency"] for e in ok], ["tl-technical-leadership"])
        self.assertEqual(rejected, 5)

    def test_prompt_hides_mentions_and_lists_competencies(self):
        prompt = build_prompt(ACTIVITY, COMPS)
        self.assertIn("tl-technical-leadership", prompt)
        self.assertNotIn("[~tester]", prompt)
        self.assertIn("@коллега", prompt)

    def test_find_evidence_with_stub_command(self):
        with tempfile.TemporaryDirectory() as d:
            stub = Path(d) / "stub.py"
            stub.write_text("import sys,json;sys.stdin.read();print('```json\\n'+json.dumps(%s)+'\\n```')"
                            % json.dumps([GOOD], ensure_ascii=False), encoding="utf-8")
            os.environ["POKER_LLM_CMD"] = f"{shlex.quote(sys.executable)} {shlex.quote(str(stub))}"
            try:
                ok, note = find_evidence(ACTIVITY, COMPS)
            finally:
                del os.environ["POKER_LLM_CMD"]
        self.assertEqual(len(ok), 1)
        self.assertIn("принято 1", note)

    def test_missing_cli_does_not_break_generation(self):
        os.environ["POKER_LLM_CMD"] = "/nonexistent/claude"
        try:
            ok, note = find_evidence(ACTIVITY, COMPS)
        finally:
            del os.environ["POKER_LLM_CMD"]
        self.assertEqual(ok, [])
        self.assertIn("недоступна", note)


if __name__ == "__main__":
    unittest.main()
