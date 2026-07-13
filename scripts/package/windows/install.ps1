#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Install re-gu-trans schema + librime-qjs-enabled rime.dll into Weasel.
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PluginDll = Join-Path $Root 'plugin\rime.dll'
$PayloadRime = Join-Path $Root 'payload\rime'

if (-not (Test-Path $PluginDll)) {
  Write-Error "Missing plugin\rime.dll"
}

# Find Weasel install dir
$WeaselRoots = @()
if ($env:ProgramFiles) { $WeaselRoots += (Join-Path $env:ProgramFiles 'Rime') }
$pf86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
if ($pf86) { $WeaselRoots += (Join-Path $pf86 'Rime') }
$WeaselRoots = $WeaselRoots | Where-Object { $_ -and (Test-Path $_) }

$WeaselDir = $null
foreach ($root in $WeaselRoots) {
  $cand = Get-ChildItem -Path $root -Directory -Filter 'weasel-*' -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending |
    Select-Object -First 1
  if ($cand) { $WeaselDir = $cand.FullName; break }
}

if (-not $WeaselDir) {
  Write-Error "Weasel not found under Program Files\Rime. Install Weasel first."
}

Write-Host "Weasel dir: $WeaselDir"

# Stop Weasel processes
Get-Process -Name 'WeaselServer','WeaselDeployer','WeaselTSF' -ErrorAction SilentlyContinue |
  Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1

$TargetDll = Join-Path $WeaselDir 'rime.dll'
if (Test-Path $TargetDll) {
  $bak = "$TargetDll.re-gu-trans.bak"
  if (-not (Test-Path $bak)) {
    Copy-Item -Force $TargetDll $bak
    Write-Host "Backed up rime.dll → $bak"
  }
}

Copy-Item -Force $PluginDll $TargetDll
Get-ChildItem (Join-Path $Root 'plugin') -Filter '*.dll' | ForEach-Object {
  if ($_.Name -ne 'rime.dll') {
    Copy-Item -Force $_.FullName (Join-Path $WeaselDir $_.Name)
  }
}
Write-Host "Installed rime.dll with librime-qjs"

# User Rime data
$RimeUser = Join-Path $env:APPDATA 'Rime'
New-Item -ItemType Directory -Force -Path (Join-Path $RimeUser 'js\lm') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $RimeUser 'run') | Out-Null

Copy-Item -Force (Join-Path $PayloadRime 'gujarati.schema.yaml') $RimeUser
Copy-Item -Force (Join-Path $PayloadRime 'gujarati.dict.yaml') $RimeUser
if (Test-Path (Join-Path $PayloadRime 'gujarati_apple.dict.yaml')) {
  Copy-Item -Force (Join-Path $PayloadRime 'gujarati_apple.dict.yaml') $RimeUser
}
Copy-Item -Force (Join-Path $PayloadRime 'js\*.js') (Join-Path $RimeUser 'js')
Copy-Item -Force (Join-Path $PayloadRime 'js\gu_lexicon_blob.json') (Join-Path $RimeUser 'js')
Copy-Item -Force (Join-Path $PayloadRime 'gu_lexicon_blob.json') $RimeUser -ErrorAction SilentlyContinue
Copy-Item -Force (Join-Path $PayloadRime 'js\lm\*') (Join-Path $RimeUser 'js\lm')
Get-ChildItem (Join-Path $PayloadRime '*.js') -ErrorAction SilentlyContinue | Copy-Item -Force -Destination $RimeUser

$Custom = Join-Path $RimeUser 'default.custom.yaml'
$Snippet = Join-Path $PayloadRime 'default.custom.yaml'
if (-not (Test-Path $Custom)) {
  Copy-Item -Force $Snippet $Custom
} elseif (-not (Select-String -Path $Custom -Pattern 'schema: gujarati' -Quiet)) {
  Add-Content -Path $Custom -Value "`n# re-gu-trans"
  Get-Content $Snippet | Add-Content -Path $Custom
}

$Deployer = Join-Path $WeaselDir 'WeaselDeployer.exe'
if (Test-Path $Deployer) {
  Start-Process -FilePath $Deployer -ArgumentList '/deploy' -Wait -ErrorAction SilentlyContinue
}

$Server = Join-Path $WeaselDir 'WeaselServer.exe'
if (Test-Path $Server) {
  Start-Process -FilePath $Server -ErrorAction SilentlyContinue
}

Write-Host "Done. Select Gujarati Transliteration in Weasel and Deploy if needed."
