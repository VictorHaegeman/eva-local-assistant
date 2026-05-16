@echo off
setlocal

powershell -NoProfile -Command "$p = Join-Path ([Environment]::GetFolderPath('Startup')) 'Eva Local Assistant.lnk'; if (Test-Path $p) { Remove-Item -LiteralPath $p -Force; Write-Host 'Lancement automatique Eva supprime.' } else { Write-Host 'Aucun raccourci Eva trouve au demarrage.' }"
pause

endlocal
