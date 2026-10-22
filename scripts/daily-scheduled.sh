#!/bin/zsh
# The scheduled daily run (launchd job com.samueleonelia.rpghunt-daily, see scripts/com.samueleonelia.rpghunt-daily.plist).
# Reads every shop, checks what's new, puts the deals on the site, commits and pushes,
# then shows a Mac notification. Runs outside Claude, so the browsing agent works.
# Go-live is refused (and you are notified) when a step failed, when the project is not on
# branch main, or when the deal count collapses.
set -u
cd /Users/samueleonelia/claudeCode/personal/rpgArchive || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$HOME/.local/bin"
echo "=== $(date '+%Y-%m-%d %H:%M') RPG Hunt daily run ==="
.venv/bin/python -m scraper.daily --go-live --notify 2>&1 | grep -v " INFO: Fetched"
echo "=== exit ${pipestatus[1]} ==="
