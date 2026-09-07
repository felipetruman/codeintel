#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${CODEINTEL_BIN:-$HOME/.local/bin/codeintel}"

if [[ ! -x "$BIN" ]]; then
  BIN="$ROOT/target/release/codeintel"
fi

if [[ ! -x "$BIN" ]]; then
  echo "codeintel binary not found: $BIN" >&2
  exit 1
fi

echo "CodeIntel binary: $BIN"

# Claude skill
mkdir -p "$HOME/.claude/skills/codeintel"

cp \
  "$ROOT/skills/codeintel/SKILL.md" \
  "$HOME/.claude/skills/codeintel/SKILL.md"

echo "Claude Code skill installed."

CLAUDE_GLOBAL="$HOME/.claude/CLAUDE.md"

mkdir -p "$(dirname "$CLAUDE_GLOBAL")"
touch "$CLAUDE_GLOBAL"

if ! grep -Fq '<!-- CODEINTEL:START -->' "$CLAUDE_GLOBAL"; then
cat >> "$CLAUDE_GLOBAL" <<'BLOCK'

<!-- CODEINTEL:START -->
When working in a code repository, prefer CodeIntel MCP tools for broad discovery.
Use `code_context` before broad repository exploration and `code_search` for repository-wide lexical or regex search.
Fall back to native tools when CodeIntel is insufficient or unavailable.
<!-- CODEINTEL:END -->
BLOCK
fi

if command -v claude >/dev/null 2>&1; then
  claude mcp remove codeintel -s user >/dev/null 2>&1 || true

  if claude mcp add --scope user codeintel -- "$BIN" mcp; then
    echo "Claude Code MCP installed."
  else
    echo "WARNING: Claude MCP registration failed." >&2
  fi
else
  echo "Claude Code not detected."
fi

# Codex skill
AGENTS_HOME="${AGENTS_HOME:-$HOME/.agents}"

mkdir -p "$AGENTS_HOME/skills/codeintel"

cp \
  "$ROOT/skills/codeintel/SKILL.md" \
  "$AGENTS_HOME/skills/codeintel/SKILL.md"

CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"

mkdir -p "$CODEX_HOME"

CODEX_AGENTS="$CODEX_HOME/AGENTS.md"
touch "$CODEX_AGENTS"

if ! grep -Fq '<!-- CODEINTEL:START -->' "$CODEX_AGENTS"; then
cat >> "$CODEX_AGENTS" <<'BLOCK'

<!-- CODEINTEL:START -->
For repository-wide discovery, prefer CodeIntel.
Call `code_context` before broad codebase exploration and use `code_search` for repository-wide lookup.
Native shell, rg and file reads remain fallback mechanisms.
<!-- CODEINTEL:END -->
BLOCK
fi

if command -v codex >/dev/null 2>&1; then
  codex mcp remove codeintel >/dev/null 2>&1 || true

  if codex mcp add codeintel -- "$BIN" mcp; then
    echo "Codex MCP installed."
  else
    echo "WARNING: Codex MCP registration failed." >&2
  fi
else
  echo "Codex not detected."
fi

echo
echo "Agent integration setup complete."
