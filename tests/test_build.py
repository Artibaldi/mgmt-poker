import json
import unittest
from pathlib import Path

from poker.build import PLACEHOLDER, render, validate

ROOT = Path(__file__).resolve().parent.parent
DEMO = json.loads((ROOT / "examples" / "demo-cards.json").read_text(encoding="utf-8"))


class ValidateTest(unittest.TestCase):
    def test_demo_is_valid(self):
        self.assertEqual(validate(DEMO), [])

    def test_reports_bad_suit_marker_and_missing_fact(self):
        data = {"meta": {"id": "x", "person": "p", "period": "m"},
                "cards": [{"id": 1, "suit": "X", "competence": "c", "marker": "great", "question": "q"}]}
        errors = "\n".join(validate(data))
        self.assertIn("suit", errors)
        self.assertIn("marker", errors)
        self.assertIn("fact", errors)

    def test_question_card_needs_no_fact(self):
        data = {"meta": {"id": "x", "person": "p", "period": "m"},
                "cards": [{"id": 1, "suit": "♥", "competence": "c", "marker": "question", "question": "q"}]}
        self.assertEqual(validate(data), [])

    def test_duplicate_ids(self):
        card = {"id": 1, "suit": "♠", "competence": "c", "marker": "strength", "fact": "f", "question": "q"}
        data = {"meta": {"id": "x", "person": "p", "period": "m"}, "cards": [card, dict(card)]}
        self.assertTrue(any("дубль" in e for e in validate(data)))


class RenderTest(unittest.TestCase):
    def test_embeds_data_and_title(self):
        html = render(DEMO)
        self.assertNotIn(PLACEHOLDER, html)
        self.assertIn('"demo_2026-06"', html)
        self.assertIn("<title>Покер — Алексей (демо), июнь 2026</title>", html)

    def test_script_tag_in_text_cannot_break_out(self):
        data = json.loads(json.dumps(DEMO))
        data["cards"][0]["fact"] = "</script><script>alert(1)</script>"
        html = render(data)
        self.assertEqual(html.count("</script>"), 1)


if __name__ == "__main__":
    unittest.main()
