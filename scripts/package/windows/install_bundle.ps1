<#!
Install a self-contained Windows x64 core + model bundle.
#>
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$CoreOnly = $false
$VerifyOnly = $false
$NoReload = $false
$UserDir = $env:APPDATA + '\Rime'
for ($i = 0; $i -lt $args.Count; $i++) {
  switch ($args[$i]) {
    '--core-only' { $CoreOnly = $true }
    '--verify-only' { $VerifyOnly = $true }
    '--no-reload' { $NoReload = $true }
    '--user-dir' { $i++; $UserDir = $args[$i] }
    '-h' { Write-Host 'usage: install_bundle.ps1 [--core-only] [--verify-only] [--user-dir PATH] [--no-reload]'; exit 0 }
    '--help' { Write-Host 'usage: install_bundle.ps1 [--core-only] [--verify-only] [--user-dir PATH] [--no-reload]'; exit 0 }
    default { throw "Unknown option: $($args[$i])" }
  }
}

$ManifestPath = Join-Path $Root 'bundle-manifest.json'
$Manifest = Get-Content -Raw $ManifestPath | ConvertFrom-Json
if ($Manifest.platform -ne 'windows' -or $Manifest.model_version -ne 'gu-transformer-ctc-v3') {
  throw 'Bundle platform/model version mismatch'
}
foreach ($entry in $Manifest.files.PSObject.Properties) {
  $path = Join-Path $Root $entry.Name
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Missing bundle file: $($entry.Name)" }
  $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
  if ($actual -ne $entry.Value) { throw "Checksum mismatch: $($entry.Name)" }
}
Write-Host 'BUNDLE_VERIFY_OK'
if ($VerifyOnly) { exit 0 }

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Run this installer as Administrator'
}
$PluginDll = Join-Path $Root 'plugin\rime.dll'
$PayloadRime = Join-Path $Root 'payload\rime'
if (-not (Test-Path $PluginDll) -or -not (Test-Path $PayloadRime)) { throw 'Core payload is incomplete' }

$WeaselRoots = @()
if ($env:ProgramFiles) { $WeaselRoots += (Join-Path $env:ProgramFiles 'Rime') }
$pf86 = [Environment]::GetEnvironmentVariable('ProgramFiles(x86)')
if ($pf86) { $WeaselRoots += (Join-Path $pf86 'Rime') }
$WeaselDir = $null
foreach ($root in $WeaselRoots | Where-Object { $_ -and (Test-Path $_) }) {
  $cand = Get-ChildItem -Path $root -Directory -Filter 'weasel-*' -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -First 1
  if ($cand) { $WeaselDir = $cand.FullName; break }
}
if (-not $WeaselDir) { throw 'Weasel not found under Program Files\Rime' }

Get-Process -Name 'WeaselServer','WeaselDeployer','WeaselTSF' -ErrorAction SilentlyContinue |
  Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
$TargetDll = Join-Path $WeaselDir 'rime.dll'
if (Test-Path $TargetDll) { Copy-Item -Force $TargetDll "$TargetDll.re-gu-trans.bak" }
Copy-Item -Force $PluginDll $TargetDll
Get-ChildItem (Join-Path $Root 'plugin') -Filter '*.dll' | Where-Object Name -ne 'rime.dll' |
  ForEach-Object { Copy-Item -Force $_.FullName (Join-Path $WeaselDir $_.Name) }

New-Item -ItemType Directory -Force -Path (Join-Path $UserDir 'js') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $UserDir 'run') | Out-Null
Copy-Item -Force (Join-Path $PayloadRime 'gujarati.schema.yaml') $UserDir
Get-ChildItem (Join-Path $PayloadRime 'js') -File | Copy-Item -Force -Destination (Join-Path $UserDir 'js')
Copy-Item -Force (Join-Path $PayloadRime 'js\gujarati_translator.js') $UserDir
Copy-Item -Force (Join-Path $PayloadRime 'js\commit_on_punct_processor.js') $UserDir
$Custom = Join-Path $UserDir 'default.custom.yaml'
if (-not (Test-Path $Custom)) {
  "patch:`n  schema_list:`n    - schema: gujarati" | Set-Content -Path $Custom -Encoding UTF8
} elseif (-not (Select-String -Path $Custom -Pattern 'schema: gujarati' -Quiet)) {
  Add-Content -Path $Custom -Value "`npatch:`n  schema_list:`n    - schema: gujarati"
}

if (-not $CoreOnly) {
  $temp = Join-Path $UserDir ('.gujarati-model-install-' + [guid]::NewGuid().ToString('N'))
  $destination = Join-Path $UserDir 'gujarati-model'
  $previous = $null
  try {
    New-Item -ItemType Directory -Force -Path $temp | Out-Null
    Copy-Item -Recurse -Force (Join-Path $Root 'model\*') $temp
    if (Test-Path $destination) {
      $previous = "$destination.previous.$(Get-Date -Format yyyyMMddHHmmssfff)"
      Move-Item -Force $destination $previous
    }
    Move-Item -Force $temp $destination
    $temp = $null
  } catch {
    if ($temp -and (Test-Path $temp)) { Remove-Item -Recurse -Force $temp -ErrorAction SilentlyContinue }
    if ($previous -and (Test-Path $previous) -and -not (Test-Path $destination)) {
      Move-Item -Force $previous $destination -ErrorAction SilentlyContinue
    }
    throw
  }
  Write-Host "Installed verified model at $destination"
}

if (-not $NoReload) {
  $Deployer = Join-Path $WeaselDir 'WeaselDeployer.exe'
  if (Test-Path $Deployer) { Start-Process -FilePath $Deployer -ArgumentList '/deploy' -Wait -ErrorAction SilentlyContinue }
  $Server = Join-Path $WeaselDir 'WeaselServer.exe'
  if (Test-Path $Server) { Start-Process -FilePath $Server -ErrorAction SilentlyContinue }
}
Write-Host 'Done. Select Gujarati Transliteration in Weasel.'
