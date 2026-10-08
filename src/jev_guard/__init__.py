"""Jev Guard: a Claude Code PreToolUse hook where code and Jev decide which shell commands need a human.

It only ever tightens: it can deny a command or force a permission prompt, and it never approves
one. When it has no opinion — or Jev is unavailable — Claude Code's own permission rules decide.
"""
