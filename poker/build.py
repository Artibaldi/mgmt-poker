#!/usr/bin/env python3
"""cards.json → game.html: автономная игра «Управленческий покер» (один файл, без сети).

Запуск: python3 -m poker.build sessions/IvanovII_2026-06/cards.json [--out game.html]
Формат карт — schema/cards.schema.json, пример — examples/demo-cards.json.
"""
import argparse
import json
import sys
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent / "template" / "game.html"
PLACEHOLDER = "/*__POKER_DATA__*/null"
SUITS = {"♠", "♥", "♦", "♣"}
MARKERS = {"strength", "growth", "disputed", "question"}
CARD_REQUIRED = ("id", "suit", "competence", "marker")


def validate(data):
    """Список ошибок; пустой — карты годны для сборки."""
    errors = []
    meta = data.get("meta") or {}
    for k in ("id", "person", "period"):
        if not meta.get(k):
            errors.append(f"meta.{k}: обязательное поле")
    cards = data.get("cards") or []
    if not cards:
        errors.append("cards: пусто")
    seen = set()
    for i, c in enumerate(cards):
        where = f"cards[{i}]"
        for k in CARD_REQUIRED:
            if c.get(k) in (None, ""):
                errors.append(f"{where}.{k}: обязательное поле")
        if c.get("id") in seen:
            errors.append(f"{where}.id: дубль {c.get('id')}")
        seen.add(c.get("id"))
        if c.get("suit") and c["suit"] not in SUITS:
            errors.append(f"{where}.suit: {c['suit']!r} не из {''.join(sorted(SUITS))}")
        if c.get("marker") and c["marker"] not in MARKERS:
            errors.append(f"{where}.marker: {c['marker']!r} не из {sorted(MARKERS)}")
        if c.get("marker") != "question" and not c.get("fact"):
            errors.append(f"{where}.fact: у карты-факта нужен факт")
        if not c.get("question"):
            errors.append(f"{where}.question: у карты нужен вопрос")
    return errors


def render(data, template=None):
    tpl = (template or TEMPLATE.read_text(encoding="utf-8"))
    if PLACEHOLDER not in tpl:
        raise ValueError(f"в шаблоне нет {PLACEHOLDER}")
    # </script> внутри текста карт не должен закрыть тег
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = f"Покер — {data['meta']['person']}, {data['meta']['period']}"
    return tpl.replace(PLACEHOLDER, payload).replace("<title>Управленческий покер</title>",
                                                     f"<title>{_esc(title)}</title>")


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cards", help="путь к cards.json")
    ap.add_argument("--out", help="куда положить html (по умолчанию game.html рядом с cards.json)")
    args = ap.parse_args()
    src = Path(args.cards)
    data = json.loads(src.read_text(encoding="utf-8"))
    errors = validate(data)
    if errors:
        sys.exit("cards.json не прошёл проверку:\n  " + "\n  ".join(errors))
    out = Path(args.out) if args.out else src.parent / "game.html"
    out.write_text(render(data), encoding="utf-8")
    print(f"{len(data['cards'])} карт → {out}")


if __name__ == "__main__":
    main()
