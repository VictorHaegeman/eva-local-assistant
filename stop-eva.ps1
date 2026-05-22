param(
    [int[]]$Ports = @(8000, 5173),
    [switch]$Quiet
)

$ErrorActionPreference = "SilentlyContinue"

function Write-EvaLog {
    param([string]$Message)

    if (-not $Quiet) {
        Write-Host $Message
    }
}

function Stop-ProcessTreeById {
    param([int]$ProcessId)

    if (-not $ProcessId) {
        return
    }

    $children = Get-CimInstance Win32_Process |
        Where-Object { $_.ParentProcessId -eq $ProcessId }

    foreach ($child in $children) {
        Stop-ProcessTreeById -ProcessId ([int]$child.ProcessId)
    }

    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Stop-UvicornReloadChildren {
    param([int[]]$ParentPids)

    foreach ($parentPid in $ParentPids) {
        $pattern = "spawn_main\(parent_pid=$parentPid,"
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -match "^python" -and
                $_.CommandLine -match $pattern
            } |
            ForEach-Object {
                Write-EvaLog "Stopping orphan backend child PID $($_.ProcessId)"
                Stop-ProcessTreeById -ProcessId ([int]$_.ProcessId)
            }
    }
}

Write-EvaLog "Stopping Eva services on ports $($Ports -join ', ')..."

$listeners = Get-NetTCPConnection -LocalPort $Ports -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    Where-Object { $_ -and $_ -gt 0 }

Stop-UvicornReloadChildren -ParentPids $listeners

foreach ($listenerPid in $listeners) {
    Write-EvaLog "Stopping listener PID $listenerPid"
    Stop-ProcessTreeById -ProcessId ([int]$listenerPid)
}

Start-Sleep -Milliseconds 700

$remaining = Get-NetTCPConnection -LocalPort $Ports -State Listen -ErrorAction SilentlyContinue
if ($remaining) {
    $remainingPids = $remaining |
        Select-Object -ExpandProperty OwningProcess -Unique |
        Where-Object { $_ -and $_ -gt 0 }

    Stop-UvicornReloadChildren -ParentPids $remainingPids

    foreach ($remainingPid in $remainingPids) {
        Write-EvaLog "Stopping remaining listener PID $remainingPid"
        Stop-ProcessTreeById -ProcessId ([int]$remainingPid)
    }
}

Write-EvaLog "Eva ports stopped."
