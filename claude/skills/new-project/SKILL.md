---
name: new-project
description: Starts a new Python data project; local uv .venv, Jupyter kernel, tests, git, and a private repo on GitHub or GitLab. Use when the user asks to create, start, scaffold or set up a new project or repo.
---

# New project

Works on macOS, Linux and Windows (Git Bash). Run each command alone: on Windows, and for any command outside the sandbox, a chain is denied.

1. Ask for the project name (kebab-case) if it is not given. Location: `~/git/<name>` (the folder name that the user keeps repos in, if it differs).
2. Create it:
   ```
   mkdir -p ~/git/<name>
   cd ~/git/<name>
   uv init --quiet --app --no-package --python 3.12
   uv add --dev ipykernel ruff pytest
   uv run python -m ipykernel install --user --name <name> --display-name "Python (<name>)"
   ```
3. Copy the template: `cp -R ${CLAUDE_PLUGIN_ROOT}/templates/project/. .` (CLAUDE.md, .claude/, .github/, .pre-commit-config.yaml, docs/, src/, tests/ with test_docs.py and test_smoke.py, evals/, data/, notebooks/) and add the pytest settings: `cat ${CLAUDE_PLUGIN_ROOT}/templates/pyproject-pytest.toml >> pyproject.toml`. Fill `<name>` in CLAUDE.md.
   - On native Windows there is no sandbox: delete `.claude/settings.json` from the copy. Its Bash allow rules would run commands with no question.
   - If the project calls an LLM: `uv add --dev anthropic`, and point `predict()` in `evals/test_evals.py` at the real code.
4. Add the data packages the user names (default: `uv add pandas numpy matplotlib seaborn`).
5. `uv run pytest -q` must pass. Then `uvx pre-commit install` (outside the sandbox on macOS and Linux: it writes `.git/hooks`). The pre-commit config runs `gitleaks`: if `gitleaks` is not installed, tell the user, or remove that hook from `.pre-commit-config.yaml`.
6. First commit on `main` is allowed here only. Run `git add -A`, then `git commit -m "Initial project"` as two commands.
7. **Ask** before creating the remote repo (it publishes code). On the user's yes, run one of these from the project folder:
   - GitHub: `gh repo create <name> --private --source . --remote origin --push`
   - GitLab: `glab repo create <name> --private --defaultBranch main --skipGitInit`, then `git remote add origin <the URL it prints>` and `git push -u origin HEAD`. For a self-hosted GitLab, set `GITLAB_HOST` first.
8. Switch to a branch for the real work: `git switch -c feature/<first-task>`.

Never `pip install`. Never commit `data/raw/` or `.env`.
