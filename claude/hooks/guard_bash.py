#!/usr/bin/env python3
"""PreToolUse Bash|PowerShell: run every shell guard in one Python process.

One process per shell call instead of one per guard. Each guard also runs alone by path.
The strongest result wins: block, then deny, then ask.
"""

import sys

# A failed import exits 1, and exit 1 lets the tool call through
try:
    import guard_compound
    import guard_live_checkout
    import guard_main_branch
    import guard_pip
    import guard_private_terms
    import guard_secrets
    from _common import run_guard

    try:
        import guard_loop
    except ModuleNotFoundError as e:  # the loop engine is optional
        if e.name != "guard_loop":
            raise
        guard_loop = None
except Exception:  # noqa: BLE001 - SyntaxError too, not only ImportError
    print("Blocked: the Bash guards could not load. Report it.", file=sys.stderr)
    sys.exit(2)

if __name__ == "__main__":
    run_guard(
        guard_secrets.check,
        guard_private_terms.check,
        guard_pip.check,
        guard_main_branch.check,
        guard_live_checkout.check,
        guard_compound.check,
        *([guard_loop.check] if guard_loop else []),
    )
