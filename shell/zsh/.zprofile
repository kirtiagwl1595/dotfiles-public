# Login shell: Homebrew environment (runs once per login, before .zshrc).
# macOS (Apple Silicon or Intel) and Linuxbrew; a system without Homebrew skips it.
for _brew in /opt/homebrew/bin/brew /usr/local/bin/brew /home/linuxbrew/.linuxbrew/bin/brew; do
  [[ -x $_brew ]] && { eval "$($_brew shellenv)"; break }
done
unset _brew

# Your own login lines (company proxy, extra PATH, ...)
[[ -f ~/.zprofile.local ]] && source ~/.zprofile.local

export HOMEBREW_NO_ANALYTICS=1
export HOMEBREW_NO_ENV_HINTS=1
export HOMEBREW_CLEANUP_PERIODIC_FULL_DAYS=7
