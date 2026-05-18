@echo off
setlocal
REM ============================================
REM WebSearchAi — Windows installer
REM ============================================

echo.
echo ============================================
echo  WebSearchAi installer
echo ============================================

REM ---- Step 1: ensure Python exists ----
python --version >nul 2>&1
if errorlevel 1 (
  echo [X] Python is not installed or not on PATH.
  echo     Install Python 3.10+ from https://www.python.org/downloads/
  pause
  exit /b 1
)

echo.
echo --- [1/4] Creating virtual environment (.venv) ---
if exist ".venv" (
  echo .venv already exists. Skipping creation.
) else (
  python -m venv .venv
  if errorlevel 1 goto :err
  echo .venv created.
)

REM ---- Step 2: activate venv ----
call .venv\Scripts\activate.bat
if errorlevel 1 goto :err

echo.
echo --- [2/4] Installing Python dependencies ---
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :err

echo.
echo --- [3/4] Installing Playwright Chromium browser ---
python -m playwright install chromium
if errorlevel 1 goto :err

echo.
echo --- [4/4] Preparing .env ---
if not exist .env (
  copy .env.example .env >nul
  echo .env created from .env.example.
  echo     -^> IMPORTANT: edit .env and set MISTRAL_API_KEY
) else (
  echo .env already exists.
)

echo.
echo ============================================
echo  Installation complete.
echo.
echo  Next:
echo    1. Edit .env  -^>  set MISTRAL_API_KEY
echo    2. Start server:  start.bat
echo    3. Or use CLI:    cli.bat run "your goal here"
echo ============================================
echo.
pause
exit /b 0

:err
echo.
echo [X] Installation failed. Check the messages above.
pause
exit /b 1
