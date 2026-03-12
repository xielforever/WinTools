param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [switch]$SkipDependencyInstall
)

$ErrorActionPreference = "Stop"

if ($Version -notmatch '^v\d+\.\d+\.\d+$') {
    throw "Version must match vMAJOR.MINOR.PATCH, e.g. v0.1.0"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$versionCore = $Version.Substring(1)
$distRoot = Join-Path $repoRoot "dist"
$buildRoot = Join-Path $repoRoot "build"
$specRoot = Join-Path $buildRoot "spec"
$versionFile = Join-Path $repoRoot "wintools\_build_version.py"

$onedirDist = Join-Path $distRoot "onedir"
$onefileDist = Join-Path $distRoot "onefile"
$onedirApp = Join-Path $onedirDist "WinTools"
$zipArtifact = Join-Path $distRoot "WinTools-$Version-windows-onedir.zip"
$exeArtifact = Join-Path $distRoot "WinTools-$Version-windows-onefile.exe"

Write-Host "[build] Preparing clean output directories..."
if (Test-Path $distRoot) { Remove-Item -Recurse -Force $distRoot }
if (Test-Path $buildRoot) { Remove-Item -Recurse -Force $buildRoot }
New-Item -ItemType Directory -Force $distRoot | Out-Null
New-Item -ItemType Directory -Force $specRoot | Out-Null

$versionContent = "VERSION = '$versionCore'`n"
Set-Content -Path $versionFile -Value $versionContent -Encoding utf8

try {
    if (-not $SkipDependencyInstall) {
        Write-Host "[build] Installing build dependencies..."
        python -m pip install --upgrade pip
        python -m pip install pyinstaller
    }

    Write-Host "[build] Building one-directory package..."
    python -m PyInstaller --noconfirm --clean --windowed --name WinTools --distpath $onedirDist --workpath (Join-Path $buildRoot "onedir") --specpath $specRoot main.py

    if (-not (Test-Path $onedirApp)) {
        throw "OneDir app folder was not created: $onedirApp"
    }

    Write-Host "[build] Creating OneDir ZIP artifact..."
    Compress-Archive -Path $onedirApp -DestinationPath $zipArtifact -Force

    Write-Host "[build] Building one-file package..."
    python -m PyInstaller --noconfirm --clean --windowed --onefile --name WinTools --distpath $onefileDist --workpath (Join-Path $buildRoot "onefile") --specpath $specRoot main.py

    $onefileExe = Join-Path $onefileDist "WinTools.exe"
    if (-not (Test-Path $onefileExe)) {
        throw "OneFile executable was not created: $onefileExe"
    }

    Move-Item -Force $onefileExe $exeArtifact

    Write-Host "[build] Artifacts ready:"
    Write-Host "  - $zipArtifact"
    Write-Host "  - $exeArtifact"
}
finally {
    if (Test-Path $versionFile) {
        Remove-Item -Force $versionFile
    }
}

