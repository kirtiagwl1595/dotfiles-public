#!/usr/bin/env bash
# User-level macOS settings (idea from mathiasbynens/dotfiles .macos). No sudo.
# install.py runs it on macOS only, after a question. Safe to run again.
# It saves each domain first (defaults export). Undo: defaults import <domain> <saved .plist>,
# then: killall Finder Dock SystemUIServer. (defaults delete gives Apple's value, not yours.)
# Needs the Claude Code sandbox off: defaults writes ~/Library/Preferences and killall signals other apps.
# Run by hand: DOTFILES_MACOS_OK=1 scripts/macos-defaults.sh
set -euo pipefail

if [[ ${DOTFILES_MACOS_OK:-} != 1 ]]; then
  echo "Run this through python3 install.py --only macos (it asks first), or set DOTFILES_MACOS_OK=1." >&2
  exit 1
fi

SAVED="$HOME/.dotfiles-backup/macos-defaults-$(date +%Y-%m-%d-%H%M%S)"
mkdir -p "$SAVED"
for domain in NSGlobalDomain com.apple.finder com.apple.desktopservices com.apple.screencapture com.apple.dock; do
  defaults export "$domain" "$SAVED/$domain.plist"
done
echo "Saved your current values in $SAVED (undo: defaults import <domain> $SAVED/<domain>.plist)."

# Finder: show file extensions, path bar, status bar; search the current folder
defaults write NSGlobalDomain AppleShowAllExtensions -bool true
defaults write com.apple.finder ShowPathbar -bool true
defaults write com.apple.finder ShowStatusBar -bool true
defaults write com.apple.finder FXDefaultSearchScope -string SCcf
# Finder: folders first, list view, no warning when an extension changes
defaults write com.apple.finder _FXSortFoldersFirst -bool true
defaults write com.apple.finder FXPreferredViewStyle -string Nlsv
defaults write com.apple.finder FXEnableExtensionChangeWarning -bool false
# Save dialogs open expanded
defaults write NSGlobalDomain NSNavPanelExpandedStateForSaveMode -bool true
# No .DS_Store files on network and USB drives
defaults write com.apple.desktopservices DSDontWriteNetworkStores -bool true
defaults write com.apple.desktopservices DSDontWriteUSBStores -bool true

# Keyboard: fast key repeat, no press-and-hold accent menu, no auto-correct of quotes
defaults write NSGlobalDomain KeyRepeat -int 2
defaults write NSGlobalDomain InitialKeyRepeat -int 15
defaults write NSGlobalDomain ApplePressAndHoldEnabled -bool false
defaults write NSGlobalDomain NSAutomaticQuoteSubstitutionEnabled -bool false
defaults write NSGlobalDomain NSAutomaticDashSubstitutionEnabled -bool false

# Screenshots in their own folder, as PNG
mkdir -p "$HOME/Pictures/Screenshots"
defaults write com.apple.screencapture location -string "$HOME/Pictures/Screenshots"
defaults write com.apple.screencapture type -string png

# Dock: hide automatically
defaults write com.apple.dock autohide -bool true
defaults write com.apple.dock show-recents -bool false

killall Finder Dock SystemUIServer 2>/dev/null || true
echo "macOS defaults set. Key repeat needs a log out and log in."
