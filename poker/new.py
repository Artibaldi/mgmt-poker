#!/usr/bin/env python3
"""Создать встречу: руководитель задаёт только человека и период — остальное автоматически.

  python -m poker.new --login jdoe --from 2026-09-01 --to 2026-09-30 [--llm claude]

Шаги: выгрузка Jira → сигналы → (необязательно) доказательства от Claude → колода по модели
компетенций роли → автопроверка → печать → комната на ретрансляторе. Руководитель видит
только отчёт без содержания карт и две ссылки: свою и для сотрудника.

Без Jira (демо и тесты): --activity examples/demo-activity.json.
"""
import argparse
import hashlib
import json
import os
import secrets
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from poker.config import ROOT, SESSIONS, load_env, load_jira_config
from poker.deck import build_deck, load_history, load_model, report, role_competencies, sanitize
from poker.seal import b64u, new_halves, seal

MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь",
          "октябрь", "ноябрь", "декабрь"]


def load_json(name):
    for n in (f"{name}.json", f"{name}.example.json"):
        p = ROOT / "config" / n
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    return {}


def period_label(date_from, date_to):
    a, b = date_from[:7], date_to[:7]
    if a == b and date_from.endswith("-01"):
        return f"{MONTHS[int(a[5:7]) - 1]} {a[:4]}"
    return f"{date_from} — {date_to}"


def links(base, room_id, tokens, halves, names):
    out = {}
    for role in ("host", "guest"):
        frag = f"role={role}&t={tokens[role]}&k={halves[role]}&n={quote(names[role])}"
        out[role] = f"{base.rstrip('/')}/r/{room_id}#{frag}"
    return out


def create(activity, *, login, role, name, manager, date_from, date_to, relay_url, ttl_days=14,
           llm=None, model=None, n_cards=12, sessions=SESSIONS, force=False, workday=(7, 22)):
    session = Path(sessions) / f"{login}_{date_from[:7]}"
    if (session / "room.json").exists() and not force:
        raise SystemExit(f"встреча уже создана: {session}/room.json (пересоздать — --force)")
    session.mkdir(parents=True, exist_ok=True)
    for d in (Path(sessions), session):          # данные о людях — только владельцу
        d.chmod(0o700)

    common, roles = load_model()
    llm_evidence, llm_note = [], "LLM не использовалась"
    if llm == "claude":
        from poker.llm import find_evidence
        llm_evidence, llm_note = find_evidence(activity, [c for c, _ in role_competencies(common, roles[role])], model)

    deck = build_deck(activity, role, name, period_label(date_from, date_to), common=common, roles=roles,
                      history=load_history(login, sessions, before=date_from[:7]), llm_evidence=llm_evidence,
                      n_cards=n_cards, workday=workday, manager_name=manager)
    deck, errors = sanitize(deck, activity)

    key, k1, k2 = new_halves()
    room_id = secrets.token_urlsafe(9)
    tokens = {"host": secrets.token_urlsafe(18), "guest": secrets.token_urlsafe(18)}
    now = datetime.now(timezone.utc)
    (session / "deck.sealed.json").write_text(json.dumps(seal(deck, key)), encoding="utf-8")
    (session / "activity.sealed.json").write_text(json.dumps(seal(activity, key)), encoding="utf-8")
    (session / "room.json").write_text(json.dumps({
        "room_id": room_id, "login": login, "period": date_from[:7],
        "tokens": {r: hashlib.sha256(t.encode()).hexdigest() for r, t in tokens.items()},
        "created": now.isoformat(timespec="seconds"),
        "expires": (now + timedelta(days=ttl_days)).isoformat(timespec="seconds"),
    }, indent=2), encoding="utf-8")
    (session / "room-log.jsonl").write_text("", encoding="utf-8")
    url = links(relay_url, room_id, tokens, {"host": b64u(k1), "guest": b64u(k2)}, {"host": manager, "guest": name})
    (session / "links.txt").write_text(
        "Ссылки встречи. Ссылку сотрудника отправьте ему вместе с приглашением на ВКС.\n"
        "Половина ключа колоды — в каждой ссылке: открыть колоду по одной ссылке нельзя.\n\n"
        f"Руководитель: {url['host']}\nСотрудник:    {url['guest']}\n", encoding="utf-8")
    for f in session.iterdir():
        f.chmod(0o600)
    return session, deck, errors, llm_note, url


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--login", required=True)
    ap.add_argument("--from", dest="date_from", required=True, help="YYYY-MM-DD")
    ap.add_argument("--to", dest="date_to", required=True, help="YYYY-MM-DD (включительно)")
    ap.add_argument("--role", help="id роли из competencies/roles (иначе из config/team.json)")
    ap.add_argument("--name", help="как обращаться к сотруднику (иначе из config/team.json)")
    ap.add_argument("--llm", choices=["none", "claude"], default="none", help="искать доказательства в комментариях через Claude")
    ap.add_argument("--model", help="модель для --llm claude (по умолчанию — модель Claude Code)")
    ap.add_argument("--cards", type=int, default=12)
    ap.add_argument("--activity", help="готовый activity.json вместо выгрузки из Jira")
    ap.add_argument("--env", help="путь к .env с JIRA_*")
    ap.add_argument("--relay", help="адрес комнаты для ссылок (иначе config/relay.json → public_url)")
    ap.add_argument("--force", action="store_true", help="пересоздать встречу (старые ссылки перестанут работать)")
    args = ap.parse_args()

    team, relay = load_json("team"), load_json("relay")
    person = team.get("people", {}).get(args.login, {})
    role, name = args.role or person.get("role"), args.name or person.get("name") or args.login
    if not role:
        sys.exit(f"роль для {args.login} не задана: --role или config/team.json (см. config/team.example.json)")
    cfg = load_jira_config()
    if args.activity:
        activity = json.loads(Path(args.activity).read_text(encoding="utf-8"))
        activity["login"], activity["period"] = args.login, [args.date_from, args.date_to]
    else:
        from poker.fetch import collect
        activity = collect(load_env(args.env), cfg, args.login, args.date_from, args.date_to, roles=True)
    wd = cfg.get("workday", {})
    session, deck, errors, llm_note, url = create(
        activity, login=args.login, role=role, name=name, manager=team.get("manager", {}).get("name", "Руководитель"),
        date_from=args.date_from, date_to=args.date_to,
        relay_url=args.relay or relay.get("public_url", "http://localhost:8765"),
        ttl_days=relay.get("room_ttl_days", 14), llm=None if args.llm == "none" else args.llm, model=args.model,
        n_cards=args.cards, force=args.force, workday=(wd.get("start_hour", 7), wd.get("end_hour", 22)))
    print(report(deck, errors))
    print(llm_note)
    print(f"\nВстреча: {session}")
    print(f"Ваша ссылка:          {url['host']}")
    print(f"Ссылка для сотрудника: {url['guest']}")
    print("\nДальше: запустите комнату — python -m poker.relay (docs/deploy-local.md) — и отправьте ссылку сотруднику.")


if __name__ == "__main__":
    main()
