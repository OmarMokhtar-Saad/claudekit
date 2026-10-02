#!/usr/bin/env python3
"""Vendor `claudekit.security` into an installed project's `.claude/hooks/vendor/`.

command-guard.sh tries the live validator first (the `claudekit` console script, a kit
checkout, an importable package). When every one of those is broken, it used to let the
command through UNCHECKED. In qa-agents that happened for ~17 minutes on 2026-08-22,
because packaging work in the kit repo rewrote the editable install the hook depended on.
A security hook in one repo must not be breakable by unrelated work in another, so the
installer now also drops a byte-for-byte copy of the rules beside the hooks, and the hook
tries it LAST: a live install stays authoritative.

The package only uses relative imports, so it runs unchanged as `claudekit_security`.
PROVENANCE.json uses the same schema as qa-agents' `vendor/sync-vendor.py`, so that
script's drift check keeps working on a tree this installer wrote.

Usage: vendor_security.py <dest-hooks-dir> [<previous-hooks-dir>]
       (exit 0 = vendored, 1 = no source found)
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

KIT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
PKG = "claudekit_security"


def source_dir():
    """The kit checkout's package first, else wherever an installed one lives."""
    local = os.path.join(KIT_ROOT, "src", "claudekit", "security")
    if os.path.isfile(os.path.join(local, "cli.py")):
        return local
    try:
        import claudekit.security as sec  # noqa: PLC0415 - optional, only as a fallback
        return os.path.dirname(os.path.abspath(sec.__file__))
    except Exception:  # noqa: BLE001 - absent or broken install: nothing to vendor
        return None


def source_commit(src):
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=src, capture_output=True,
                             text=True, timeout=10)
        return out.stdout.strip() if out.returncode == 0 else ""
    except Exception:  # noqa: BLE001 - not a checkout
        return ""


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def vendor(dest_hooks, previous_hooks=None):
    src = source_dir()
    if not src:
        return 1
    vendor_dir = os.path.join(dest_hooks, "vendor")
    pkg_dir = os.path.join(vendor_dir, PKG)
    os.makedirs(pkg_dir, exist_ok=True)
    files = {}
    for name in sorted(os.listdir(src)):
        if name.endswith(".py"):
            shutil.copyfile(os.path.join(src, name), os.path.join(pkg_dir, name))
            files[name] = sha256(os.path.join(pkg_dir, name))
    # Files the source no longer has must not linger as importable rules.
    for name in os.listdir(pkg_dir):
        if name.endswith(".py") and name not in files:
            os.unlink(os.path.join(pkg_dir, name))
    provenance = {
        "files": files,
        "note": "Byte-for-byte copy written by the ClaudeKit installer. Do NOT hand-edit: "
                "re-run the installer (or vendor/sync-vendor.py --sync where present).",
        "source_commit": source_commit(src),
        "source_subpackage": "src/claudekit/security",
        "vendored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "vendored_from": os.path.dirname(os.path.dirname(os.path.dirname(src))),
    }
    # An unchanged reinstall must leave the tree byte-identical (manifest, git status), so
    # the previous install's timestamp is kept unless something else changed. install.sh
    # writes into a fresh staging tree, so the previous one is passed in.
    old_path = os.path.join(previous_hooks or dest_hooks, "vendor", "PROVENANCE.json")
    try:
        with open(old_path, encoding="utf-8") as fh:
            old = json.load(fh)
        if {k: v for k, v in old.items() if k != "vendored_at"} == \
                {k: v for k, v in provenance.items() if k != "vendored_at"}:
            provenance["vendored_at"] = old["vendored_at"]
    except (OSError, ValueError, AttributeError, KeyError):
        pass
    with open(os.path.join(vendor_dir, "PROVENANCE.json"), "w", encoding="utf-8") as fh:
        json.dump(provenance, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return 0


if __name__ == "__main__":
    if len(sys.argv) not in (2, 3):
        sys.exit("usage: vendor_security.py <dest-hooks-dir> [<previous-hooks-dir>]")
    sys.exit(vendor(*sys.argv[1:]))
