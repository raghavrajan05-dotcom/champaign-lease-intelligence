#!/usr/bin/env bash
# Scrape Green Street Realty from THIS computer and publish the result to the
# GitHub "data" branch. Green Street approved one read of their public student
# search page per day, but their site blocks GitHub's servers (403), so this
# runs on your laptop instead of in the GitHub Action.
#
# Usage (from the project folder):  bash scripts/scrape_greenstreet_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source .venv/bin/activate

python -m src.scrapers.greenstreet
FILE="data/green-street-realty_$(date +%F).csv"

# Commit just that file to the data branch, without touching your current branch.
git fetch -q origin data
TMP="$(mktemp -d)"
trap 'git worktree remove --force "$TMP" 2>/dev/null || true' EXIT
git worktree add -q --detach "$TMP" origin/data
mkdir -p "$TMP/data" "$TMP/latest"
cp "$FILE" "$TMP/data/"
cp "$FILE" "$TMP/latest/green-street-realty.csv"
(
  cd "$TMP"
  git add -f data latest
  git commit -qm "Green Street scrape $(date +%F) (local, with permission)" || echo "Nothing new to save"
  git push -q origin HEAD:data
)
echo "Published $FILE to the data branch."
