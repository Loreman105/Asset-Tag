@echo off
setlocal EnableExtensions

rem Start the Inventory Hub, including its built-in mDNS responder.
rem Run this file as Administrator when using the default HTTP port (80).

cd /d "%~dp0"

set "PYTHON="
where py >nul 2>&1 && set "PYTHON=py -3"
if not defined PYTHON (
    where python >nul 2>&1 && set "PYTHON=python"
)

if not defined PYTHON (
    echo Python 3 was not found.
    echo Install Python 3.13 or newer from https://www.python.org/downloads/
    echo and select "Add Python to PATH", then run this file again.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating the project virtual environment...
    %PYTHON% -m venv .venv
    if errorlevel 1 goto :setup_failed
)

echo Installing or updating required packages...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :setup_failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :setup_failed

echo Starting Inventory Hub and mDNS discovery...
start "Inventory Hub" /D "%CD%" cmd /k ".venv\Scripts\python.exe run_inventory_hub.py"

rem Give Flask a moment to bind its HTTP port before opening the browser.
timeout /t 3 /nobreak >nul
start "" "http://InventoryHub.local"

echo Inventory Hub is running at http://InventoryHub.local
echo Close the "Inventory Hub" command window to stop it.
exit /b 0

:setup_failed
echo.
echo Setup failed. Check the messages above, then run this file again.
pause
exit /b 1
