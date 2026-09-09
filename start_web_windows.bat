@echo off
setlocal
cd /d "%~dp0"

if not exist "web\dist\index.html" (
  echo Web build was not found.
  echo Run the web build first or use the public HTTPS URL.
  pause
  exit /b 1
)

set "WEB_PORT=8080"
if exist ".venv\Scripts\python.exe" (
  start "MotionLab Gait Web Server" /min ".venv\Scripts\python.exe" -m http.server %WEB_PORT% -d "web\dist"
) else (
  start "MotionLab Gait Web Server" /min python -m http.server %WEB_PORT% -d "web\dist"
)
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:%WEB_PORT%"
