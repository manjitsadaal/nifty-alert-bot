#!/bin/bash
# Mac/Linux: cron runs this at 08:45 Mon-Fri.
cd "$(dirname "$0")"
mkdir -p state
PY=python3; [ -x .venv/bin/python ] && PY=.venv/bin/python
"$PY" run.py day >> state/day.log 2>&1
