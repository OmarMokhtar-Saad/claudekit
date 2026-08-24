"""`security-reminder.sh` scans the whole edit, and says so when it cannot.

`print(inp[key][:3000])` meant every pattern below it -- `shell=True`, SQL concatenation,
`innerHTML`, TLS-verify-off, weak crypto, permissive CORS -- matched a TRUNCATED copy. A
risk at character 3001 was never scanned, the hook exited 0, and nothing indicated that
coverage had been partial. 3000 characters is roughly 75 lines. **The defect is the
silence, not the number**, so the cap stays (a PreToolUse hook must not chew through a
pathological paste) and a truncated scan now announces itself with the numbers.

Second half: the weak-crypto pattern `\bMD5\b` is case-SENSITIVE, so `hashlib.md5(data)`
-- the way weak crypto is actually written in Python -- never matched, while a comment
saying "MD5" did. Exactly backwards. Verified against the previous version before
changing it. Now API-call shapes match case-insensitively, the bare uppercase word matches
only on non-comment lines, and `hashlib.sha256` must not fire.
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "security-reminder.sh"


def run_hook(content, path="src/app.py"):
    payload = json.dumps({"tool_name": "Edit",
                          "tool_input": {"file_path": path, "new_string": content}})
    env = dict(os.environ, ECC_HOOK_PROFILE="standard")
    proc = subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True,
                          text=True, env=env, cwd=str(REPO))
    return proc.stdout + proc.stderr


def test_a_risk_past_the_old_3000_char_limit_is_found():
    """The assertion that would have failed before: 3000 chars of padding, then the risk."""
    content = "x = 1  # pad\n" * 300 + "subprocess.run(cmd, shell=True)"
    assert len(content) > 3000
    assert "Shell injection risk" in run_hook(content)


def test_a_scan_over_the_cap_announces_itself():
    """Partial coverage that announces itself is a limitation; partial coverage that stays
    quiet is a false negative wearing a pass."""
    out = run_hook("a" * 200_050)
    assert "PARTIAL SCAN" in out
    assert "200000" in out and "200050" in out, "the notice must carry both numbers"


def test_a_scan_within_the_cap_is_silent_about_truncation():
    assert "PARTIAL SCAN" not in run_hook("y = 2\n")


@pytest.mark.parametrize("content", [
    "import hashlib\nh = hashlib.md5(data)",     # the commonest real form, lowercase
    "cipher = MD5.new()",
    "from Crypto.Hash import SHA1",
])
def test_real_weak_crypto_warns(content):
    assert "Weak cryptographic algorithm" in run_hook(content)


@pytest.mark.parametrize("content", [
    "# do not use MD5 here, it is banned",
    "// SHA1 is banned by policy",
    "h = hashlib.sha256(data)",
])
def test_comments_and_strong_crypto_do_not_warn(content):
    assert "Weak cryptographic algorithm" not in run_hook(content)


def test_documentation_targets_are_still_skipped():
    """The path skip list predates this change and must survive it."""
    assert run_hook("hashlib.md5(x)", path="docs/notes.md").strip() == ""
