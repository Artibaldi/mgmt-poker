"""Автоматическая сборка колоды по модели компетенций — без участия человека.

Вход: activity.json (выгрузка Jira), роль из competencies/roles, история прошлых встреч,
необязательные доказательства от LLM (poker/llm.py). Выход: колода (dict), которая сразу
уходит под печать (poker/seal.py) — её не видит никто до встречи.

Правила подбора — docs/competencies.md:
- компетенции роли: хард (♠) из профиля + общие (♦ ♣ ♥) с весом > 0;
- места в колоде делятся между мастями пропорционально весам, минимум одна карта на масть;
- внутри масти выше те, у кого есть доказательства за период, и те, что давно не обсуждали;
- до двух карт «проверка договорённости» из прошлой встречи — первыми.
"""
import hashlib
import json
from pathlib import Path

from poker.config import ROOT, SESSIONS
from poker.signals import compute as compute_signals

SUIT_ORDER = ["♠", "♦", "♣", "♥"]
POSITIVE_SIGNALS = {"handoff"}
KIND_TITLE = {"fact": "Факт из Jira", "behavior": "Поведенческий вопрос", "followup": "Проверка договорённости"}


def load_model(root=ROOT):
    base = Path(root) / "competencies"
    common = json.loads((base / "common.json").read_text(encoding="utf-8"))
    roles = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((base / "roles").glob("*.json"))}
    return common, roles


def role_competencies(common, role):
    """[(competency, weight)] для роли: хард всегда с весом 3, общие — по профилю, 0 = не берём."""
    out = [(c, 3) for c in role["hard"]]
    for c in common["competencies"]:
        w = role["weights"].get(c["id"], 0)
        if w > 0:
            out.append((c, w))
    return out


def load_history(login, sessions=SESSIONS, before=None):
    """Итоги прошлых встреч человека (results.json), новые — первыми."""
    out = []
    for p in sorted(Path(sessions).glob(f"{login}_*/results.json"), reverse=True):
        r = json.loads(p.read_text(encoding="utf-8"))
        if before and r.get("period", "") >= before:
            continue
        out.append(r)
    return out


def _d(iso):
    return f"{iso[8:10]}.{iso[5:7]}" if iso and len(iso) >= 10 else (iso or "?")


def plural(n, one, few, many):
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def _keys(keys, n=4):
    keys = sorted(keys)
    return ", ".join(keys[:n]) + (f" и ещё {len(keys) - n}" if len(keys) > n else "")


def signal_fact(s, facts):
    """Человеческая формулировка факта по сигналу — с датами и ключами, без оценок."""
    sid, ev = s["id"], s["evidence"]
    v, com = facts.get("volume", {}), facts.get("communication", {})
    if sid == "all-on-self":
        return (f"За период {plural(v.get('issues'), 'задача', 'задачи', 'задач')}: исполнитель — "
                f"в {v.get('as_assignee')}, на коллег поставлено {v.get('delegated')}.")
    if sid == "delegated-silent":
        return f"Поставленные на коллег задачи {_keys(ev)} просрочены; комментариев и напоминаний в них за период нет."
    if sid == "duedate-shifts":
        parts = []
        for k, shifts in sorted(facts.get("duedate_shifts", {}).items()):
            if k in ev and shifts:
                parts.append(f"{k}: " + " → ".join([_d(shifts[0][0])] + [_d(t) for _, t in shifts]))
        return "Срок переносился несколько раз: " + "; ".join(parts) + "."
    if sid == "overdue":
        return f"На конец периода просрочены свои задачи: {_keys(ev)}."
    if sid == "tracker-post-factum":
        b = facts.get("batch_workflow", {})
        return "Задачи прошли workflow пачкой — несколько переходов статуса в течение часа: " + \
            ", ".join(f"{k} ({plural(b[k], 'переход', 'перехода', 'переходов')})" for k in sorted(b)[:4]) + "."
    if sid == "off-hours":
        n = sum(facts.get("off_hours_events", {}).values())
        return f"{plural(n, 'действие', 'действия', 'действий')} в задачах ({_keys(ev)}) — поздний вечер, ночь или выходные."
    if sid == "self-set":
        return f"В задачах {_keys(ev)} сотрудник сам указан в полях-ролях (приёмщик, постановщик, ответственный)."
    if sid == "handoff":
        return (f"За период {plural(com.get('comments'), 'комментарий', 'комментария', 'комментариев')} "
                f"в задачах, адресных @-упоминаний — {com.get('mentions')}; примеры: {_keys(ev, 3)}.")
    if sid == "silent-tracker":
        return "За период в задачах нет ни одного комментария — обсуждение, если было, шло вне трекера."
    return s["title"] + "."


