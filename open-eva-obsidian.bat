@echo off
setlocal

set "EVA_OBSIDIAN_VAULT=%~dp0data\obsidian_vault"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p=$env:EVA_OBSIDIAN_VAULT; if (!(Test-Path -LiteralPath $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null }; $resolved=(Resolve-Path -LiteralPath $p).Path; Start-Process ('obsidian://open?path=' + [uri]::EscapeDataString($resolved))"

