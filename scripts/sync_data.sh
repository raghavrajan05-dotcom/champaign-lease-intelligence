#!/usr/bin/env bash
# Copy the latest scraped files from the GitHub "data" branch into data/ and raw/.
# Uses `git archive` so the files are written to disk without being staged for commit.
set -euo pipefail
git fetch -q origin data
git archive origin/data data raw | tar -x
echo "Synced. Newest files:"
ls -1 data | tail -4