---
name: poker
description: Подготовка 1:1 в формате «Управленческий покер»: выгрузка активности человека из Jira за период → сигналы → досье → колода карт → автономная HTML-игра в sessions/. Use when: «подготовь покер с <человеком>», «1:1 по итогам месяца», «собери колоду», «восстанови игру». NOT for: публикация оценок куда-либо, массовые отчёты команды.
---

# /poker <jira-login> <YYYY-MM | from..to> [ФИО]

Метод — `docs/method.md`, подключение к Jira — `docs/jira-integration.md`.

## Шаги
1. **Период.** `2026-06` → `--from 2026-06-01 --to 2026-06-30`.
2. **Выгрузка** (read-only):
   `uv run --with requests python -m poker.fetch --login <login> --from … --to … --roles`
   Креды — `.env` / `--env <путь>` / `$POKER_ENV`. Нет кредов — спросить путь, не выдумывать.
   Проверить, что логин верный: 0 задач — почти всегда не тот логин.
3. **Сигналы:** `python3 -m poker.signals sessions/<login>_<YYYY-MM>/activity.json`.
4. **Встречи:** если задан `POKER_DAILY_DIR` — найти саммари за период с упоминанием человека
   (`grep -ril "<фамилия>"`). Тёзок различать по контексту и команде.
5. **Досье** по `prompts/dossier.md` → `sessions/<…>/dossier.md`. Показать пользователю профиль-гипотезу.
6. **Карты** по `prompts/cards.md` → `sessions/<…>/cards.json`.
7. **Сборка:** `python3 -m poker.build sessions/<…>/cards.json` → `game.html`; открыть `open <путь>`.

## Гардрейлы
- Всё про человека — только в `sessions/` (под .gitignore). Перед любым коммитом —
  `git status --porcelain sessions/` должен быть пуст.
- В Jira/Confluence ничего не писать. Артефакты claude.ai — только по явной просьбе.
- Факты без оценочных слов; у каждой карты-факта — проверяемый источник.
