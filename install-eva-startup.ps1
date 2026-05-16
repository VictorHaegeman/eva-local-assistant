$ErrorActionPreference = "Stop"

function Resolve-EvaProjectDir {
    $scriptDir = $PSScriptRoot
    if (Test-Path (Join-Path $scriptDir "start-eva-background.bat")) {
        return (Resolve-Path $scriptDir).Path
    }

    $fallback = Join-Path $env:USERPROFILE "Desktop\Cursor\eva-local-assistant"
    if (Test-Path (Join-Path $fallback "start-eva-background.bat")) {
        return (Resolve-Path $fallback).Path
    }

    throw "Projet Eva introuvable."
}

$projectDir = Resolve-EvaProjectDir
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "Eva Local Assistant.lnk"
$targetPath = Join-Path $projectDir "start-eva-background.bat"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $targetPath
$shortcut.WorkingDirectory = $projectDir
$shortcut.WindowStyle = 7
$shortcut.Description = "Lance Eva en arriere-plan au demarrage Windows."
$shortcut.Save()

Write-Host "Eva sera lancee automatiquement a la prochaine ouverture de session Windows."
Write-Host "Raccourci cree: $shortcutPath"
