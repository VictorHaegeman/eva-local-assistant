@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"

if exist "%PROJECT_DIR%backend\app\main.py" goto found_project

set "PROJECT_DIR=%USERPROFILE%\Desktop\Cursor\eva-local-assistant\"
if exist "%PROJECT_DIR%backend\app\main.py" goto found_project

echo [Eva] Impossible de trouver le projet Eva.
echo.
echo Ce fichier .bat doit etre dans la racine du projet, ou le projet doit etre ici:
echo %USERPROFILE%\Desktop\Cursor\eva-local-assistant
echo.
pause
exit /b 1

:found_project
for %%I in ("%PROJECT_DIR%.") do set "PROJECT_DIR=%%~fI\"

set "BACKEND_PY=python"
if exist "%PROJECT_DIR%backend\.venv\Scripts\python.exe" (
  set "BACKEND_PY=%PROJECT_DIR%backend\.venv\Scripts\python.exe"
)

echo Starting Eva from:
echo %PROJECT_DIR%
echo.

start "Eva Backend" cmd /k "cd /d ""%PROJECT_DIR%backend"" && ""%BACKEND_PY%"" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

start "Eva Frontend" cmd /k "cd /d ""%PROJECT_DIR%frontend"" && npm run dev -- --host 0.0.0.0"

echo Waiting for Eva to start...
for /l %%I in (1,1,12) do (
  powershell -NoProfile -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173 -TimeoutSec 1 > $null; exit 0 } catch { exit 1 }" >nul 2>&1
  if not errorlevel 1 goto open_browser
  ping -n 2 127.0.0.1 >nul
)

:open_browser
start "" "http://localhost:5173"

endlocal
