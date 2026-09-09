@echo off
setlocal
cd /d "%~dp0"

set "PRESERVED_DATA=%CD%\.build-preserved-data"
set "HAD_DATA="
if exist "%PRESERVED_DATA%" (
    echo A previous build data backup still exists:
    echo %PRESERVED_DATA%
    echo Restore or rename it before building again.
    exit /b 1
)

if exist "dist\MotionLab Gait\data" (
    echo Preserving patient data before rebuilding...
    move "dist\MotionLab Gait\data" "%PRESERVED_DATA%" >nul
    if errorlevel 1 goto :failed
    set "HAD_DATA=1"
)

if not exist ".venv\Scripts\pyinstaller.exe" (
    echo Installing build dependencies...
    ".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
    if errorlevel 1 goto :failed
)

echo Building the Windows application...
".venv\Scripts\pyinstaller.exe" --noconfirm --clean --windowed --onedir ^
    --name "MotionLab Gait" ^
    --paths "src" ^
    --add-data "models;models" ^
    --collect-binaries mediapipe ^
    --collect-data mediapipe ^
    --hidden-import mediapipe.tasks.c ^
    "src\motionlab_gait\__main__.py"
if errorlevel 1 goto :failed

if defined HAD_DATA (
    echo Restoring patient data...
    move "%PRESERVED_DATA%" "dist\MotionLab Gait\data" >nul
    if errorlevel 1 goto :failed
)

rem PyInstaller can pick up an incompatible Poppler ICU from the developer PATH.
rem Qt 6 on supported Windows uses the operating-system ICU implementation.
if exist "dist\MotionLab Gait\_internal\icuuc.dll" del /q "dist\MotionLab Gait\_internal\icuuc.dll"
if exist "dist\MotionLab Gait\_internal\icudt78.dll" del /q "dist\MotionLab Gait\_internal\icudt78.dll"

rem PySide 6.11 ships these matching MSVC runtime files beside Qt.
copy /y ".venv\Lib\site-packages\PySide6\msvcp140.dll" "dist\MotionLab Gait\_internal\" >nul
copy /y ".venv\Lib\site-packages\PySide6\msvcp140_1.dll" "dist\MotionLab Gait\_internal\" >nul
copy /y ".venv\Lib\site-packages\PySide6\msvcp140_2.dll" "dist\MotionLab Gait\_internal\" >nul
copy /y ".venv\Lib\site-packages\PySide6\concrt140.dll" "dist\MotionLab Gait\_internal\" >nul
copy /y ".venv\Lib\site-packages\PySide6\msvcp140_codecvt_ids.dll" "dist\MotionLab Gait\_internal\" >nul

echo.
echo Build completed:
echo %CD%\dist\MotionLab Gait\MotionLab Gait.exe
exit /b 0

:failed
if exist "%PRESERVED_DATA%" (
    if not exist "dist\MotionLab Gait" mkdir "dist\MotionLab Gait"
    if not exist "dist\MotionLab Gait\data" (
        move "%PRESERVED_DATA%" "dist\MotionLab Gait\data" >nul
    )
)
echo Build failed.
exit /b 1
