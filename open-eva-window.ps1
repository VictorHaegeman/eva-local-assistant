param(
    [string]$Url = "http://localhost:5173"
)

$ErrorActionPreference = "Stop"

function Find-AppBrowser {
    $candidates = @()
    if (${env:ProgramFiles(x86)}) {
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Microsoft\Edge\Application\msedge.exe"
        $candidates += Join-Path ${env:ProgramFiles(x86)} "Google\Chrome\Application\chrome.exe"
    }
    if ($env:ProgramFiles) {
        $candidates += Join-Path $env:ProgramFiles "Microsoft\Edge\Application\msedge.exe"
        $candidates += Join-Path $env:ProgramFiles "Google\Chrome\Application\chrome.exe"
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    $edge = Get-Command "msedge.exe" -ErrorAction SilentlyContinue
    if ($edge) {
        return $edge.Source
    }

    $chrome = Get-Command "chrome.exe" -ErrorAction SilentlyContinue
    if ($chrome) {
        return $chrome.Source
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
