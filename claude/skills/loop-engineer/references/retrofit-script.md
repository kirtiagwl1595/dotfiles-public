# Retrofit a script

Use this for `script <path>`: a shell or Python file with side effects. The goal is a script that you can check without running its side effects for real.

## Side effects first

Run `python3 -B "${CLAUDE_PLUGIN_ROOT}/loopctl.py" audit` and find the script in `scripts`. Its `side_effects` list (deletes, downloads, installs, pushes, writes home) is what the checks must cover. Name each one in the LOOP.md goal or scope.

## The checks, in this order

| # | Check | Example `verify` | Why |
|---|---|---|---|
| 1 | A dry run that names each side effect and does none | `bash scripts/x.sh --dry-run \| grep -q 'would download'` | The first check you can run safely |
| 2 | The linter | `shellcheck -S warning scripts/x.sh` or `ruff check scripts/x.py` | Cheap, and it finds quoting and unused code |
| 3 | A test that runs the real script with stubbed tools | `uv run --no-project --with pytest pytest -q tests/test_x.py -p no:cacheprovider` | The real run path (R7): a unit test of a helper is not enough |
| 4 | One check for each other behavior of the real path | the test file, one test id each | One failed check names one cause |
| 5 | Baseline checks from `discover` that passed | the repo's lint for that one file | A fix must not break what worked |

For check 3, write the test in step 3 of the skill, before confirm:

- Put stub commands (`curl`, `wget`, `brew`, `git`) in a temp `bin/` first on `PATH`. A stub writes its arguments to a log and returns a local file, so the test needs no network.
- Set `HOME` to a temp folder. After the run, assert that nothing was written outside it.
- Build the path to the script from the repo root (`ROOT / "scripts/x.sh"`). Then `loopctl audit` counts the test as a verifier.

## Scope

- **may change:** the script, and every doc that names it. Find the docs with `git grep -l <file name> -- ':!tests' ':!*/tests/*'`. Pilot 1 could not update the skill and the setup doc that describe `install-jena.sh`, because they were not in scope.
- **must not change:** the paths of other scripts that call this one, unless the goal needs them. The tests and checks are protected anyway.

## Platform

- macOS: `/bin/bash` is 3.2 (no `declare -A`, no `${x,,}`). `sed -i` needs `''`, and `mktemp` needs a template. Run the checks with the bash that the script's `#!` line names.
- Windows: the loop itself does not run there (`docs/loop-engineering.md` §1), so it cannot check a Windows path. If the script supports Windows, write "Windows: not checked" in the debrief.
