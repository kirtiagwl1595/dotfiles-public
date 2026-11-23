#!/usr/bin/env bash
# Notification + Stop: a desktop banner, so long agent runs need no watching.
# macOS: osascript. Linux: notify-send when it exists. Windows (Git Bash): a PowerShell toast.
# No tool, no banner, no error: this hook never fails.
# Stop hooks run in parallel: the Stop banner can show while a gate (test_gate,
# lesson_gate) blocks the same Stop. That is by design; this hook does not wait for them.
# Notification (Claude waits for you): always. Stop (Claude finished): only when
# the terminal/editor is not the front app (macOS; elsewhere always).
# NOTIFY_DRY_RUN=1 prints the banner text instead of showing it.
. "$(dirname "${BASH_SOURCE[0]}")/_py.sh"
input=$(cat)
IFS=$'\x1f' read -r cwd event active message < <(pyrun -c '
import json, sys
d = json.loads(sys.argv[1])
keys = ("cwd", "hook_event_name", "stop_hook_active", "message")
print("\x1f".join(str(d.get(k) or "").replace("\n", " ") for k in keys))
' "$input") || exit 0

project=$(basename "${cwd:-session}")
os=$(uname -s 2>/dev/null)
if [[ $event == Stop ]]; then
  [[ $active == True ]] && exit 0
  if [[ $os == Darwin || -n ${NOTIFY_FRONT_APP:-} ]]; then
    front=${NOTIFY_FRONT_APP:-$(lsappinfo info -only name "$(lsappinfo front)" 2>/dev/null)}
    [[ $front =~ iTerm|Terminal|Code|Claude ]] && exit 0
  fi
  msg="Claude finished"
else
  msg=$message
  msg=${msg:-Claude needs you}
fi
title="Claude Code · ${project:-session}"

if [[ -n ${NOTIFY_DRY_RUN:-} ]]; then
  echo "$title: $msg"
  exit 0
fi
case $os in
Darwin)
  # AppleScript strings: drop the " and \ characters that would end or escape the string
  msg=${msg//\\/}
  title=${title//\\/}
  osascript -e "display notification \"${msg//\"/}\" with title \"${title//\"/}\" sound name \"Glass\"" >/dev/null 2>&1 || true
  ;;
Linux)
  command -v notify-send >/dev/null 2>&1 && { notify-send "$title" "$msg" >/dev/null 2>&1 || true; }
  ;;
MINGW* | MSYS* | CYGWIN*)
  # The text goes in through the environment, never into the script: no quoting to break
  if command -v powershell.exe >/dev/null 2>&1; then
    NOTIFY_TITLE=$title NOTIFY_MSG=$msg powershell.exe -NoProfile -NonInteractive -Command '
      Add-Type -AssemblyName System.Windows.Forms
      $n = New-Object System.Windows.Forms.NotifyIcon
      $n.Icon = [System.Drawing.SystemIcons]::Information
      $n.Visible = $true
      $n.ShowBalloonTip(5000, $env:NOTIFY_TITLE, $env:NOTIFY_MSG, "Info")
      Start-Sleep -Seconds 6
      $n.Dispose()' >/dev/null 2>&1 &
    disown 2>/dev/null || true # the toast lives on in the background; the hook returns at once
  fi
  ;;
esac
exit 0
