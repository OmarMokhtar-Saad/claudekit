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


# ---------------------------------------------------------------------------
# Every case the second adversarial review found. The suite passed before each of
# these, which is the point: the fixtures had been written around the implementation.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("content", [
    "import hashlib as _h\nh = _h.md5(x)",        # aliased import
    "from hashlib import md5\nd = md5(x)",        # direct import
    "h = hashlib . md5(data)",                    # spaced attribute access
    'f = getattr(hashlib, "md5")',                # dynamic lookup
    "cipher = MD5.new()",                         # PyCrypto style
])
def test_aliased_and_indirect_weak_crypto_warns(content):
    """The module-adjacent pattern caught ONE spelling. These are the rest."""
    assert "Weak cryptographic algorithm" in run_hook(content)


@pytest.mark.parametrize("content", [
    "x = 1  # never use MD5 here",                # TRAILING comment -- the original miss
    "AES_KEY = 1  // RC4 was removed",
    'BANNED = ["RC4", "MD5"]',                    # a DENYLIST, not weak crypto
    '"""Return the SHA1 of HEAD."""',             # a docstring
    "h = hashlib.sha256(d)",
    "k = crypto.randomBytes(32)",
    "p = sha1sum_path",
])
def test_prose_literals_and_strong_crypto_do_not_warn(content):
    """A check that fires on a file FORBIDDING md5 is the false positive that makes an
    advisory ignorable. The trailing-comment case is the one this hook got wrong twice,
    in opposite directions."""
    assert "Weak cryptographic algorithm" not in run_hook(content)


def test_the_partial_scan_notice_is_on_stdout():
    """It qualifies the warnings, which are on stdout; a PreToolUse hook exiting 0 does
    not surface stderr. Asserting against merged streams hid this."""
    payload = json.dumps({"tool_name": "Edit",
                          "tool_input": {"file_path": "src/a.py",
                                         "new_string": "a" * 200_050}})
    env = dict(os.environ, ECC_HOOK_PROFILE="standard")
    proc = subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True,
                          text=True, env=env, cwd=str(REPO))
    assert "PARTIAL SCAN" in proc.stdout, "the notice is not on stdout"


def test_a_non_string_content_value_is_not_scanned_as_a_repr():
    """A list-valued `content` gave len() == 2, so a 300,000-char payload reported a
    length of 2, triggered no PARTIAL SCAN, and was scanned as a Python repr."""
    payload = json.dumps({"tool_name": "Edit",
                          "tool_input": {"file_path": "src/a.py",
                                         "content": ["x" * 300_000, "y"]}})
    env = dict(os.environ, ECC_HOOK_PROFILE="standard")
    proc = subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True,
                          text=True, env=env, cwd=str(REPO))
    assert proc.stdout.strip() == "", proc.stdout

def test_documentation_targets_are_still_skipped():
    """The path skip list predates this change and must survive it."""
    assert run_hook("hashlib.md5(x)", path="docs/notes.md").strip() == ""
