@echo off
rem Web UI mode: view tasks from a browser (remote monitoring)
rem First time only: .venv\Scripts\pip install fastapi uvicorn
cd /d "%~dp0"
start "" ".venv\Scripts\python.exe" main_web.py --browser
