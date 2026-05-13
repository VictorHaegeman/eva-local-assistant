@echo off
setlocal

set "PROJECT_DIR=%~dp0"

echo Starting Eva from:
echo %PROJECT_DIR%
echo.

start "Eva Backend" cmd /k "cd /d ""%PROJECT_DIR%backend"" && if exist "".venv\Scripts\activate.bat"" call "".venv\Scripts\activate.bat"" && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

start "Eva Frontend" cmd /k "cd /d ""%PROJECT_DIR%frontend"" && npm run dev -- --host 0.0.0.0"

echo Waiting for Eva to start...
timeout /t 5 /nobreak >nul

start "" "http://localhost:5173"

endlocal
