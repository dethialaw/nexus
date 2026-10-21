#!/usr/bin/env bash
# PreToolUse hook (Bash): blocks git commands that rewrite or bypass shared history.
# Pushing a feature branch stays allowed; `main` changes only through a merged PR.
set -euo pipefail

command=$(jq -r '.tool_input.command // empty')
sp='(^|[[:space:];&|])'

block() {
  echo "BLOCKED by .claude/hooks/git-guardrails.sh ($1): $command" >&2
  exit 2
}

if grep -qE "${sp}git[[:space:]]+push" <<<"$command"; then
  grep -qE "(--force|--force-with-lease|[[:space:]]-[a-zA-Z]*f([[:space:]]|$)|[[:space:]]\+)" <<<"$command" \
    && block "force push"
  grep -qE "([[:space:]]|:)main([[:space:]]|$)" <<<"$command" && block "push to main"
  [[ "$(git -C "${CLAUDE_PROJECT_DIR:-.}" branch --show-current 2>/dev/null)" == "main" ]] \
    && block "push while on main"
fi
# Merging is the maintainer's call: the ruleset stops a red PR, not a green unreviewed one.
grep -qE "${sp}gh[[:space:]]+pr[[:space:]]+merge" <<<"$command" && block "gh pr merge"
grep -qE "${sp}gh[[:space:]]+api" <<<"$command" \
  && grep -qE "(pulls/[^[:space:]]+/merge|mergePullRequest|enablePullRequestAutoMerge)" <<<"$command" \
  && block "merge through the API"
grep -qE "${sp}git[[:space:]]+reset[[:space:]]+(.*[[:space:]])?--hard" <<<"$command" && block "reset --hard"
grep -qE "${sp}git[[:space:]]+clean[[:space:]]+(.*[[:space:]])?-[a-zA-Z]*f" <<<"$command" && block "clean -f"
grep -qE "${sp}git[[:space:]]+branch[[:space:]]+(.*[[:space:]])?-D" <<<"$command" && block "branch -D"
exit 0
