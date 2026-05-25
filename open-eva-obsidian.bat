@echo off
setlocal

set "EVA_OBSIDIAN_VAULT=%~dp0data\obsidian_vault"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$p=$env:EVA_OBSIDIAN_VAULT;" ^
  "if (!(Test-Path -LiteralPath $p)) { New-Item -ItemType Directory -Force -Path $p | Out-Null };" ^
  "$resolved=(Resolve-Path -LiteralPath $p).Path;" ^
  "$obsDir=Join-Path $env:APPDATA 'obsidian'; New-Item -ItemType Directory -Force -Path $obsDir | Out-Null;" ^
  "$jsonPath=Join-Path $obsDir 'obsidian.json';" ^
  "$raw=@{}; if (Test-Path $jsonPath) { try { $raw=Get-Content $jsonPath -Raw | ConvertFrom-Json } catch { $raw=@{} } };" ^
  "$vaults=@{}; if ($raw.PSObject.Properties.Name -contains 'vaults') { foreach ($prop in $raw.vaults.PSObject.Properties) { $candidatePath=[string]$prop.Value.path; if ($candidatePath.ToLowerInvariant() -ne $resolved.ToLowerInvariant()) { $vaults[$prop.Name]=@{path=$candidatePath; ts=[int64]$prop.Value.ts; open=[bool]$prop.Value.open} } } };" ^
  "$sha=[System.Security.Cryptography.SHA1]::Create(); $bytes=[Text.Encoding]::UTF8.GetBytes($resolved); $hash=($sha.ComputeHash($bytes) | ForEach-Object { $_.ToString('x2') }) -join ''; $vaultId=$hash.Substring(0,16);" ^
  "$vaults[$vaultId]=@{path=$resolved; ts=[DateTimeOffset]::Now.ToUnixTimeMilliseconds(); open=$true};" ^
  "@{vaults=$vaults} | ConvertTo-Json -Depth 8 -Compress | Set-Content -Path $jsonPath -Encoding UTF8;" ^
  "$candidates=@((Join-Path $env:LOCALAPPDATA 'Programs\Obsidian\Obsidian.exe'), (Join-Path $env:ProgramFiles 'Obsidian\Obsidian.exe'), (Join-Path ${env:ProgramFiles(x86)} 'Obsidian\Obsidian.exe'));" ^
  "$obsExe=$candidates | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -First 1;" ^
  "$vaultName=Split-Path $resolved -Leaf; $uri='obsidian://open?vault=' + [uri]::EscapeDataString($vaultName) + '&file=00%20-%20Eva%2FINDEX';" ^
  "if ($obsExe) { Start-Process -FilePath $obsExe -ArgumentList @($resolved) } else { Start-Process $uri };" ^
  "Start-Sleep -Seconds 4;" ^
  "$shell=New-Object -ComObject WScript.Shell; $null=$shell.AppActivate('Obsidian'); Start-Sleep -Milliseconds 500; $shell.SendKeys('^g');"

endlocal
