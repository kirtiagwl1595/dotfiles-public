# ─────────────────────────────────────────────────────────────────────────────
# zsh config for macOS and Linux. install.py links it to ~/.zshrc.
# Every tool is optional: a missing tool skips its lines.
# ─────────────────────────────────────────────────────────────────────────────
[[ $- != *i* ]] && return

# The clone this file lives in (the link in ~/.zshrc is resolved)
export DOTFILES="${DOTFILES:-${${(%):-%x}:A:h:h:h}}"

# ─────────────────────────────────────────────────────────────────────────────
# 1. Locale, History & Shell Options
# ─────────────────────────────────────────────────────────────────────────────
export LANG=${LANG:-en_US.UTF-8}
(( $+commands[code] )) && export EDITOR="code --wait" || export EDITOR=vi
export VISUAL=$EDITOR
if (( $+commands[bat] )); then
  export MANPAGER="sh -c 'col -bx | bat -l man -p'"
elif (( $+commands[batcat] )); then  # Debian and Ubuntu name it batcat
  export MANPAGER="sh -c 'col -bx | batcat -l man -p'"
fi

HISTFILE=~/.zsh_history
HISTSIZE=50000
SAVEHIST=50000

setopt SHARE_HISTORY HIST_IGNORE_ALL_DUPS EXTENDED_GLOB AUTO_CD
setopt HIST_FIND_NO_DUPS HIST_IGNORE_SPACE HIST_REDUCE_BLANKS HIST_VERIFY INTERACTIVE_COMMENTS  # allow "cmd  # note" at the prompt

# ─────────────────────────────────────────────────────────────────────────────
# 2. PATH (Homebrew comes from .zprofile)
# ─────────────────────────────────────────────────────────────────────────────
typeset -U path
path=($HOME/.local/bin $path)

# ─────────────────────────────────────────────────────────────────────────────
# 3. Completion (cached in ~/.cache/zsh, rebuilt at most once a day)
# ─────────────────────────────────────────────────────────────────────────────
# Where Homebrew (macOS or Linux) or the system package manager puts shell add-ons
for HB in ${HOMEBREW_PREFIX:-} /opt/homebrew /home/linuxbrew/.linuxbrew /usr/local /usr; do
  [[ -n $HB && -d $HB/share ]] && break
