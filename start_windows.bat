@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo First-time setup is required.
    call setup_windows.bat
    if errorlevel 1 exit /b 1
)

set "PYTHONPATH=%CD%\src"
set "MPLCONFIGDIR=%CD%\data\cache\matplotlib"
set "MOTIONLAB_ARGS="
if /i "%MOTIONLAB_SMOKE_TEST%"=="1" set "MOTIONLAB_ARGS=--smoke-test --data-dir .test-output\launcher-smoke-data"
if not exist "logs" mkdir "logs"
echo [%DATE% %TIME%] Starting MotionLab Gait>"logs\startup.log"
".venv\Scripts\python.exe" -m motionlab_gait %MOTIONLAB_ARGS% >>"logs\startup.log" 2>&1
if errorlevel 1 (
    echo.
    echo MotionLab Gait could not start.
    echo Error log: %CD%\logs\startup.log
    type "logs\startup.log"
    pause
)
