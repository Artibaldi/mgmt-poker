#!/usr/bin/env python3
"""Обёртка для POKER_LLM_CMD: промпт из stdin → Anthropic Messages API → текст в stdout.

  pip install anthropic && export ANTHROPIC_API_KEY=...
  export POKER_LLM_CMD="python3 scripts/llm_anthropic.py"
  export POKER_LLM_MODEL=claude-sonnet-5-5   # необязательно

Используйте, если на машине нет Claude Code. Подробности — docs/llm.md.
"""
import os
import sys

import anthropic

prompt = sys.stdin.read()
msg = anthropic.Anthropic().messages.create(
    model=os.environ.get("POKER_LLM_MODEL", "claude-sonnet-5-5"),
    max_tokens=4000,
    messages=[{"role": "user", "content": prompt}],
)
print("".join(b.text for b in msg.content if b.type == "text"))
