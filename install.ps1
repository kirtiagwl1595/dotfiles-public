# Start install.py with a working Python 3.9+ on Windows (PowerShell 5.1 or 7).
# If PowerShell blocks scripts, use install.cmd: it starts this file with -ExecutionPolicy Bypass.
#
#   .\install.ps1 --check   shows what would change; changes nothing
#   .\install.ps1           makes the changes; asks before each one
#
# No Python 3.9+: it asks, then installs one with winget.
# `python` and `python3` are often the Microsoft Store stub: the version check skips them.

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
    foreach ($candidate in @(@('py', '-3'), @('python'), @('python3'))) {
        $exe = $candidate[0]
        $pre = @($candidate | Select-Object -Skip 1)
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        try {
            & $exe @pre -c 'import sys; sys.exit(sys.version_info < (3, 9))' *> $null
            if ($LASTEXITCODE -eq 0) { return , $candidate }
        } catch {
            continue
        }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host 'install.ps1 needs Python 3.9 or later, and found none.'
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Host 'Install Python 3 from python.org, then run install.ps1 again.'
        exit 1
    }
    $answer = Read-Host '  Install it now with: winget install --id Python.Python.3.12 -e ? [y/N]'
    if ($answer -notmatch '^(y|yes)$') {
        Write-Host 'Install Python 3, then run install.ps1 again.'
        exit 1
    }
    & winget install --id Python.Python.3.12 -e
    if ($LASTEXITCODE -ne 0) {
        Write-Host "The Python install failed. Exit code $LASTEXITCODE."
        exit 1
    }
    Write-Host 'Python is installed. Open a new terminal, then run install.ps1 again.'
    exit 0
}

$exe = $py[0]
$pre = @($py | Select-Object -Skip 1)
& $exe @pre (Join-Path $here 'install.py') @args
exit $LASTEXITCODE
