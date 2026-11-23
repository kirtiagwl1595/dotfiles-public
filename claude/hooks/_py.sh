# Sourced by the shell hooks: `pyrun` runs a working Python 3.9+, on macOS, Linux and Windows
# (Git Bash), where `python3` can be the Microsoft Store stub. Returns 127 when there is none;
# the shell hooks then do nothing, because they only advise (the guards fail closed in py.sh).
export PYTHONUTF8=1
pyrun() {
  local p
  for p in python3 "py -3" python; do
    # $p unquoted on purpose: "py -3" is a program and an option
    if $p -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
      $p "$@"
      return
    fi
  done
  return 127
}

# A hash of stdin, with the tool this machine has (shasum is not on every Git Bash)
sha() {
  if command -v shasum >/dev/null 2>&1; then shasum; else sha1sum; fi
}
