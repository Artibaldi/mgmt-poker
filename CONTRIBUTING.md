# Contributing

Thanks for helping build Management Poker! This guide covers how to run the project, how to check a change
and what a good pull request looks like.

## Principles

These shape every rule in the tool. A change that breaks one of them will not be merged:

1. **No ranking of people.** Signals are hypotheses for a conversation, never scores; there is no comparison
   between colleagues.
2. **Read-only towards Jira.** The tool never writes to Jira, Confluence or any other system.
3. **People's data stays local.** Nothing about real people goes into the repository, issues, screenshots or
   tests. Use the fictional deck in `examples/` and invented issue keys.
4. **The game is one offline file.** No network calls, no external scripts or fonts in `game.html`.

## Setup

You need **Python 3.9+**. `poker.build` and `poker.signals` use the standard library only; `poker.fetch`
needs `requests` (`pip install -r requirements.txt` or `uv run --with requests …`). Node.js is used only
for the template syntax check.

```bash
python3 -m poker.build examples/demo-cards.json --out /tmp/demo.html && open /tmp/demo.html
```

## Checks

```bash
scripts/test.sh
```

It runs the unit tests, builds the demo deck, checks the template's JavaScript syntax and fails if anything
under `sessions/` is tracked. CI runs the same steps on Python 3.9 and 3.12.

- A new signal goes in `poker/signals.py` with a test that fires it and a test that it stays quiet on a calm
  month, plus a row in `docs/jira-integration.md` and both READMEs.
- A change to the deck format updates `schema/cards.schema.json`, `poker/build.py` validation and the demo deck.

## Branches, commits and pull requests

- Branch from `main`: `feature/<name>`, `fix/<name>`, `chore/<name>`.
- Commit messages are in Russian, start with the area and describe the result:
  `Сигналы: молчание по делегированным задачам`.
- Fill in the pull request template. Include screenshots for UI changes (desktop and phone) — demo deck only.
- If rules or setup change, update both [README.md](README.md) and [README.ru.md](README.ru.md), and add a line
  to [CHANGELOG.md](CHANGELOG.md) under *Unreleased*.

## Code style

- Python: standard library first, functions over classes, no new runtime dependencies in `build` and `signals`.
- Game: vanilla JS and CSS in one file, design tokens on `:root`, every text escaped before it goes into HTML.
- Interface copy is Russian; keep it short and concrete.
