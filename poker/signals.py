#!/usr/bin/env python3
"""activity.json → signals.md: автоматические сигналы из Jira для подготовки досье.

Сигнал — это гипотеза с доказательствами (ключи задач), а не оценка. Каждый
сигнал привязан к компетенции и масти, чтобы из него можно было собрать карту.
Таблица «сигнал → компетенция» и пороги — docs/jira-integration.md.

Запуск: python3 -m poker.signals sessions/IvanovII_2026-06/activity.json
  → рядом signals.md и signals.json. Только stdlib, работает на python3.9.
"""
import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SUITS = {  # как в competencies/common.json
    "♠": "Профессиональные навыки (хард)",
    "♦": "Софт-навыки",
    "♣": "Личные качества и самоорганизация",
    "♥": "Управленческие навыки",
}
DUEDATE_FIELDS = {"duedate", "Due Date", "Срок исполнения"}
BATCH_WINDOW = timedelta(minutes=60)
BATCH_MIN_TRANSITIONS = 4
DUEDATE_MIN_SHIFTS = 2


def parse_ts(ts):
    """Время Jira «2026-06-26T23:26:00.000+0300» → naive datetime в часах сервера."""
    return datetime.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S") if ts and len(ts) >= 19 else None


def max_in_window(times, window):
    times, best, lo = sorted(times), 0, 0
    for hi, t in enumerate(times):
        while t - times[lo] > window:
            lo += 1
        best = max(best, hi - lo + 1)
    return best


def compute(activity, workday=(7, 22)):
    login = activity["login"]
    end_excl = (datetime.fromisoformat(activity["period"][1]) + timedelta(days=1)).date().isoformat()
    issues = {r["key"]: r for r in activity.get("issues", [])}
    details = {d["key"]: d for d in activity.get("details", [])}
    signals, facts = [], {}

    def add(sid, suit, competence, title, keys, hint):
        signals.append({"id": sid, "suit": suit, "competence": competence, "title": title,
                        "evidence": sorted(set(keys)), "hint": hint})

    # Объём и делегирование
    own = [k for k, r in issues.items() if r.get("assignee") == login]
    delegated = {k: r["assignee"] for k, r in issues.items()
                 if r.get("reporter") == login and r.get("assignee") not in (None, login)}
    facts["volume"] = {"issues": len(issues), "as_assignee": len(own),
                       "delegated": len(delegated), "delegated_to": dict(Counter(delegated.values()))}
    if issues and len(own) / len(issues) >= 0.6 and len(set(delegated.values())) <= 1:
        add("all-on-self", "♥", "Делегирование",
            f"Исполнитель по {len(own)} из {len(issues)} задач, делегировано людям: {len(set(delegated.values()))}",
            own, "Осознанный выбор (некому отдать) или трудно отпускать и просить ресурс?")

    # Контроль делегированного: задачи на других, без его активности в период
    silent = [k for k in delegated
              if not (details.get(k, {}).get("comments") or details.get(k, {}).get("transitions"))
              and not issues[k].get("resolved") and (issues[k].get("duedate") or "9999") < end_excl]
    if silent:
        add("delegated-silent", "♥", "Контроль делегированного",
            f"Делегированные задачи просрочены, комментариев и напоминаний от сотрудника нет: {len(silent)}", silent,
            "Есть ли система контроля после постановки задачи?")

    # Сроки: повторные переносы duedate самим человеком
    shifts = {k: [c for c in d.get("field_changes", []) if c.get("field") in DUEDATE_FIELDS]
              for k, d in details.items()}
    multi = {k: v for k, v in shifts.items() if len(v) >= DUEDATE_MIN_SHIFTS}
    facts["duedate_shifts"] = {k: [(c["from"], c["to"]) for c in v] for k, v in shifts.items() if v}
    if multi:
        add("duedate-shifts", "♣", "Эскалация и блокеры",
            f"Сотрудник переносил срок ≥{DUEDATE_MIN_SHIFTS} раз, задач: {len(multi)}", list(multi),
            "Перенос срока вместо эскалации? Посмотреть комментарии к переносам: что блокировало.")

    # Просрочка на конец периода по своим задачам
    overdue = [k for k in own if (issues[k].get("duedate") or "9999") < end_excl
               and (not issues[k].get("resolved") or issues[k]["resolved"][:10] > issues[k]["duedate"])]
    facts["overdue_own"] = overdue
    if overdue:
        add("overdue", "♣", "Контроль сроков", f"Свои задачи просрочены на конец периода: {len(overdue)}",
            overdue, "Честный статус или тихая просрочка? Есть ли обзор своих хвостов?")

    # Трекер постфактум: пачка переходов за короткое окно
    batch = {}
    for k, d in details.items():
        times = [t for t in (parse_ts(x.get("created")) for x in d.get("transitions", [])) if t]
        n = max_in_window(times, BATCH_WINDOW)
        if n >= BATCH_MIN_TRANSITIONS:
            batch[k] = n
    facts["batch_workflow"] = batch
    if batch:
        add("tracker-post-factum", "♣", "Трекер как инструмент",
            f"≥{BATCH_MIN_TRANSITIONS} переходов статуса за час, задач: {len(batch)}", list(batch),
            "Jira — инструмент управления по ходу или слой отчётности после факта?")

    # Нерабочее время: комментарии, переходы, правки, ворклоги
    off = defaultdict(int)
    for k, d in details.items():
        events = ([c.get("created") for c in d.get("comments", [])]
                  + [x.get("created") for x in d.get("transitions", []) + d.get("field_changes", [])]
                  + [w.get("started") for w in d.get("worklogs", [])])
        for t in filter(None, map(parse_ts, events)):
            if t.weekday() >= 5 or not (workday[0] <= t.hour < workday[1]):
                off[k] += 1
    facts["off_hours_events"] = dict(off)
    if sum(off.values()) >= 3:
        add("off-hours", "♣", "Нагрузка и самоорганизация",
            f"Действий в нерабочее время и выходные: {sum(off.values())}, задач: {len(off)}", list(off),
            "Темп устойчивый или перегруз компенсируется личным временем? Что сознательно не берётся в работу?")

    # Формальные назначения на себя
    self_set = {k: d["self_set_fields"] for k, d in details.items() if d.get("self_set_fields")}
    facts["self_set_fields"] = self_set
    if self_set:
        add("self-set", "♣", "Ответственность и владение",
            f"Сотрудник проставил себя в поля-роли, задач: {len(self_set)}", list(self_set),
            "Реальное решение/ответственность или формальное назначение скриптом?")

    # Коммуникация: объём комментариев и адресность
    comments = [(k, c) for k, d in details.items() for c in d.get("comments", [])]
    mentions = sum((c.get("body") or "").count("[~") for _, c in comments)
    facts["communication"] = {"comments": len(comments), "issues_with_comments": len({k for k, _ in comments}),
                              "mentions": mentions,
                              "avg_len": round(sum(len(c.get("body") or "") for _, c in comments)
                                               / len(comments)) if comments else 0}
    if comments and mentions:
        add("handoff", "♦", "Цифровой след и хендофф",
            f"{len(comments)} комментариев, {mentions} адресных @-упоминаний", [k for k, _ in comments],
            "Норма коммуникации или разовые образцовые задачи? Найти лучший и худший комментарий.")
    elif issues and not comments:
        add("silent-tracker", "♦", "Цифровой след и хендофф",
            "Ни одного комментария за период", list(issues),
            "Где живёт коммуникация по задачам — в чатах? Видна ли она команде?")

    return {"login": login, "period": activity["period"], "facts": facts, "signals": signals}