done
typeset -U fpath
fpath=($HB/share/zsh/site-functions $fpath)
[[ -d ~/.cache/zsh ]] || mkdir -p ~/.cache/zsh
autoload -Uz compinit
if [[ -n ~/.cache/zsh/zcompdump(#qN.mh+24) || ! -f ~/.cache/zsh/zcompdump ]]; then
  compinit -d ~/.cache/zsh/zcompdump
else
  compinit -C -d ~/.cache/zsh/zcompdump
fi
zstyle ':completion:*' matcher-list 'm:{a-z}={A-Z}'
zstyle ':completion:*' menu select
zstyle ':completion:*' group-name ''
zstyle ':completion:*' list-colors ''

# ─────────────────────────────────────────────────────────────────────────────
# 4. Tools
# ─────────────────────────────────────────────────────────────────────────────
# Init scripts are cached in ~/.cache/zsh and made again when the tool is newer (an upgrade).
# fnm is not cached: its output names a new folder for each shell.
_cached() {  # _cached <name> <command...>
  local f=~/.cache/zsh/$1.zsh bin=${commands[$2]}; shift
  [[ -n $bin ]] || return 0
  [[ -s $f && $f -nt $bin ]] || "$@" >| $f
  source $f
}
_cached fzf    fzf --zsh                       # Ctrl+R, Ctrl+T
_cached zoxide zoxide init zsh                 # z <folder>
_cached uv     uv generate-shell-completion zsh
path=(${path:#*/fnm_multishells/*})  # a nested shell inherits the parent's fnm folder: drop it
command -v fnm >/dev/null && eval "$(fnm env --use-on-cd --shell zsh)"
_fd=${commands[fd]:+fd}; _fd=${_fd:-${commands[fdfind]:+fdfind}}  # Debian and Ubuntu name it fdfind
if [[ -n $_fd ]]; then  # fzf: hidden files yes, .git and gitignored files no
  _fd_skip='--exclude .git --exclude .cache --exclude .venv --exclude node_modules --exclude Library --exclude .Trash'
  export FZF_DEFAULT_COMMAND="$_fd --type f --hidden $_fd_skip"
  export FZF_CTRL_T_COMMAND=$FZF_DEFAULT_COMMAND
  export FZF_ALT_C_COMMAND="$_fd --type d --hidden $_fd_skip"
  unset _fd_skip
fi
unset _fd
if (( $+commands[bat] )); then
  export FZF_CTRL_T_OPTS="--preview 'bat --color=always --style=numbers --line-range=:200 {}'"
fi

# ─────────────────────────────────────────────────────────────────────────────
# 5. Aliases
# ─────────────────────────────────────────────────────────────────────────────
alias ..='cd ..'
alias ...='cd ../..'
alias ....='cd ../../..'

if command -v eza >/dev/null; then
  alias ls='eza --group-directories-first'
  alias ll='eza -l --git --group-directories-first'
  alias la='eza -la --git --group-directories-first'
  alias lt='eza --tree --level=2'
fi
if command -v bat >/dev/null; then
  alias cat='bat --paging=never --style=plain'
elif command -v batcat >/dev/null; then
  alias bat=batcat
  alias cat='batcat --paging=never --style=plain'
fi
command -v lazygit >/dev/null && alias lg=lazygit
command -v rg >/dev/null && alias rg='rg --smart-case'
alias gs='git status -sb'

# Python: uv only
alias venv='uv venv'
alias act='source .venv/bin/activate'
alias py='uv run python'

# ─────────────────────────────────────────────────────────────────────────────
# 6. Functions
# ─────────────────────────────────────────────────────────────────────────────
brewup() {
  command -v brew >/dev/null || { echo "brew is not installed"; return 1; }
  brew update && brew outdated && brew upgrade && brew autoremove && brew cleanup && brew doctor
}
# Try a package and keep it: your own lists are untracked files in packages/ (see packages/pkgs.py)
pkgadd()    { python3 "$DOTFILES/install.py" pkg add "$@"; }
pkgkeep()   { python3 "$DOTFILES/install.py" pkg keep "$@"; }
pkgtrials() { python3 "$DOTFILES/install.py" pkg list; }

update_all() {
  if [[ $OSTYPE == darwin* ]]; then
    echo "→ macOS";      sudo softwareupdate --install --all
  elif command -v apt-get >/dev/null; then
    echo "→ apt";        sudo apt-get update && sudo apt-get upgrade -y
  fi
  command -v brew >/dev/null && { echo "→ Homebrew"; brewup; }
  command -v uv >/dev/null && { echo "→ uv tools"; uv tool upgrade --all; }
  echo "Done."
}

# New Python project with its own .venv and a Jupyter kernel named after it
newproj() {
  local dir=${1:-.}
  mkdir -p "$dir" && cd "$dir" || return 1
  local name=${PWD:t}
  uv init --quiet --app --no-package --python 3.12 && uv add --dev ipykernel ruff pytest \
    && cat "$DOTFILES/claude/templates/pyproject-pytest.toml" >> pyproject.toml \
    && uv run python -m ipykernel install --user --name "$name" --display-name "Python ($name)"
}

# Parallel agents: Claude in its own git worktree + branch, so 2-3 agents never clash.
# First time in a repo: run `claude` there once and accept the trust question.
cw() { claude --worktree "${1:?usage: cw <task-name>}"; }

# API keys live in the system keychain, never in .env or git. Claude's hooks block reading them.
#   secret set NAME | secret get NAME | secret list | secret rm NAME
#   withsecret NAME [NAME…] -- command   (runs command with those env vars set)
# macOS: Keychain (security). Linux: the Secret Service (secret-tool, package libsecret-tools).
secret() {
  if [[ $OSTYPE == darwin* ]]; then
    case $1 in
      # -w last with no value: security asks for it, so the key is never on the command line (ps)
      set)  security add-generic-password -U -a "$USER" -s "${2:?usage: secret set NAME}" -D dotfiles-secret -w ;;
      get)  security find-generic-password -a "$USER" -s "$2" -w ;;
      rm)   security delete-generic-password -a "$USER" -s "$2" >/dev/null && echo "removed $2" ;;
      list) security dump-keychain 2>/dev/null | grep -A14 '"desc"<blob>="dotfiles-secret"' | sed -n 's/.*"svce"<blob>="\(.*\)"/\1/p' ;;
      *)    echo "usage: secret set|get|rm NAME, secret list"; return 1 ;;
    esac
  else
    command -v secret-tool >/dev/null || { echo "secret-tool is missing: sudo apt install libsecret-tools"; return 1; }
    case $1 in
      set)  secret-tool store --label "${2:?usage: secret set NAME}" service dotfiles-secret name "$2" ;;
      get)  secret-tool lookup service dotfiles-secret name "$2" ;;
      rm)   secret-tool clear service dotfiles-secret name "$2" && echo "removed $2" ;;
      list) secret-tool search --all service dotfiles-secret 2>/dev/null | sed -n 's/^attribute.name = //p' ;;
      *)    echo "usage: secret set|get|rm NAME, secret list"; return 1 ;;
    esac
  fi
}
withsecret() {
  local names=() n v
  while [[ $# -gt 0 && $1 != -- ]]; do names+=$1; shift; done
  [[ $1 == -- && $# -gt 1 ]] || { echo "usage: withsecret NAME [NAME…] -- command"; return 1; }
  shift
  # A subshell: the keys reach only this command, not your open shell
  (
    for n in $names; do v=$(secret get "$n") || exit 1; export "$n=$v"; done
    "$@"
  )
}

mkcd() { mkdir -p "${1:?usage: mkcd <folder>}" && cd "$1"; }

extract() {
  [[ -f $1 ]] || { echo "'$1' not found"; return 1 }
  case $1 in
    *.tar.bz2|*.tbz2)        tar xvjf "$1" ;;
    *.tar.gz|*.tgz|*.tar.xz|*.tar.zst|*.tar) tar xvf "$1" ;;
    *.bz2)                   bunzip2 "$1"  ;;
    *.zip)                   unzip "$1"    ;;
    *.7z)                    7zz x "$1"    ;;
    *.gz)                    gunzip "$1"   ;;
    *.Z)                     uncompress "$1" ;;
    *)         echo "Cannot extract '$1'"; return 1 ;;
  esac
}

