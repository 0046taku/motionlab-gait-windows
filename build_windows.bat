@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Run setup_windows.bat first.
    pause
    exit /b 1
)

echo Installing build tools...
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if errorlevel 1 goto :failed

echo Building the Windows application...
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onedir ^
    --name "MotionLab Gait" ^
    --paths "src" ^
    --add-data "models;models" ^
    --collect-all mediapipe ^
    --hidden-import mediapipe.tasks.c ^
    "src\motionlab_gait\__main__.py"
if errorlevel 1 goto :failed

echo.
echo Build completed:
echo %CD%\dist\MotionLab Gait\MotionLab Gait.exe
pause
exit /b 0

:failed
echo.
echo Build failed. Review the message above.
pause
exit /b 1
