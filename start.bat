@echo off
REM ============================================
REM WebSearchAi — تشغيل الخادم والواجهة معاً
REM ============================================

if not exist ".venv\Scripts\activate.bat" (
  echo [!] virtual env not found. Run install.bat first.
  pause
  exit /b 1
)

if not exist ".env" (
  echo [!] .env not found. Copy from .env.example and add your API keys.
  pause
  exit /b 1
)

if not exist "web-chat\node_modules" (
  echo [!] node_modules not found. Running npm install...
  cd web-chat
  npm install
  cd ..
)

echo.
echo ============================================
echo  Starting WebSearchAi...
echo  Backend  : http://localhost:8000
echo  Frontend : http://localhost:5173/chat/
echo  Press Ctrl+C in each window to stop.
echo ============================================
echo.

REM -- Backend (Python / uvicorn) in a new window
start "WebSearchAi Backend" cmd /k "cd /d "%~dp0" && call .venv\Scripts\activate.bat && python serve.py"

REM -- Wait 3 seconds so uvicorn is ready before Vite starts
timeout /t 3 /nobreak >nul

REM -- Frontend (Vite dev server) in a new window
start "WebSearchAi Frontend" cmd /k "cd /d "%~dp0web-chat" && npm run dev"

REM -- Open the browser after another 3 seconds
timeout /t 3 /nobreak >nul
start "" "http://localhost:5173/chat/"

echo [OK] Both servers started. Browser opening...
echo.
