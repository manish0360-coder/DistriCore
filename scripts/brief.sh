#!/usr/bin/env bash
# Session bootstrap (ADR-0005 §5.2).
#
# GENERATED, never hand-maintained. Everything below is derived from git or from files
# that already have a verification gate, so it cannot drift. This replaces the
# hand-written SESSION_CONTEXT.md that was considered and rejected.
#
# Usage:  make brief   ->  paste the output as the first message of a new AI session.
set -uo pipefail
cd "$(dirname "$0")/.."

rule() { printf '\n== %s %s\n' "$1" "$(printf '=%.0s' $(seq 1 $((66 - ${#1}))))"; }

echo "DISTRICORE — SESSION BRIEF   $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "Repository is the source of truth. This brief is generated; do not edit it."

rule "BRANCH & HEAD"
git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "(not a git repository)"
git log --oneline -10 2>/dev/null || true

rule "WORKING TREE"
if [ -n "$(git status --short 2>/dev/null)" ]; then
  echo "DIRTY — in-flight work. A session must not end in this state (ADR-0005 §6.4)."
  git status --short
else
  echo "clean"
fi

rule "LAST VERIFICATION"
if [ -f .verify-result ]; then
  cat .verify-result
  echo "(stale if HEAD above differs from the commit shown)"
else
  echo "never run on this machine — run: make verify"
fi

rule "MILESTONE STATE"
sed -n '1,12p' PROJECT_STATE.md 2>/dev/null || echo "PROJECT_STATE.md missing"

rule "NEXT TASK"
cat NEXT_TASK.md 2>/dev/null || echo "NEXT_TASK.md missing — write it before continuing"

rule "OPEN TECHNICAL DEBT"
latest=$(ls -1 docs/M*_Verification_Report.md 2>/dev/null | sort | tail -1)
if [ -n "${latest:-}" ]; then
  echo "from $latest"
  grep -E '^\| (TD|\*\*TD)-[0-9]+' "$latest" | cut -c1-150
else
  echo "(no verification report yet)"
fi

rule "DO NOT RETRY — negative results from earlier sessions"
if [ -f docs/_session/NOTES.md ]; then cat docs/_session/NOTES.md; else echo "(none recorded)"; fi

rule "STANDING RULES"
cat <<'RULES'
  * docs/ is the specification. Where code and documents disagree, documents win (C-1).
  * `make verify` inside Docker is the only authority (N-12).
  * One task per session. Never end with uncommitted work (ADR-0005 §7).
  * Architecture is enforced by lint-imports. It has caught the author twice.
  * Read docs/00_Engineering_Foundation.md before changing anything structural.
RULES
echo
