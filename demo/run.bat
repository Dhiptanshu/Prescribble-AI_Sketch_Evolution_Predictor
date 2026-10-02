@echo off
rem One-command launcher for Windows: starts the local server and opens the browser.
cd /d "%~dp0"
set PORT=8765
start "" http://localhost:%PORT%
python serve.py %PORT%
