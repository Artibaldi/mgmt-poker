#!/usr/bin/env python3
"""Read-only выгрузка активности одного человека в Jira за период → activity.json.

Собирает задачи, где человек assignee/reporter (обновлялись в период), затем по
каждой — комментарии, changelog и worklog с фильтром по автору и датам периода.
Jira Server не умеет JQL-фильтр по автору комментария/перехода, поэтому фильтрация
идёт постфактум по пулу задач. Ничего не пишет в Jira. Паузы против rate-limit.

--roles: дополнительно задачи, где человек в полях-ролях (config/jira.json →
role_fields), автор worklog за период, комментатор (ScriptRunner, если включён).
По каждой задаче — роли человека, эпик, его worklog-часы и self_set_fields:
поля-роли, которые он сам проставил на себя («формально назначен»).

Запуск:
  uv run --with requests python -m poker.fetch \\
    --login IvanovII --from 2026-06-01 --to 2026-06-30 [--roles] [--max-issues 5]
  → sessions/IvanovII_2026-06/activity.json
Принцип подключения и что из этих данных получается — docs/jira-integration.md.
"""
import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
import urllib3
from requests.auth import HTTPBasicAuth

from poker.config import load_env, load_jira_config, session_dir

FIELDS = [
    "summary", "issuetype", "status", "assignee", "reporter",
    "created", "resolutiondate", "duedate", "priority", "labels",
    "components", "updated", "resolution",
]


class Jira:
    def __init__(self, env, cfg):
        self.base = env["JIRA_URL"].rstrip("/")
        self.auth = HTTPBasicAuth(env["JIRA_USERNAME"], env["JIRA_PASSWORD"])
        self.pause_s = float(cfg.get("pause_seconds", 2.0))
        self.s = requests.Session()
        self.s.verify = bool(cfg.get("verify_ssl", True))
        if not self.s.verify:
            urllib3.disable_warnings()
        self.last = 0.0

    def _pause(self):
        dt = time.time() - self.last
        if dt < self.pause_s:
            time.sleep(self.pause_s - dt)
        self.last = time.time()

    def get(self, path, params=None, tries=5, soft400=False):
        for attempt in range(tries):
            self._pause()
            r = self.s.get(f"{self.base}{path}", params=params, auth=self.auth, timeout=60)
            if r.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"  429, backoff {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            if r.status_code == 400 and soft400:
                print(f"  400 (skip): {r.text[:200]}", file=sys.stderr)
                return None
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"failed after {tries}: {path}")

    def search(self, jql, fields, soft400=False):
        out, start = [], 0
        while True:
            data = self.get("/rest/api/2/search", params={
                "jql": jql, "startAt": start, "maxResults": 100, "fields": ",".join(fields),
            }, soft400=soft400)
            if data is None:
                return None
            out.extend(data.get("issues", []))
            total = data.get("total", 0)
            start += len(data.get("issues", []))
            print(f"  jql ok: {len(out)}/{total}", file=sys.stderr)
            if start >= total or not data.get("issues"):
                return out


def _name(v):
    return v.get("name") if isinstance(v, dict) else v


def slim(issues, cfg):
    rows = []
    for it in issues:
        f = it.get("fields", {})
        rows.append({
            "key": it["key"],
            "summary": f.get("summary"),
            "type": _name(f.get("issuetype") or {}),
            "status": _name(f.get("status") or {}),
            "assignee": _name(f.get("assignee") or {}),
            "reporter": _name(f.get("reporter") or {}),
            "created": f.get("created"),
            "resolved": f.get("resolutiondate"),
            "duedate": f.get("duedate"),
            "priority": _name(f.get("priority") or {}),
            "resolution": _name(f.get("resolution") or {}),
            "components": [c.get("name") for c in (f.get("components") or [])],
            "epic": f.get(cfg["epic_field"]) if cfg.get("epic_field") else None,
            **{role: _name(f.get(cf)) for role, cf in cfg.get("role_fields", {}).items()},
        })
    return rows


def in_period(ts, start, end_excl):
    return bool(ts) and start <= ts[:10] < end_excl


