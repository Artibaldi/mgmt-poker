# Security and privacy

## Status

Management Poker is an **MVP for personal use** by a manager on their own machine.

- `poker.fetch` uses Basic auth with the credentials from `.env` (git-ignored). Use a personal token where
  your Jira supports it.
- `verify_ssl` can be turned off for self-signed certificates — only do that inside a trusted network.
- The game stores the session in the browser's `localStorage`. Anyone with access to that browser profile can
  read the estimates and notes. Use “Начать заново” after the session or keep the JSON export in a safe place.

## People's data

Activity exports, dossiers, decks, built games and session results describe real people. They belong in
`sessions/`, which is git-ignored, and must never be committed, attached to issues or pasted into pull
requests. `scripts/test.sh` and CI fail if anything under `sessions/` is tracked.

## Supported versions

Only the latest commit on `main` is supported.

## Reporting a vulnerability

Please **do not open a public issue.** Report it privately through
[GitHub Security Advisories](https://github.com/Artibaldi/mgmt-poker/security/advisories/new).

Include what is affected, how to reproduce it (with the demo deck, never real data) and the impact you expect.
