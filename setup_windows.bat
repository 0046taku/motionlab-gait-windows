@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto :install

where py >nul 2>nul
if not errorlevel 1 (
    py -3.12 -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>nul
    if not errorlevel 1 (
        echo Creating the local Python environment...
        py -3.12 -m venv .venv
        if errorlevel 1 goto :failed
        goto :install
    )
)

where python >nul 2>nul
if not errorlevel 1 (
python -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>nul
    if not errorlevel 1 (
        echo Creating the local Python environment...
        python -m venv .venv
        if errorlevel 1 goto :failed
        goto :install
    )
)

set "CODEX_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%CODEX_PYTHON%" (
    echo Creating the local Python environment...
    "%CODEX_PYTHON%" -m venv .venv
    if errorlevel 1 goto :failed
    goto :install
)

echo Python 3.12 was not found.
echo Install 64-bit Python 3.12 from https://www.python.org/downloads/windows/
pause
exit /b 1

:install
echo Installing MotionLab Gait dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :failed

if not exist "models\pose_landmarker_full.task" goto :models
if not exist "models\blaze_face_short_range.tflite" goto :models
goto :ready

:models
    echo Downloading the official MediaPipe models...
    set "PYTHONPATH=%CD%\src"
    ".venv\Scripts\python.exe" tools\download_model.py
    if errorlevel 1 goto :failed

:ready

echo.
echo Setup completed. Double-click start_windows.bat to launch the app.
pause
exit /b 0

:failed
echo.
echo Setup failed. Check the network connection and error message above.
pause
exit /b 1
