"""Which file names hold secrets. One rule for guard_secrets.py, repo_setup.py and git/.gitignore_global.

Standard library only: repo_setup.py imports it under /usr/bin/python3.
"""

TEMPLATE_KINDS = ("example", "sample", "template")
ENV_TEMPLATES = tuple(f".env.{kind}" for kind in TEMPLATE_KINDS)

# `*.env` covers `.env`, and `!*.env.example` covers `.env.example`; the plain lines
# stay so that a search for `.env` finds them. Git uses the last matching line, so
# the template negations come last.
ENV_IGNORE = [
    *(".env", ".env.*", "*.env", "*.env.*"),
    *(f"!{t}" for t in ENV_TEMPLATES),
    *(f"!*{t}" for t in ENV_TEMPLATES),
]


def env_name(name):
    """True for an env file: `env` is a dot part after the first one, and the name
    does not end in a template (`.env.example`, `prod.env.sample`).

    Covers `.env`, `.env.local`, `prod.env` and `dev.env.bak`; not `.envrc` or `environment.py`.
    """
    parts = name.split(".")
    template = parts[-2:-1] == ["env"] and parts[-1] in TEMPLATE_KINDS
    return "env" in parts[1:] and not template
