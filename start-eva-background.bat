@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"

if exist "%PROJECT_DIR%start-eva-background.ps1" goto found_project

set "PROJECT_DIR=%USERPROFILE%\Desktop\Cursor\eva-local-assistant\"
if exist "%PROJECT_DIR%start-eva-background.ps1" goto found_project

echo [Eva] Impossible de trouver start-eva-background.ps1.
echo.
pause
exit /b 1

:found_project
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%start-eva-background.ps1"

endlocal
