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
4. **Nobody sees the deck before the meeting.** The online deck is generated without a human and sealed; no
   command, log or report may print card content before both players are in the room.
5. **Blind means blind.** Estimates travel as commitments until both have played; the relay validates the
   protocol. Never add a code path that sends a vote before the reveal.
6. **No external dependencies in the browser.** `game.html`, `room.html` and `core.js` load nothing from the
   network; the relay and the deck tooling use the Python standard library only.

## Setup

You need **Python 3.9+**. Everything except `poker.fetch` uses the standard library; `poker.fetch` needs
`requests` (`pip install -r requirements.txt` or `uv run --with requests …`). Node.js runs the room-core tests.

```bash
# online room on the fictional demo activity
python3 -m poker.relay &
python3 -m poker.new --login demo --from 2026-09-01 --to 2026-09-30 --role team-lead --name Алексей \
  --activity examples/demo-activity.json --relay http://localhost:8765 --force
# offline game
python3 -m poker.build examples/demo-cards.json --out /tmp/demo.html && open /tmp/demo.html
```

## Checks

```bash
scripts/test.sh
```

It runs the Python tests, the Node tests of the room core, builds the demo deck, checks JavaScript syntax and
fails if anything under `sessions/` is tracked. CI runs the same steps on Python 3.9 and 3.12.

| Change | Where | Also update |
|---|---|---|
| New Jira signal | `poker/signals.py` (+ fact template in `poker/deck.py`) | test that fires it and stays quiet; `signals` of a competency; `docs/jira-integration.md`, READMEs |
| Competency, anchors, role | `competencies/*.json` | `tests/test_deck.py` checks structure; regenerate tables in `docs/competencies.md` |
| Room event or rule | `poker/web/core.js` (`reduce`) **and** `poker/relay.py` (`validate`) | `tests/core.test.js`, `tests/test_relay.py`, protocol table in `docs/spec-online.md` |
| Seal | `poker/seal.py` **and** `poker/web/core.js` | both must stay byte-compatible; `tests/test_seal.py` |
| LLM prompt or validation | `prompts/llm-evidence.md`, `poker/llm.py` | `tests/test_llm.py`, `docs/llm.md` |
| Offline deck format | `schema/cards.schema.json`, `poker/build.py` | demo deck, `tests/test_build.py` |

## Branches, commits and pull requests

- Branch from `main`: `feature/<name>`, `fix/<name>`, `chore/<name>`.
- Commit messages are in Russian, start with the area and describe the result:
  `Сигналы: молчание по делегированным задачам`.
- Fill in the pull request template. Include screenshots for UI changes (desktop and phone) — demo deck only.
- If rules or setup change, update both [README.md](README.md) and [README.ru.md](README.ru.md), and add a line
  to [CHANGELOG.md](CHANGELOG.md) under *Unreleased*.

## Code style

- Python 3.9-compatible, standard library first, functions over classes.
- Browser: vanilla JS and CSS, design tokens on `:root`, every text escaped before it goes into HTML.
- Examples and tests use only fictional people and issue keys (`PAY-1xx`, `jdoe`).
- Interface copy is Russian; keep it short and concrete.
