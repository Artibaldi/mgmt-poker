"""Необязательное подключение LLM: доказательства компетенций из комментариев Jira.

Провайдер по умолчанию — Claude через Claude Code CLI (`claude -p`): та же авторизация, что у
пользователя, без ключей в проекте. Команду можно заменить через $POKER_LLM_CMD (например,
на свою обёртку над Anthropic API или на заглушку в тестах). Рекомендации и что уходит в
модель — docs/llm.md.

Ответ модели не доверяется: каждый эпизод проверяется по выгрузке (компетенция из списка,
ключи из выгрузки, цитата дословно есть в комментарии), остальное отбрасывается.
"""
import json
import os
import re
import shlex
import subprocess
from pathlib import Path

from poker.config import ROOT

PROMPT = ROOT / "prompts" / "llm-evidence.md"
MAX_COMMENT = 600
MAX_EVIDENCE = 8


def compact_activity(activity, max_comments=80):
    """Только то, что нужно модели: ключ, тема, его комментарии и переходы. Без чужих имён."""
    titles = {r["key"]: r.get("summary") or "" for r in activity.get("issues", [])}
    lines = []
    for d in activity.get("details", []):
        for c in d.get("comments", [])[:5]:
            body = re.sub(r"\[~[^\]]+\]", "@коллега", c.get("body") or "")[:MAX_COMMENT]
            lines.append(f"- {d['key']} «{titles.get(d['key'], '')}» {c.get('created', '')[:16]} комментарий: {body}")
        for t in d.get("transitions", [])[:6]:
            lines.append(f"- {d['key']} {t.get('created', '')[:16]} переход: {t.get('from')} → {t.get('to')}")
        if len(lines) >= max_comments:
            break
    return "\n".join(lines)


def build_prompt(activity, competencies):
    comp = "\n".join(f"- {c['id']}: {c['title']} — {c['description']} Где искать: {c.get('jira_hints', '')}"
                     for c in competencies)
    data = f"### Компетенции\n{comp}\n\n### Действия сотрудника\n{compact_activity(activity)}"
    text = PROMPT.read_text(encoding="utf-8").split("## Промт", 1)[1]
    return text.replace("{{DATA}}", data).strip()


def parse_json_array(text):
    """Устойчиво к ```json-фенсам и тексту вокруг."""
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.S) or re.search(r"(\[.*\])", text, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def validate(items, activity, competency_ids):
    keys = {r["key"] for r in activity.get("issues", [])}
    comments = {d["key"]: _norm(" ".join(c.get("body") or "" for c in d.get("comments", [])))
                for d in activity.get("details", [])}
    ok, rejected, seen = [], 0, set()
    for it in items:
        if not isinstance(it, dict):
            rejected += 1
            continue
        cid, ks = it.get("competency"), [k for k in it.get("keys", []) if isinstance(k, str)]
        quote = _norm(it.get("quote"))
        good = (cid in competency_ids and cid not in seen and ks and set(ks) <= keys
                and isinstance(it.get("fact"), str) and 10 <= len(it["fact"]) <= 400
                and it.get("polarity") in ("strength", "concern")
                and (not quote or any(quote in comments.get(k, "") for k in ks)))
        if good:
            seen.add(cid)
            ok.append({"competency": cid, "fact": it["fact"].strip(), "keys": ks,
                       "quote": it.get("quote", ""), "polarity": it["polarity"]})
        else:
            rejected += 1
    return ok[:MAX_EVIDENCE], rejected


def run(prompt, model=None, timeout=300):
    cmd = os.environ.get("POKER_LLM_CMD")
    argv = shlex.split(cmd) if cmd else ["claude", "-p", "--output-format", "text"] + (["--model", model] if model else [])
    r = subprocess.run(argv, input=prompt, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"LLM-команда завершилась с кодом {r.returncode}: {r.stderr.strip()[:300]}")
    return r.stdout


def find_evidence(activity, competencies, model=None):
    """→ (валидные эпизоды, сколько отброшено). Ошибка вызова не роняет сборку колоды."""
    try:
        raw = run(build_prompt(activity, competencies), model)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
        return [], f"LLM недоступна ({e.__class__.__name__}): колода собрана без неё"
    ok, rejected = validate(parse_json_array(raw), activity, {c["id"] for c in competencies})
    return ok, f"LLM: принято {len(ok)}, отброшено проверкой {rejected}"
