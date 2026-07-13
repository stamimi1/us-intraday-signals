#!/usr/bin/env bash
# Force-push live/*.json as the single-commit `data-live` branch.
# The dashboard fetches these via raw.githubusercontent with a cache-buster,
# giving ~1-minute data freshness without a Pages rebuild per cycle.
set -euo pipefail

[ -f live/signals.json ] || { echo "no data to publish"; exit 0; }

cd live
rm -rf .git
git init -q
git checkout -qb data-live
git add signals.json performance.json ledger.json 2>/dev/null || git add -A
git -c user.name="engine-bot" -c user.email="actions@users.noreply.github.com" \
    commit -qm "data $(date -u +%FT%TZ)"
git push -qf "https://x-access-token:${GITHUB_TOKEN:-$(gh auth token)}@github.com/${GITHUB_REPOSITORY:-stamimi1/us-intraday-signals}.git" data-live
rm -rf .git
echo "published data-live @ $(date -u +%T)"
