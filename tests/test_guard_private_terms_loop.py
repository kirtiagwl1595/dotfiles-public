"""guard_private_terms treats the loop engine as optional, but a broken one must block.

A failed import exits 1, and exit 1 lets the tool call through: only "no such module" is fine.
"""

import json
import shutil
import subprocess
import sys

import pytest
from hookrun import HOOKS, env_for


def run_copy(tmp_path, loop_source):
    """Run a copy of the guard next to a _loop.py with this source (None: no file)."""
    for name in ("_common.py", "guard_private_terms.py"):
        shutil.copyfile(HOOKS / name, tmp_path / name)
    if loop_source is not None:
        (tmp_path / "_loop.py").write_text(loop_source)
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(tmp_path / "a.txt"), "content": "hello"},
    }
    p = subprocess.run(
        [sys.executable, "-B", str(tmp_path / "guard_private_terms.py")],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env_for(tmp_path),
        check=False,
    )
    return p.returncode, p.stdout, p.stderr


def test_no_loop_engine_is_fine(tmp_path):
    assert run_copy(tmp_path, None) == (0, "", "")


@pytest.mark.parametrize(
    "source",
    [
        "def broken(:\n",  # a syntax error
        "import no_such_module_for_this_test\n",  # a missing module of its own
        "raise RuntimeError('boom')\n",
    ],
    ids=["syntax-error", "missing-dependency", "crash"],
)
def test_a_broken_loop_engine_blocks(tmp_path, source):
    code, out, err = run_copy(tmp_path, source)
    assert code == 2 and "Blocked" in err and out == ""
