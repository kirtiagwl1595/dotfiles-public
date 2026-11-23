# Apache Jena on Windows: download the official zip, check its SHA-512, unpack it under
# %LOCALAPPDATA%, and tell you which folder to put on PATH. Java: Temurin, through winget, after your yes.
# Usage: .\install-jena.ps1 [-DryRun] [-Version X.Y.Z]
# Undo: delete %LOCALAPPDATA%\jena-<version>, and the PATH entry if you added one.
param(
    [switch]$DryRun,
    [string]$Version = '6.2.0'
)
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    Write-Host 'Usage: install-jena.ps1 [-DryRun] [-Version X.Y.Z]'
    exit 2
}
$name = "apache-jena-$Version"
$url = "https://archive.apache.org/dist/jena/binaries/$name.zip"
$dest = Join-Path $env:LOCALAPPDATA "jena-$Version"

if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    $cmd = 'winget install --id EclipseAdoptium.Temurin.21.JDK --exact --accept-package-agreements --accept-source-agreements'
    if ($DryRun) {
        Write-Host "Dry run: no Java found; would ask to run: $cmd"
    } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
        $answer = Read-Host "  No Java found. Install Temurin with: $cmd ? [y/N]"
        if ($answer -notmatch '^(y|yes)$') { Write-Host 'Install a JDK, then run this script again.'; exit 1 }
        Invoke-Expression $cmd
        Write-Host 'Open a new terminal so that PATH sees Java, then run this script again.'
        exit 0
    } else {
        Write-Host 'No Java found, and no winget. Install a JDK, then run this script again.'
        exit 1
    }
}

if ($DryRun) {
    Write-Host "Dry run: would download $url"
    Write-Host "Dry run: would unpack into $dest"
    exit 0
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("install-jena-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    $zip = Join-Path $tmp 'jena.zip'
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    $want = ((Invoke-WebRequest -Uri "$url.sha512" -UseBasicParsing).Content.ToString().Trim() -split '\s+')[0]
    $have = (Get-FileHash -Algorithm SHA512 -Path $zip).Hash
    if ($want.ToLower() -ne $have.ToLower()) {
        Write-Host 'Checksum mismatch: nothing installed.'
        exit 1
    }
    Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp 'stage')
    $inner = Join-Path (Join-Path $tmp 'stage') $name
    if (-not (Test-Path (Join-Path $inner 'bat'))) {
        Write-Host "Unpack failed: no bat folder in $name. Nothing installed."
        exit 1
    }
    if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
    Move-Item -Path $inner -Destination $dest
} finally {
    Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
}
Write-Host "Installed Jena $Version in $dest"
Write-Host "Add this folder to your user PATH to run riot, sparql and arq: $(Join-Path $dest 'bat')"