def fetch_person_details(jira, key, login, start, end_excl):
    """Комментарии, changelog и worklog задачи, отфильтрованные по автору и периоду."""
    data = jira.get(f"/rest/api/2/issue/{key}", params={
        "expand": "changelog", "fields": "comment,summary,status,worklog",
    })
    f = data.get("fields", {})
    histories = (data.get("changelog") or {}).get("histories", [])
    wl = f.get("worklog") or {}
    wl_items = wl.get("worklogs", [])
    if wl.get("total", 0) > len(wl_items):
        wl_items = (jira.get(f"/rest/api/2/issue/{key}/worklog") or {}).get("worklogs", [])
    worklogs = [
        {"started": w.get("started"), "hours": round(w.get("timeSpentSeconds", 0) / 3600, 2),
         "comment": w.get("comment")}
        for w in wl_items
        if (w.get("author") or {}).get("name") == login and in_period(w.get("started"), start, end_excl)
    ]
    self_set_fields = sorted({
        item.get("field")
        for h in histories if (h.get("author") or {}).get("name") == login
        for item in h.get("items", [])
        if item.get("field") not in ("status", "assignee") and login in (item.get("to") or "")
    })
    comments = [
        {"created": c.get("created"), "body": c.get("body")}
        for c in (f.get("comment") or {}).get("comments", [])
        if (c.get("author") or {}).get("name") == login and in_period(c.get("created"), start, end_excl)
    ]
    transitions, field_changes = [], []
    for h in histories:
        if (h.get("author") or {}).get("name") != login or not in_period(h.get("created"), start, end_excl):
            continue
        for item in h.get("items", []):
            row = {"created": h.get("created"), "field": item.get("field"),
                   "from": item.get("fromString"), "to": item.get("toString")}
            (transitions if item.get("field") == "status" else field_changes).append(row)
    return {
        "key": key,
        "summary": f.get("summary"),
        "status": _name(f.get("status") or {}),
        "comments": comments,
        "transitions": transitions,
        "field_changes": field_changes,
        "worklogs": worklogs,
        "worklog_hours": round(sum(w["hours"] for w in worklogs), 2),
        "self_set_fields": self_set_fields,
    }


def collect(env, cfg, login, date_from, date_to, roles=False, max_issues=None):
    """Выгрузка активности человека за период → dict (формат activity.json)."""
    missing = [k for k in ("JIRA_URL", "JIRA_PROJECT_KEY", "JIRA_USERNAME", "JIRA_PASSWORD") if not env.get(k)]
    if missing:
        raise SystemExit(f"нет {', '.join(missing)}: заполните .env (см. .env.example) или передайте --env")
    jira, proj = Jira(env, cfg), env["JIRA_PROJECT_KEY"]
    start = date_from
    end_excl = (date.fromisoformat(date_to) + timedelta(days=1)).isoformat()
    per = f'updated >= "{start}" AND updated < "{end_excl}"'
    fields = FIELDS + [f for f in [cfg.get("epic_field"), *cfg.get("role_fields", {}).values()] if f]

    jql = f"project = {proj} AND (assignee = {login} OR reporter = {login}) AND {per} ORDER BY updated"
    print(f"== issues: {jql} ==", file=sys.stderr)
    issues = slim(jira.search(jql, fields), cfg)
    buckets = {"assignee_or_reporter": [r["key"] for r in issues]}
    if roles:
        extra = {role: f"project = {proj} AND cf[{cf.split('_')[1]}] = {login} AND {per}"
                 for role, cf in cfg.get("role_fields", {}).items()}
        extra["worklog"] = (f'project = {proj} AND worklogAuthor = {login} '
                            f'AND worklogDate >= "{start}" AND worklogDate < "{end_excl}"')
        if cfg.get("scriptrunner_commented"):
            extra["commenter"] = f'project = {proj} AND issueFunction in commented("by {login}") AND {per}'
        seen = {r["key"] for r in issues}
        for name, q in extra.items():
            print(f"== {name}: {q} ==", file=sys.stderr)
            found = jira.search(q, fields, soft400=True)
            if found is None:
                buckets[name] = None
                continue
            rows = slim(found, cfg)
            buckets[name] = [r["key"] for r in rows]
            for r in rows:
                if r["key"] not in seen:
                    seen.add(r["key"])
                    issues.append(r)
    for r in issues:
        r["roles"] = [b for b, keys in buckets.items() if keys and r["key"] in keys]
    if max_issues:
        issues = issues[:max_issues]

    details = []
    for i, row in enumerate(issues, 1):
        print(f"== details {i}/{len(issues)}: {row['key']} ==", file=sys.stderr)
        details.append(fetch_person_details(jira, row["key"], login, start, end_excl))

    return {
        "login": login,
        "period": [date_from, date_to],
        "project": proj,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "buckets": {k: (len(v) if v is not None else None) for k, v in buckets.items()},
        "issues": issues,
        "details": details,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--login", required=True, help="jira-login")
    ap.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD (включительно)")
    ap.add_argument("--max-issues", type=int, help="ограничить число задач (проверочный прогон)")
    ap.add_argument("--roles", action="store_true", help="добавить задачи по полям-ролям/worklog/комментариям")
    ap.add_argument("--env", help="путь к .env с JIRA_* (иначе $POKER_ENV или ./.env)")
    ap.add_argument("--out", help="каталог вывода (по умолчанию sessions/<login>_<YYYY-MM>)")
    args = ap.parse_args()

    result = collect(load_env(args.env), load_jira_config(), args.login, args.date_from, args.date_to,
                     roles=args.roles, max_issues=args.max_issues)
    details = result["details"]
    out_dir = Path(args.out) if args.out else session_dir(args.login, args.date_from[:7])
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "activity.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "issues": len(result["issues"]),
        "comments": sum(len(d["comments"]) for d in details),
        "transitions": sum(len(d["transitions"]) for d in details),
        "field_changes": sum(len(d["field_changes"]) for d in details),
        "worklog_hours": round(sum(d["worklog_hours"] for d in details), 2),
        "buckets": result["buckets"],
        "path": str(path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
