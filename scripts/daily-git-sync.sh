#!/usr/bin/env bash
# Daily LLM Systems Wiki auto-commit + push to GitHub.
# Installed via crontab; logs to logs/daily-git-sync.log

WIKI="/home/ailabadmin/LLM-Wiki"
LOG="$WIKI/logs/daily-git-sync.log"
LOCK="/tmp/llm-wiki-daily-git-sync.lock"

export PATH="/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin:$PATH"
export GIT_SSH_COMMAND="ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

mkdir -p "$WIKI/logs"

if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK"
  if ! flock -n 9; then
    echo "$(date -Is) already running, skip" >> "$LOG"
    exit 0
  fi
fi

{
  echo "======== $(date -Is) start ========"
  cd "$WIKI" || exit 1
  git fetch origin --quiet || echo "WARN: git fetch failed"
  "$WIKI/publish.sh" "Wiki auto-update $(date '+%Y-%m-%d')"
  echo "======== $(date -Is) done (exit $?) ========"
} >> "$LOG" 2>&1
