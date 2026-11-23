#!/usr/bin/env bash
# SessionStart: in a repo with a graphify graph, tell Claude to query it before Grep/Read.
# Stdout of a SessionStart hook goes into Claude's context. Silent when there is no graph.
. "$(dirname "${BASH_SOURCE[0]}")/_py.sh"
input=$(cat)
cwd=$(pyrun -c "import json,sys; print(json.loads(sys.argv[1]).get('cwd') or '')" "$input") || exit 0
cd "${cwd:-${CLAUDE_PROJECT_DIR:-.}}" 2>/dev/null || exit 0
root=$(git rev-parse --show-toplevel 2>/dev/null) || root=$PWD
graph="$root/graphify-out/graph.json"
[[ -f $graph ]] || exit 0

echo "graphify: this repo has a knowledge graph (graphify-out/). For code and architecture questions, run graphify query/path/explain first; read only the files it points to."
last_commit=$(git -C "$root" log -1 --format=%ct 2>/dev/null || echo 0)
# Python reads the mtime: `stat` differs between macOS and Linux
mtime=$(pyrun -c "import os,sys; print(int(os.path.getmtime(sys.argv[1])))" "$graph") || exit 0
if ((mtime < last_commit)); then
  echo "graphify: the graph is older than the last commit; run \`graphify . --update\` first."
fi
exit 0
