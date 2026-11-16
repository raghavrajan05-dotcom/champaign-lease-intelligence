#!/usr/bin/env bash
# Scrape Green Street Realty from THIS computer and publish the result to the
# GitHub "data" branch. Green Street approved one read of their public student
# search page per day, but their site blocks GitHub's servers (403), so this
# runs on your laptop instead of in the GitHub Action.
#
# Safe to run many times a day: if today's file is already published it stops
# before contacting Green Street, so their site is read at most once per day.
#
# Usage (from the project folder):  bash scripts/scrape_greenstreet_local.sh
# Runs automatically once scripts/install_greenstreet_schedule.sh has been run.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "--- $(date '+%F %T') Green Street job starting"

TODAY="$(date +%F)"
NAME="green-street-realty_$TODAY.csv"

# Just after the laptop wakes, wifi can take a moment: try a few times.
for attempt in 1 2 3 4 5; do
  if git fetch -q origin data 2>/dev/null; then break; fi
  if [ "$attempt" = 5 ]; then echo "No connection to GitHub; will try again later."; exit 0; fi
  sleep 30
done

if git cat-file -e "origin/data:data/$NAME" 2>/dev/null; then
  echo "Already published today ($NAME). Nothing to do."
  exit 0
fi

source .venv/bin/activate
if [ ! -f "data/$NAME" ]; then   # scraped earlier today but the upload failed? reuse it
  python -m src.scrapers.greenstreet
fi

# Commit just that file to the data branch, without touching your current branch.
# The daily GitHub job pushes to the same branch, so retry if it got there first.
publish() {
  local tmp
  tmp="$(mktemp -d)"
  git fetch -q origin data
  git worktree add -q --detach "$tmp" origin/data
  mkdir -p "$tmp/data" "$tmp/latest"
  cp "data/$NAME" "$tmp/data/"
  cp "data/$NAME" "$tmp/latest/green-street-realty.csv"
  local ok=0
  (
    cd "$tmp"
    git add -f data latest
    git commit -qm "Green Street scrape $TODAY (local, with permission)"
    git push -q origin HEAD:data
  ) && ok=1
  git worktree remove --force "$tmp" 2>/dev/null || true
  [ "$ok" = 1 ]
}

for attempt in 1 2 3; do
  if publish; then
    echo "Published data/$NAME to the data branch."
    exit 0
  fi
  echo "Upload attempt $attempt failed; retrying."
  sleep 5
done
echo "Could not upload after 3 tries. The file is saved locally; the next run will retry."
exit 1
