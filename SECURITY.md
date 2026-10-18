# Security and privacy

## Status

Management Poker is an **MVP for personal use** by a manager on their own machine.

- `poker.fetch` uses Basic auth with the credentials from `.env` (git-ignored). Use a personal token where
  your Jira supports it.
- `verify_ssl` can be turned off for self-signed certificates — only do that inside a trusted network.
- **Online room.** The relay listens on the manager's laptop over plain http — use it inside a corporate VPN or
  office network only; anywhere else put an HTTPS proxy in front. Each link carries a role token and half of the
  deck key after `#`; treat the employee's link like a password and send it only to that person.
  `sessions/<…>/links.txt` holds both links. Rooms expire after `room_ttl_days` and a closed room is read-only.
- **What the relay stores:** commitments (hashes) before the reveal; after the reveal — estimates, reasons,
  agreements in `room-log.jsonl`; the deck and the Jira activity only encrypted. Trust model and its honest
  limits: [docs/spec-online.md](docs/spec-online.md).
- **LLM.** With `--llm claude` the employee's Jira comments are sent to the model provider. Agree this with your
  security team first: [docs/llm.md](docs/llm.md).
- **Offline game.** The session lives in the browser's `localStorage`. Anyone with access to that browser
  profile can read the estimates and notes. Use “Начать заново” after the session or keep the JSON export safe.

## People's data

Activity exports, dossiers, decks, room logs, built games and session results describe real people. They
belong in `sessions/`; the team registry is `config/team.json`. Both are git-ignored and must never be
committed, attached to issues or pasted into pull requests. `scripts/test.sh` and CI fail if anything under `sessions/` is tracked.

## Supported versions

Only the latest commit on `main` is supported.

## Reporting a vulnerability

Please **do not open a public issue.** Report it privately through
[GitHub Security Advisories](https://github.com/Artibaldi/mgmt-poker/security/advisories/new).

Include what is affected, how to reproduce it (with the demo deck, never real data) and the impact you expect.
