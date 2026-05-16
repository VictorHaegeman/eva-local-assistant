@echo off
setlocal EnableExtensions

set "PROJECT_DIR=%~dp0"

if exist "%PROJECT_DIR%open-eva-window.ps1" goto found_project

set "PROJECT_DIR=%USERPROFILE%\Desktop\Cursor\eva-local-assistant\"
if exist "%PROJECT_DIR%open-eva-window.ps1" goto found_project

start "" "http://localhost:5173"
exit /b 0

:found_project
powershell -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_DIR%open-eva-window.ps1"

endlocal
