@echo off
REM Start the Retention Schedule Determination Engine on http://localhost:8050
cd /d %~dp0
if not exist .venv (
  python -m venv .venv
  .venv\Scripts\python -m pip install -q --upgrade pip
  .venv\Scripts\pip install -q -r requirements.txt
)
if exist .env for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do set "%%a=%%b"
echo Open http://localhost:8050
.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8050