def evidence_from_signals(sig, comps):
    """{competency_id: [evidence]} по результату signals.compute; сигнал достаётся одной компетенции."""
    by_signal = {}
    for c, _ in comps:
        for s in c.get("signals", []):
            by_signal.setdefault(s, []).append(c["id"])
    ev = {}
    for s in sig["signals"]:
        for cid in by_signal.get(s["id"], []):
            ev.setdefault(cid, []).append({
                "source": "signal", "signal": s["id"], "fact": signal_fact(s, sig["facts"]), "keys": s["evidence"],
                "hint": s["hint"], "polarity": "strength" if s["id"] in POSITIVE_SIGNALS else "concern",
            })
    return ev


def _rot(seed, cid):
    return int(hashlib.sha256(f"{seed}:{cid}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def allocate(weights_by_suit, counts_by_suit, slots):
    """Места по мастям: минимум 1, остальное — пропорционально весам (метод наибольшего остатка)."""
    suits = [s for s in SUIT_ORDER if counts_by_suit.get(s)]
    alloc = {s: 1 for s in suits}
    left = slots - len(suits)
    total = sum(weights_by_suit[s] for s in suits) or 1
    if left > 0:
        raw = {s: left * weights_by_suit[s] / total for s in suits}
        for s in suits:
            alloc[s] += int(raw[s])
        rest = slots - sum(alloc.values())
        for s in sorted(suits, key=lambda s: raw[s] - int(raw[s]), reverse=True)[:max(rest, 0)]:
            alloc[s] += 1
    # не больше, чем компетенций в масти; излишек — в масти, где есть запас
    spare = 0
    for s in suits:
        if alloc[s] > counts_by_suit[s]:
            spare += alloc[s] - counts_by_suit[s]
            alloc[s] = counts_by_suit[s]
    for s in sorted(suits, key=lambda s: weights_by_suit[s], reverse=True):
        while spare and alloc[s] < counts_by_suit[s]:
            alloc[s] += 1
            spare -= 1
    return alloc


def build_deck(activity, role_id, name, period_label, *, common=None, roles=None, history=(),
               llm_evidence=(), n_cards=12, workday=(7, 22), manager_name="Руководитель"):
    if common is None or roles is None:
        common, roles = load_model()
    if role_id not in roles:
        raise ValueError(f"нет профиля роли {role_id!r}; есть: {', '.join(sorted(roles))}")
    role = roles[role_id]
    comps = role_competencies(common, role)
    by_id = {c["id"]: (c, w) for c, w in comps}
    sig = compute_signals(activity, workday)
    evidence = evidence_from_signals(sig, comps)
    for e in llm_evidence:
        evidence.setdefault(e["competency"], []).append(dict(e, source="llm"))

    seed = f"{activity['login']}:{activity['period'][0]}"
    recent = {cid for r in list(history)[:2] for cid in r.get("covered", [])}

    followups = []
    if history:
        for a in history[0].get("agreements", [])[:2]:
            if a.get("competency") in by_id:
                followups.append(a)

    slots = max(n_cards - len(followups), 1)
    weights = {s: sum(w for c, w in comps if c["suit"] == s) for s in SUIT_ORDER}
    counts = {s: sum(1 for c, _ in comps if c["suit"] == s) for s in SUIT_ORDER}
    alloc = allocate(weights, counts, slots)

    def score(item):
        c, w = item
        return (w * 2 + (3 if c["id"] in evidence else 0) + (0 if c["id"] in recent else 2)
                + _rot(seed, c["id"]))

    chosen = []
    for s in SUIT_ORDER:
        pool = sorted((x for x in comps if x[0]["suit"] == s), key=score, reverse=True)
        chosen += [c for c, _ in pool[: alloc.get(s, 0)]]

    used_signals, cards = set(), []

    def base(c, kind):
        return {
            "id": len(cards) + 1, "kind": kind, "kind_title": KIND_TITLE[kind], "suit": c["suit"],
            "competency": c["id"], "title": c["title"], "description": c["description"],
            "question": c["rate_question"].replace("{name}", name), "anchors": c["anchors"],
            "discussion": c.get("discussion_prompts", []),
        }

    for a in followups:
        c = by_id[a["competency"]][0]
        card = base(c, "followup")
        card.update({
            "fact": f"На прошлой встрече ({a.get('date', '—')}) договорились: «{a['text']}»"
                    + (f" — {a['owner']}" if a.get("owner") else "") + (f", до {a['due']}" if a.get("due") else "") + ".",
            "question": "Насколько договорённость выполнена и что изменилось на практике?",
            "source": "итоги прошлой встречи",
            "data_view": "Это проверка договорённости: данные Jira здесь вторичны, важны примеры из периода.",
        })
        cards.append(card)

    for c in sorted(chosen, key=lambda c: (SUIT_ORDER.index(c["suit"]), c["id"] not in evidence)):
        ev = [e for e in evidence.get(c["id"], []) if e.get("signal") not in used_signals]
        if ev:
            used_signals.update(e["signal"] for e in ev if e.get("signal"))
            keys = sorted({k for e in ev for k in e.get("keys", [])})
            card = base(c, "fact")
            pol = "strength" if all(e["polarity"] == "strength" for e in ev) else "concern"
            card.update({
                "fact": " ".join(e["fact"] for e in ev),
                "source": ", ".join(keys[:10]) + (" …" if len(keys) > 10 else ""),
                "evidence_keys": keys,
                "data_view": ("Данные скорее говорят о сильной стороне. " if pol == "strength"
                              else "Данные указывают на зону внимания. ")
                             + " ".join(e.get("hint", "") for e in ev).strip(),
                "polarity": pol,
            })
        else:
            card = base(c, "behavior")
            card.update({
                "fact": "",
                "source": "",
                "data_view": "Прямых данных в Jira за период нет — оценка опирается на примеры из разговора.",
            })
        cards.append(card)

    return {
        "meta": {
            "id": f"{activity['login']}_{activity['period'][0][:7]}",
            "person": name, "role": role_id, "role_title": role["title"], "period": period_label,
            "players": [manager_name, name], "suits": common["suits"], "scale": common["scale"],
            "generated_from": {"issues": len(activity.get("issues", [])), "signals": len(sig["signals"]),
                               "llm_evidence": len(list(llm_evidence))},
        },
        "cards": cards,
    }


def check_deck(deck, activity):
    """Автопроверка без человека: ключи из выгрузки, баланс, отсутствие оценочных слов."""
    errors = []
    keys = {r["key"] for r in activity.get("issues", [])}
    banned = ("не умеет", "плохо", "ленив", "безответствен", "неспособ", "провал")
    for c in deck["cards"]:
        for k in c.get("evidence_keys", []):
            if k not in keys:
                errors.append(f"карта {c['id']}: ключ {k} не из выгрузки")
        text = " ".join([c.get("fact", ""), c.get("question", "")]).lower()
        for w in banned:
            if w in text:
                errors.append(f"карта {c['id']}: оценочное слово «{w}»")
    suits = {c["suit"] for c in deck["cards"]}
    if len(deck["cards"]) < 4 or len(suits) < 2:
        errors.append("колода слишком узкая: меньше 4 карт или одна масть")
    return errors


def sanitize(deck, activity):
    """Карты-факты, не прошедшие проверку, превращаются в поведенческие. → (deck, замечания)."""
    errors = check_deck(deck, activity)
    bad = {int(e.split()[1].rstrip(":")) for e in errors if e.startswith("карта ")}
    for c in deck["cards"]:
        if c["id"] in bad and c["kind"] == "fact":
            c.update({"kind": "behavior", "kind_title": KIND_TITLE["behavior"], "fact": "", "source": "",
                      "evidence_keys": [], "polarity": None,
                      "data_view": "Факт не прошёл автопроверку и снят — оценка опирается на примеры из разговора."})
    return deck, errors


def report(deck, errors=()):
    """Отчёт для руководителя без содержания карт."""
    by_suit, by_kind = {}, {}
    for c in deck["cards"]:
        by_suit[c["suit"]] = by_suit.get(c["suit"], 0) + 1
        by_kind[c["kind_title"]] = by_kind.get(c["kind_title"], 0) + 1
    g = deck["meta"]["generated_from"]
    return "\n".join([
        f"Колода: {len(deck['cards'])} карт · роль «{deck['meta']['role_title']}» · период {deck['meta']['period']}",
        "  по мастям: " + ", ".join(f"{s} {n}" for s, n in sorted(by_suit.items(), key=lambda x: SUIT_ORDER.index(x[0]))),
        "  по типам:  " + ", ".join(f"{k} {n}" for k, n in by_kind.items()),
        f"  источники: задач {g['issues']}, сигналов {g['signals']}, доказательств от LLM {g['llm_evidence']}",
        "  автопроверка: " + ("пройдена" if not errors else f"{len(errors)} замечаний (карты исправлены или заменены)"),
        "Содержание карт запечатано и откроется, когда в комнату войдут оба.",
    ])
