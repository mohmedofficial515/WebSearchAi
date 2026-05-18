@echo off
REM ============================================
REM WebSearchAi — تشغيل CLI
REM Usage:  cli.bat run "your goal here"
REM         cli.bat explore https://example.com
REM         cli.bat clone https://example.com
REM ============================================

if not exist ".venv\Scripts\activate.bat" (
  echo [!] virtual env not found. Run install.bat first.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat

python run.py %*
