@echo off
setlocal

echo Stopping Eva services on ports 8000 and 5173...
echo.

for %%P in (8000 5173) do (
  echo Checking port %%P...
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr /R /C:":%%P .*LISTENING"') do (
    echo Stopping PID %%A on port %%P
    taskkill /PID %%A /F >nul 2>&1
  )
)

echo.
echo Done.
timeout /t 2 /nobreak >nul

endlocal
