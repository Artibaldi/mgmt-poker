# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- **One suit model everywhere:** ♠ hard skills · ♦ soft skills · ♣ personal qualities · ♥ management — in signals,
  the offline game, the demo deck and the docs (previously the offline mode used older cluster names).
- **Docs brought up to date with the online mode:** method (two modes side by side), Jira integration (automatic
  and manual preparation), contributing (where each kind of change goes), security (room links, relay storage,
  LLM), PR template; new `CLAUDE.md` with the project map and hard rules for agents.

## [0.2.0] — 2026-10-18

Online sessions: two screens, a sealed deck, a competency model.

### Added

- **Competency model:** 4 suits (hard, soft, personal qualities, management), 18 common competencies and 8 role
  profiles (system and business analyst, developer, QA, DevOps, architect, project manager, team lead) with
  behavioral anchors for every level.
- **Automatic deck** (`poker.new`, `poker/deck.py`): the manager picks only the person and the period; cards come
  from Jira signals, behavioral questions and follow-ups of last time's agreements; auto-check; content-free report.
- **Seal:** stdlib encryption of the deck, key split between the two links; opens only when both are in the room.
- **Online room** (`poker.relay`, `poker/web/`): lobby, frame, read → blind estimate with “why” (commit–reveal) →
  reveal with “what the data shows” → co-signed agreement; pause and “go back”; recording timecodes; summary
  confirmed by both; export for both players (Markdown, PDF via print).
- **Claude connection** (`--llm claude`): episodes from comments, each verified against the export;
  `POKER_LLM_CMD` for other providers, `scripts/llm_anthropic.py` for the API.
- **Docs:** online session spec and trust model, step-by-step local deployment, model connection guide,
  competency model.
- **Tests:** relay (live server, cheating attempts), deck for all roles, seal, LLM validation, Node tests for the
  room core.

## [0.1.0] — 2026-10-18

The first MVP.

### Added

- **Jira context:** read-only export of one person's activity for a period — issues, own comments,
  transitions, field edits, worklogs, role fields; field mapping in `config/jira.json`.
- **Signals:** delegation, silent delegated work, due-date shifts, overdue, tracker after the fact, off-hours,
  self-assigned roles, handoff — each with issue keys and a question to check.
- **Deck:** JSON schema, validator, prompts for the dossier and the cards, a fictional demo deck.
- **Game:** one offline HTML file — blind estimates 1-2-3-5-8-?, reveal with the gap in steps, the manager's
  hypothesis after the reveal, question cards, notes, summary by suit, Markdown and JSON export.
- **Claude Code skill** `/poker <login> <period>`.
- **Repository presentation:** English README with Russian translation, hero banner, screenshots, Apache-2.0
  license, contributing and security guides, roadmap, issue and PR templates, CI, Dependabot.
- **Privacy:** `sessions/` git-ignored, hygiene check in tests and CI.

[Unreleased]: https://github.com/Artibaldi/mgmt-poker/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/Artibaldi/mgmt-poker/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Artibaldi/mgmt-poker/releases/tag/v0.1.0
