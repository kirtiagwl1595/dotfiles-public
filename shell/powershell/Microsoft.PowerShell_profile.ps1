# PowerShell profile for Windows (PowerShell 7 and Windows PowerShell 5.1).
# install.py copies it to Documents\PowerShell and, if that folder exists, Documents\WindowsPowerShell.
# Same ideas as shell/zsh/.zshrc. Every tool is optional: a missing tool skips its lines.
# Keep this file ASCII: Windows PowerShell 5.1 reads a file without a BOM as the ANSI code page.

function Test-Tool([string]$Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# PATH: user-level tools (uv, pipx, Claude Code install here)
$localBin = Join-Path $HOME '.local\bin'
if ((Test-Path $localBin) -and ($env:PATH -notlike "*$localBin*")) {
    $env:PATH = "$localBin;$env:PATH"
}

# Editor
if (Test-Tool 'code') { $env:EDITOR = 'code --wait' } else { $env:EDITOR = 'notepad' }
$env:VISUAL = $env:EDITOR

# History search: Up and Down search for what is typed (like zsh-history-substring-search)
if (Get-Module -ListAvailable -Name PSReadLine) {
    Import-Module PSReadLine -ErrorAction SilentlyContinue
    Set-PSReadLineOption -HistorySearchCursorMovesToEnd
    Set-PSReadLineKeyHandler -Key UpArrow -Function HistorySearchBackward
    Set-PSReadLineKeyHandler -Key DownArrow -Function HistorySearchForward
    Set-PSReadLineOption -MaximumHistoryCount 50000
    try {
        # Suggestions from history (PSReadLine 2.1 and later)
        Set-PSReadLineOption -PredictionSource History
    } catch {
        Write-Verbose 'This PSReadLine has no prediction.'
    }
}

# fzf: hidden files yes, .git and big folders no
if (Test-Tool 'fd') {
    $skip = '--exclude .git --exclude .cache --exclude .venv --exclude node_modules'
    $env:FZF_DEFAULT_COMMAND = "fd --type f --hidden $skip"
    $env:FZF_CTRL_T_COMMAND = $env:FZF_DEFAULT_COMMAND
    $env:FZF_ALT_C_COMMAND = "fd --type d --hidden $skip"
}

# Navigation
function .. { Set-Location .. }
function ... { Set-Location ..\.. }
function .... { Set-Location ..\..\.. }
function mkcd {
    param([Parameter(Mandatory = $true)][string]$Path)
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
    Set-Location $Path
}

# Listing (an alias beats a function, so remove the built-in alias first)
if (Test-Tool 'eza') {
    Remove-Item Alias:ls -Force -ErrorAction SilentlyContinue
    function ls { eza --group-directories-first @args }
    function ll { eza -l --git --group-directories-first @args }
    function la { eza -la --git --group-directories-first @args }
    function lt { eza --tree --level=2 @args }
}
if (Test-Tool 'lazygit') { Set-Alias -Name lg -Value lazygit }
if (Test-Tool 'rg') {
    function rg {
        & (Get-Command rg -CommandType Application | Select-Object -First 1) --smart-case @args
    }
}
function gs { git status -sb @args }

# Python: uv only
function venv { uv venv @args }
function act { & .\.venv\Scripts\Activate.ps1 }
function py { uv run python @args }

# Your own lines: put them in $HOME\.profile.local.ps1
$own = Join-Path $HOME '.profile.local.ps1'
if (Test-Path $own) { . $own }

# zoxide (z <folder>) and the starship prompt. Prompt tools go last.
if (Test-Tool 'zoxide') {
    Invoke-Expression (& { (zoxide init powershell | Out-String) })
}
if (Test-Tool 'starship') {
    $env:STARSHIP_LOG = 'error'
    Invoke-Expression (&starship init powershell)
}
