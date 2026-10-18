import unittest

from poker.signals import compute, max_in_window, parse_ts, to_markdown
from datetime import timedelta


def issue(key, assignee="me", reporter="me", duedate=None, resolved=None):
    return {"key": key, "assignee": assignee, "reporter": reporter, "duedate": duedate, "resolved": resolved}


def detail(key, comments=(), transitions=(), field_changes=(), worklogs=(), self_set=()):
    return {"key": key, "comments": list(comments), "transitions": list(transitions),
            "field_changes": list(field_changes), "worklogs": list(worklogs), "self_set_fields": list(self_set)}


def ts(day, hm):
    return f"2026-06-{day:02d}T{hm}:00.000+0300"


ACTIVITY = {
    "login": "me",
    "period": ["2026-06-01", "2026-06-30"],
    "issues": [
        issue("P-1", duedate="2026-06-10"),
        issue("P-2"),
        issue("P-3"),
        issue("P-4", assignee="junior", duedate="2026-06-20"),
    ],
    "details": [
        detail("P-1",
               field_changes=[{"created": ts(9, "10:00"), "field": "duedate", "from": "2026-06-05", "to": "2026-06-08"},
                              {"created": ts(9, "11:00"), "field": "duedate", "from": "2026-06-08", "to": "2026-06-10"}],
               comments=[{"created": ts(26, "23:26"), "body": "готово, [~tester] можно тестировать"}]),
        detail("P-2", transitions=[{"created": ts(17, f"10:{m:02d}"), "field": "status", "from": "a", "to": "b"}
                                   for m in (0, 3, 7, 12)]),
        detail("P-3", worklogs=[{"started": ts(21, "23:10"), "hours": 1}, {"started": ts(22, "06:51"), "hours": 1}],
               self_set=["Приёмщик"]),
        detail("P-4"),
    ],
}


class SignalsTest(unittest.TestCase):
    def setUp(self):
        self.res = compute(ACTIVITY)
        self.ids = {s["id"]: s for s in self.res["signals"]}

    def test_expected_signals(self):
        for sid in ("all-on-self", "delegated-silent", "duedate-shifts", "overdue",
                    "tracker-post-factum", "off-hours", "self-set", "handoff"):
            self.assertIn(sid, self.ids)

    def test_evidence_points_to_issues(self):
        self.assertEqual(self.ids["duedate-shifts"]["evidence"], ["P-1"])
        self.assertEqual(self.ids["tracker-post-factum"]["evidence"], ["P-2"])
        self.assertEqual(self.ids["delegated-silent"]["evidence"], ["P-4"])
        self.assertEqual(self.ids["overdue"]["evidence"], ["P-1"])

    def test_off_hours_counts_night_and_early(self):
        self.assertEqual(self.res["facts"]["off_hours_events"], {"P-1": 1, "P-3": 2})

    def test_quiet_month_gives_no_false_alarms(self):
        quiet = {"login": "me", "period": ["2026-06-01", "2026-06-30"],
                 "issues": [issue("Q-1", reporter="boss"), issue("Q-2", assignee="other", reporter="boss")],
                 "details": [detail("Q-1", comments=[{"created": ts(3, "12:00"), "body": "ok"}]), detail("Q-2")]}
        self.assertEqual(compute(quiet)["signals"], [])
        self.assertIn("Сигналов по порогам нет", to_markdown(compute(quiet)))

    def test_helpers(self):
        self.assertIsNone(parse_ts(None))
        t = [parse_ts(ts(1, x)) for x in ("10:00", "10:30", "11:20", "12:00")]
        self.assertEqual(max_in_window(t, timedelta(minutes=60)), 2)


if __name__ == "__main__":
    unittest.main()
