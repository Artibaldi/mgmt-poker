# CLAUDE.md

«Управленческий покер» — формат 1:1 на фактах из Jira. Онлайн-режим: руководитель задаёт человека и период,
колода собирается автоматически по модели компетенций роли и запечатывается, оба играют на своих экранах
по ВКС, слепота оценок обеспечена протоколом commit–reveal. Офлайн-режим — один HTML-файл на одном экране.

## Карта проекта

| Что | Где |
|---|---|
| Создать встречу (человек + период → печать → 2 ссылки) | `poker/new.py` |
| Комната: журнал событий, проверка протокола, итоги | `poker/relay.py` |
| Клиент комнаты; ядро (SHA-256, печать, commit–reveal, `reduce`, выгрузка) | `poker/web/room.html`, `poker/web/core.js` |
| Сборка колоды по модели компетенций, автопроверка | `poker/deck.py` |
| Модель компетенций: 18 общих + 8 ролей | `competencies/common.json`, `competencies/roles/*.json` |
| Выгрузка Jira (read-only) / сигналы | `poker/fetch.py` / `poker/signals.py` |
| Печать колоды (совместима с `core.js`) | `poker/seal.py` |
| Подключение LLM (Claude по умолчанию) | `poker/llm.py`, `prompts/llm-evidence.md` |
| Офлайн-игра | `poker/build.py`, `poker/template/game.html` |
| Метод · путь и доверие · развёртывание · LLM · компетенции · Jira | `docs/{method,spec-online,deploy-local,llm,competencies,jira-integration}.md` |

## Команды

```bash
scripts/test.sh                                   # всё: Python + Node тесты, демо-сборка, гигиена sessions/
python3 -m unittest discover -s tests -t .        # только Python (stdlib, 3.9+)
node --test tests/core.test.js                    # ядро комнаты
python3 -m poker.relay                            # комната на :8765
python3 -m poker.new --login demo --from 2026-09-01 --to 2026-09-30 --role team-lead --name Алексей \
  --activity examples/demo-activity.json --relay http://localhost:8765 --force   # встреча без Jira
uv run --with requests python -m poker.new --login <login> --from … --to … [--llm claude]  # с Jira
```

## Жёсткие правила

- **Данные о реальных людях — только в `sessions/` и `config/team.json`** (под .gitignore). В коде, тестах,
  примерах, скриншотах, коммитах и PR — только вымышленные люди и ключи (`jdoe`, `PAY-1xx`). Перед коммитом
  `git ls-files sessions config` показывает только `.gitkeep` и `*.example.json`.
- **Колоду до встречи не видит никто, включая тебя.** Не читай и не расшифровывай `deck.sealed.json`,
  `activity.sealed.json`, `links.txt`, `room-log.jsonl` реальных сессий. Показывай только отчёт `poker.new`.
- **Слепота:** правило в `core.js` (`reduce`) и `relay.py` (`validate`) меняется только синхронно, с тестами в
  `tests/core.test.js` и `tests/test_relay.py`. Печать — синхронно в `seal.py` и `core.js`.
- **Jira — только чтение.** Ничего не писать в Jira и Confluence.
- **Без внешних зависимостей в браузере**; ретранслятор и генератор — stdlib, совместимость с Python 3.9.
- Документация на русском (README — на английском с русской версией). При изменении правил или запуска
  обновлять оба README и строку в CHANGELOG «Unreleased».
- Коммиты на русском, с указанием области: `Комната: …`, `Колода: …`, `Документация: …`.
