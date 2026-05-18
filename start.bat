@echo off
REM ============================================
REM WebSearchAi — تشغيل الخادم (Web UI + API)
REM ============================================

if not exist ".venv\Scripts\activate.bat" (
  echo [!] virtual env not found. Run install.bat first.
  pause
  exit /b 1
)

if not exist ".env" (
  echo [!] .env not found. Copy from .env.example and add MISTRAL_API_KEY.
  pause
  exit /b 1
)

call .venv\Scripts\activate.bat

echo.
echo ============================================
echo  Starting WebSearchAi server...
echo  Open: http://127.0.0.1:8000
echo  Press Ctrl+C to stop.
echo ============================================
echo.

python serve.py
