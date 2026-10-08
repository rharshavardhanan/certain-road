#!/usr/bin/env bash
# Part 6: the three-road survey report (vision-estimated PCI, road lifespan, priority, frames).
# Usage: [build] -- with `build`, rebuild it from the existing runs first (~1 min).
source "$(dirname "$0")/_common.sh"
[ "${1:-}" = build ] && .venv/bin/python scripts/survey_environments.py --report-only
exec xdg-open runs/survey_environments/report.html
