# Windows equivalent of build_layer.sh - see that file for why Docker isn't needed.
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$buildDir = Join-Path $here "build"
$pyVersion = "3.12"
$platform = "manylinux2014_x86_64"
$pillowVersion = "11.3.0"

Write-Host "==> Rebuilding Pillow layer (Pillow $pillowVersion, py$pyVersion, $platform)"
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
New-Item -ItemType Directory -Force -Path (Join-Path $buildDir "python") | Out-Null

python -m pip install --quiet --platform $platform --implementation cp `
  --python-version $pyVersion --only-binary=:all: `
  --target (Join-Path $buildDir "python") "Pillow==$pillowVersion"
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Get-ChildItem (Join-Path $buildDir "python") -Recurse -Directory -Filter "__pycache__" |
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$linuxSo = Get-ChildItem (Join-Path $buildDir "python\PIL") -Filter "*x86_64-linux-gnu.so" -ErrorAction SilentlyContinue
if (-not $linuxSo) { throw "Layer does not contain Linux binaries - refusing to continue." }

$mb = [math]::Round(((Get-ChildItem $buildDir -Recurse | Measure-Object Length -Sum).Sum / 1MB), 1)
Write-Host "==> Layer ready: $buildDir ($mb MB)"
