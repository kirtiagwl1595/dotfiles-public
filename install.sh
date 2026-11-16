#!/usr/bin/env bash
# Start install.py with a working Python 3.9+. macOS, Linux, and Git Bash on Windows.
# (Windows without Git Bash: install.cmd or install.ps1.)
#
#   ./install.sh --check   shows what would change; changes nothing
#   ./install.sh           makes the changes; asks before each one
#
# No Python 3.9+: it asks, then installs one with winget, brew or apt-get (the first it finds).
# On Windows, `python3` is often the Microsoft Store stub: the version check skips it.

# Bash builtins only until Python runs: PATH can be almost empty here
src="${BASH_SOURCE[0]//\\//}" # C:\x\install.sh → C:/x/install.sh
here="${src%/*}"
[ "$here" = "$src" ] && here=.

find_python() {
  for py in python3 "py -3" python; do
    # $py unquoted on purpose: "py -3" is a program and an option
    if $py -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
      echo "$py"
      return 0
    fi
  done
  return 1
}

python_installer() {
  if command -v winget >/dev/null 2>&1; then
    echo "winget install --id Python.Python.3.12 -e"
  elif command -v brew >/dev/null 2>&1; then
    echo "brew install python"
  elif command -v apt-get >/dev/null 2>&1; then
    echo "sudo apt-get install -y python3"
  fi
}

if ! py=$(find_python); then
  echo "install.sh needs Python 3.9 or later, and found none."
  cmd=$(python_installer)
  if [ -z "$cmd" ]; then
    echo "Install Python 3 from python.org, then run ./install.sh again."
    exit 1
  fi
  printf '  Install it now with: %s ? [y/N] ' "$cmd"
  read -r answer || answer=""
  answer=${answer//$'\r'/} # Git Bash on Windows can read "y\r"
  case $answer in
    y | Y | yes | Yes) $cmd || { echo "The Python install failed. Exit code $?."; exit 1; } ;;
    *) echo "Install Python 3, then run ./install.sh again."; exit 1 ;;
  esac
  if ! py=$(find_python); then
    echo "Python is installed, but this terminal does not see it yet. Open a new terminal, then run ./install.sh again."
    exit 1
  fi
fi

exec $py "$here/install.py" "$@"