# ─────────────────────────────────────────────────────────────────────────────
# 7. Your own lines: put them in ~/.zshrc.local, or in ~/.zshrc itself (install.py adds only
#    a marked block there that sources this file; the rest of ~/.zshrc stays yours)
# ─────────────────────────────────────────────────────────────────────────────
[[ -f ~/.zshrc.local ]] && source ~/.zshrc.local

# ─────────────────────────────────────────────────────────────────────────────
# 8. Plugins (syntax highlighting, then history substring search, its required order) & Prompt
# ─────────────────────────────────────────────────────────────────────────────
for plugin in zsh-autosuggestions zsh-syntax-highlighting zsh-history-substring-search; do
  for dir in $HB/share/$plugin /usr/share/$plugin; do  # Homebrew, then Debian and Ubuntu
    [[ -f $dir/$plugin.zsh ]] && { source $dir/$plugin.zsh; break }
  done
done
unset plugin dir
if (( $+widgets[history-substring-search-up] )); then  # Up/Down: search history for what is typed
  bindkey '^[[A' history-substring-search-up '^[OA' history-substring-search-up
  bindkey '^[[B' history-substring-search-down '^[OB' history-substring-search-down
fi

export STARSHIP_LOG=error  # no scan-timeout warnings on slow folders (network drives)
_cached starship starship init zsh
