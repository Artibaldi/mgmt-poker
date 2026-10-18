import copy
import json
import unittest
from pathlib import Path

from poker.deck import allocate, build_deck, load_model, plural, role_competencies, sanitize

ROOT = Path(__file__).resolve().parent.parent
ACTIVITY = json.loads((ROOT / "examples" / "demo-activity.json").read_text(encoding="utf-8"))
COMMON, ROLES = load_model()
EXPECTED_ROLES = {"system-analyst", "business-analyst", "developer", "qa", "devops", "architect",
                  "project-manager", "team-lead"}


class ModelTest(unittest.TestCase):
    def test_all_roles_present_and_consistent(self):
        self.assertEqual(set(ROLES), EXPECTED_ROLES)
        common_ids = {c["id"] for c in COMMON["competencies"]}
        seen = set(common_ids)
        for rid, role in ROLES.items():
            self.assertEqual(set(role["weights"]), common_ids, rid)
            for c in role["hard"]:
                self.assertEqual(c["suit"], "♠")
                self.assertNotIn(c["id"], seen, f"дубль id {c['id']}")
                seen.add(c["id"])
        for c in COMMON["competencies"] + [h for r in ROLES.values() for h in r["hard"]]:
            self.assertEqual(set(c["anchors"]), {"1", "2", "3", "5", "8"}, c["id"])
            self.assertIn("{name}", c["rate_question"], c["id"])

    def test_managers_get_managerial_cards_others_mostly_not(self):
        for rid, role in ROLES.items():
            managerial = {c["id"] for c, w in role_competencies(COMMON, role) if c["suit"] == "♥"}
            if role["has_reports"]:
                self.assertIn("delegation", managerial, rid)
            else:
                self.assertNotIn("delegated-control", managerial, rid)


class BuildTest(unittest.TestCase):
    def test_every_role_builds_a_valid_deck(self):
        for rid in ROLES:
            deck, errors = sanitize(build_deck(ACTIVITY, rid, "Алексей", "сентябрь 2026"), ACTIVITY)
            self.assertEqual(errors, [], rid)
            self.assertEqual(len(deck["cards"]), 12, rid)
            self.assertGreaterEqual(len({c["suit"] for c in deck["cards"]}), 3, rid)
            self.assertIn("♠", {c["suit"] for c in deck["cards"]}, rid)
            for c in deck["cards"]:
                self.assertNotIn("{name}", c["question"])
                self.assertIn("Алексей", c["question"]) if c["kind"] != "followup" else None

    def test_facts_come_from_signals_with_keys(self):
        deck = build_deck(ACTIVITY, "team-lead", "Алексей", "сентябрь 2026")
        facts = [c for c in deck["cards"] if c["kind"] == "fact"]
        self.assertTrue(facts)
        keys = {r["key"] for r in ACTIVITY["issues"]}
        for c in facts:
            self.assertTrue(set(c["evidence_keys"]) <= keys)
            self.assertIn(c["polarity"], ("strength", "concern"))
        signals_used = [c["fact"] for c in facts]
        self.assertEqual(len(signals_used), len(set(signals_used)), "один сигнал — одна карта")

    def test_followups_from_previous_agreements_go_first(self):
        history = [{"period": "2026-08", "covered": ["delegation"], "agreements": [
            {"competency": "escalation", "title": "Эскалация", "text": "Блокер дольше недели — сразу к руководителю",
             "owner": "Алексей", "due": "сентябрь", "date": "2026-09-01"}]}]
        deck = build_deck(ACTIVITY, "team-lead", "Алексей", "сентябрь 2026", history=history)
        self.assertEqual(deck["cards"][0]["kind"], "followup")
        self.assertIn("Блокер дольше недели", deck["cards"][0]["fact"])
        self.assertEqual(len(deck["cards"]), 12)

    def test_llm_evidence_turns_behavior_into_fact(self):
        ev = [{"competency": "tl-technical-leadership", "fact": "В PAY-101 предложил разбор сценариев ошибок.",
               "keys": ["PAY-101"], "quote": "", "polarity": "strength"}]
        deck = build_deck(ACTIVITY, "team-lead", "Алексей", "сентябрь 2026", llm_evidence=ev)
        card = next(c for c in deck["cards"] if c["competency"] == "tl-technical-leadership")
        self.assertEqual(card["kind"], "fact")
        self.assertIn("PAY-101", card["source"])

    def test_sanitize_demotes_unverifiable_fact(self):
        deck = build_deck(ACTIVITY, "team-lead", "Алексей", "сентябрь 2026")
        bad = copy.deepcopy(deck)
        card = next(c for c in bad["cards"] if c["kind"] == "fact")
        card["evidence_keys"] = ["NOPE-1"]
        bad, errors = sanitize(bad, ACTIVITY)
        self.assertTrue(errors)
        self.assertEqual(next(c for c in bad["cards"] if c["id"] == card["id"])["kind"], "behavior")

    def test_allocate_respects_minimum_and_capacity(self):
        alloc = allocate({"♠": 15, "♦": 10, "♣": 14, "♥": 2}, {"♠": 5, "♦": 5, "♣": 7, "♥": 1}, 12)
        self.assertEqual(sum(alloc.values()), 12)
        self.assertEqual(alloc["♥"], 1)
        self.assertTrue(all(v >= 1 for v in alloc.values()))

    def test_plural(self):
        self.assertEqual([plural(n, "задача", "задачи", "задач") for n in (1, 3, 5, 11, 21)],
                         ["1 задача", "3 задачи", "5 задач", "11 задач", "21 задача"])


if __name__ == "__main__":
    unittest.main()
