param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

function Resolve-EvaProjectDir {
    $scriptDir = $PSScriptRoot
    if (Test-Path (Join-Path $scriptDir "backend\app\main.py")) {
        return (Resolve-Path $scriptDir).Path
    }

    $fallback = Join-Path $env:USERPROFILE "Desktop\Cursor\eva-local-assistant"
    if (Test-Path (Join-Path $fallback "backend\app\main.py")) {
        return (Resolve-Path $fallback).Path
    }

    throw "Projet Eva introuvable. Place ce script dans la racine du projet ou garde le repo dans Desktop\Cursor\eva-local-assistant."
}

function Test-LocalPort {
    param([int]$Port)

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $connect = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        $ready = $connect.AsyncWaitHandle.WaitOne(500)
        if ($ready) {
            $client.EndConnect($connect)
            $client.Close()
            return $true
        }

        $client.Close()
        return $false
    }
    catch {
        return $false
    }
}

$projectDir = Resolve-EvaProjectDir
$backendDir = Join-Path $projectDir "backend"
$frontendDir = Join-Path $projectDir "frontend"
$logsDir = Join-Path $projectDir "logs"

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null

$python = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

if (-not (Test-LocalPort -Port 8000)) {
    Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload") `
        -WorkingDirectory $backendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logsDir "backend.out.log") `
        -RedirectStandardError (Join-Path $logsDir "backend.err.log")
}

if (-not (Test-LocalPort -Port 5173)) {
    Start-Process `
        -FilePath "cmd.exe" `
        -ArgumentList @("/c", "npm run dev -- --host 0.0.0.0") `
        -WorkingDirectory $frontendDir `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logsDir "frontend.out.log") `
        -RedirectStandardError (Join-Path $logsDir "frontend.err.log")
}

for ($attempt = 1; $attempt -le 20; $attempt++) {
    if ((Test-LocalPort -Port 5173) -and (Test-LocalPort -Port 8000)) {
        break
    }

    Start-Sleep -Seconds 1
}

if (-not $NoBrowser) {
    Start-Process "http://localhost:5173"
}

Write-Host "Eva est lancee depuis $projectDir"
Write-Host "Logs: $logsDir"
