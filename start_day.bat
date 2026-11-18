@echo off
REM Windows: Task Scheduler runs this at 08:45 Mon-Fri.
cd /d "%~dp0"
if not exist state mkdir state
if exist .venv\Scripts\python.exe (set PY=.venv\Scripts\python.exe) else (set PY=python)
%PY% run.py day >> state\day.log 2>&1
