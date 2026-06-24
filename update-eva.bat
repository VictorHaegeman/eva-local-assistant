@echo off
setlocal EnableExtensions

rem === Met a jour Eva depuis GitHub puis la relance ===
rem Recupere le dernier code de la branche, installe les dependances backend,
rem puis lance Eva. Ton fichier backend\.env (avec ta cle) n'est jamais touche.

set "PROJECT_DIR=%~dp0"

if exist "%PROJECT_DIR%backend\app\main.py" goto found_project

set "PROJECT_DIR=%USERPROFILE%\Desktop\Cursor\eva-local-assistant\"
if exist "%PROJECT_DIR%backend\app\main.py" goto found_project

echo [Eva] Impossible de trouver le projet Eva.
echo Place ce fichier .bat dans la racine du projet eva-local-assistant.
echo.
pause
exit /b 1

:found_project
for %%I in ("%PROJECT_DIR%.") do set "PROJECT_DIR=%%~fI\"
set "BRANCH=claude/eva-autonomy-improvements-bpq4ly"

echo ============================================================
echo  Mise a jour d'Eva depuis GitHub (branche %BRANCH%)
echo ============================================================
echo.

cd /d "%PROJECT_DIR%"

echo [1/4] Recuperation du code...
git fetch origin
if errorlevel 1 (
  echo [Eva] git fetch a echoue. Verifie ta connexion ou l'installation de Git.
  pause
  exit /b 1
)

echo [2/4] Passage sur la branche...
git checkout %BRANCH%
git pull origin %BRANCH%
if errorlevel 1 (
  echo [Eva] git pull a echoue. Si tu as des modifications locales, note-les puis relance.
  pause
  exit /b 1
)

echo [3/4] Installation des dependances backend...
set "BACKEND_PY=python"
if exist "%PROJECT_DIR%backend\.venv\Scripts\python.exe" (
  set "BACKEND_PY=%PROJECT_DIR%backend\.venv\Scripts\python.exe"
)
"%BACKEND_PY%" -m pip install -q -r "%PROJECT_DIR%backend\requirements.txt"

echo [4/4] Lancement d'Eva...
if exist "%PROJECT_DIR%start-eva.bat" (
  call "%PROJECT_DIR%start-eva.bat"
) else (
  echo [Eva] start-eva.bat introuvable. Lance Eva manuellement.
  pause
)

endlocal
