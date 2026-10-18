# Changelog

All notable changes to this project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

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

[Unreleased]: https://github.com/Artibaldi/mgmt-poker/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Artibaldi/mgmt-poker/releases/tag/v0.1.0
