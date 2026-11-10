#!/usr/bin/env bash
# Copy the scraped CSVs from the GitHub "data" branch into data/.
# Uses `git archive` so the files are written to disk without being staged for commit.
# (Raw HTML pages are no longer published to GitHub, so only data/ is synced.)
set -euo pipefail
git fetch -q origin data
git archive origin/data data | tar -x
echo "Synced. Newest files:"
ls -1 data | tail -4
