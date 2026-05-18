param(
    [string]$Url = "http://localhost:5173"
)

$ErrorActionPreference = "Stop"

function Find-AppBrowser {
    $candidates = @()
    if ($env:LOCALAPPDATA) {
        $candidates += Join-Path $env:LOCALAPPDATA "BraveSoftware\Brave-Browser\Application\brave.exe"
    }
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "BraveSoftware\Brave-Browser\Application\brave.exe"
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "BraveSoftware\Brave-Browser\Application\brave.exe"
    }
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"
        $candidates += Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe"
    }
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"
    }

    $brave = Get-Command "brave.exe" -ErrorAction SilentlyContinue
    if ($brave) {
        $candidates += $brave.Source
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    $chrome = Get-Command "chrome.exe" -ErrorAction SilentlyContinue
    if ($chrome) {
        return $chrome.Source
    }

    $edge = Get-Command "msedge.exe" -ErrorAction SilentlyContinue
    if ($edge) {
        return $edge.Source
    }

    return $null
}

$browser = Find-AppBrowser

if ($browser) {
    Start-Process `
        -FilePath $browser `
        -ArgumentList @(
            "--app=$Url",
            "--new-window",
            "--window-size=1320,900",
            "--window-position=80,40"
        )
    exit 0
}

Start-Process $Url