def to_markdown(res):
    v = res["facts"]["volume"]
    lines = [
        f"# Сигналы Jira — {res['login']}, {res['period'][0]} … {res['period'][1]}",
        "",
        "Автоматические гипотезы для досье. Не оценка: каждую проверить по задачам и дейли.",
        "",
        f"**Объём:** {v['issues']} задач, исполнитель в {v['as_assignee']}, "
        f"делегировано {v['delegated']} ({', '.join(f'{k}: {n}' for k, n in v['delegated_to'].items()) or '—'}). "
        f"**Комментарии:** {res['facts']['communication']['comments']}.",
        "",
        "| Масть | Компетенция | Сигнал | Задачи | Что проверить |",
        "|---|---|---|---|---|",
    ]
    for s in res["signals"]:
        ev = ", ".join(s["evidence"][:8]) + (" …" if len(s["evidence"]) > 8 else "")
        lines.append(f"| {s['suit']} | {s['competence']} | {s['title']} | {ev} | {s['hint']} |")
    if not res["signals"]:
        lines.append("| — | — | Сигналов по порогам нет | — | Опираться на дейли и встречи |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("activity", help="путь к activity.json")
    args = ap.parse_args()
    src = Path(args.activity)
    cfg_path = Path(__file__).resolve().parent.parent / "config"
    cfg = next((json.loads((cfg_path / n).read_text(encoding="utf-8"))
                for n in ("jira.json", "jira.example.json") if (cfg_path / n).is_file()), {})
    wd = cfg.get("workday", {})
    res = compute(json.loads(src.read_text(encoding="utf-8")),
                  (wd.get("start_hour", 7), wd.get("end_hour", 22)))
    (src.parent / "signals.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    (src.parent / "signals.md").write_text(to_markdown(res), encoding="utf-8")
    print(f"{len(res['signals'])} сигналов → {src.parent / 'signals.md'}")


if __name__ == "__main__":
    main()
