# Sourced by the shell hooks: `pyrun` runs a working Python 3.9+, on macOS, Linux and Windows
# (Git Bash), where `python3` can be the Microsoft Store stub. Returns 127 when there is none;
# the shell hooks then do nothing, because they only advise (the guards fail closed in py.sh).
export PYTHONUTF8=1
pyrun() {
  local p
  for p in python3 "py -3" python; do
    # $p unquoted on purpose: "py -3" is a program and an option
    if $p -c "import sys; sys.exit(sys.version_info < (3, 9))" >/dev/null 2>&1; then
      # Windows Python ends a printed line with CRLF; bash `read` keeps the \r in the last field
      # (so `== True` fails). Strip it here, once, and keep Python's own exit status.
      $p "$@" | tr -d '\r'
      return "${PIPESTATUS[0]}"
    fi
  done
  return 127
}

# One path form for every comparison and key: forward slashes, as `git rev-parse` prints them
# on Windows (a C:\x path from a test or an env var becomes C:/x)
fwd() { printf '%s' "${1//\\//}"; }

# A hash of stdin, with the tool this machine has (shasum is not on every Git Bash)
sha() {
  if command -v shasum >/dev/null 2>&1; then shasum; else sha1sum; fi
}
