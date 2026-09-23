#!/usr/bin/env python3
"""
heal_local_settings.py - repair the maintainer's local hook-profile override.

CLAUDE.md's "session setup gotcha" documents a recurring session tax: when the
gitignored `.claude/settings.local.json` carrying `ECC_HOOK_PROFILE=minimal` goes
missing, `ops-enforcement.sh` blocks every Edit/Write and the only remedy is a manual
copy out of CONTRIBUTING.md. This restores the file instead.

REPO-GATED, and that gate is the whole safety argument. `ops-enforcement.sh:13` exits 0
on the `minimal` profile, so writing that value into a FLEET project would silently
switch enforcement off across every kitted repo. Healing therefore acts only when the
project root's pyproject.toml declares `name = "claudekit-agents"` -- this kit's own
repository, where the maintainer is the maintainer and not a constrained agent.

The gate takes TWO independent signals, both required: the pyproject name AND the kit's
own source package at `src/claudekit/__init__.py`. The name alone was not enough -- it is
forgeable by copying, so a fork or a vendored `.claude/` tree that kept the name was
healed too and had its enforcement profile flipped to `minimal`. A vendored copy brings
the prompts, never the source package. `test_a_vendored_copy_keeping_the_name_is_refused`
pins this; drop the marker check and it goes red on its own.

Never destructive:
  missing                      -> write the known-good default
  unparseable / not an object  -> move the original aside, then write the default
  object without the key       -> insert ONLY that key; every other key is preserved
  object WITH the key (any value, including "standard") -> untouched
  symlink                      -> refused, untouched

It cannot interact with the installer's preservation trap (a file written before
preserve_assets.py runs makes preservation skip the project's real one): this name is in
preserve_assets.py SKIP_NAMES and install_overrides.NEVER_MANAGED, so the preserving walk never
reaches `_consider` for it, and this script runs at session start, never inside install.

Advisory: always exits 0, prints at most one line, and never blocks a session. The profile
itself takes effect at the NEXT session start (CONTRIBUTING.md).

Zero third-party dependencies; Python 3.9+ (no tomllib -- the pyproject name is matched
with a regex, not parsed).
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Tuple

SETTINGS_REL = os.path.join(".claude", "settings.local.json")
PROFILE_KEY = "ECC_HOOK_PROFILE"
DEFAULT_SETTINGS = {"env": {PROFILE_KEY: "minimal"}}
# The one project this may ever heal. Matched on the [project] name line rather than
# parsed: tomllib is 3.11+ and this file must import on 3.9.
_NAME_RE = re.compile(r"""^\s*name\s*=\s*["']claudekit-agents["']""", re.M)
# Second, independent signal, because the name alone is forgeable by copying. Healing
# writes ECC_HOOK_PROFILE=minimal, which turns enforcement OFF: a false positive in a
# downstream project is the worst thing this script can do, so BOTH must hold. A
# vendored .claude/ tree brings the prompts, never the kit's own source package.
_MARKER_REL = os.path.join("src", "claudekit", "__init__.py")


def is_claudekit_repo(root: str) -> bool:
    """True only for this kit's own repository.

    Two signals, both required: the pyproject name AND the kit's own source package.
    Either alone is copyable; together they are not present in a project that merely
    vendored the prompts.
    """
    if not os.path.isfile(os.path.join(root, _MARKER_REL)):
        return False
    try:
        with open(os.path.join(root, "pyproject.toml"), "r", encoding="utf-8") as handle:
            return bool(_NAME_RE.search(handle.read()))
    except (OSError, ValueError):
        return False


def _atomic_write(path: str, data: dict) -> None:
    tmp = path + ".tmp-heal"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.replace(tmp, path)


def heal(root: str) -> Tuple[str, str]:
    """Repair the local override under `root`. Returns (action, message).

    action is one of: not-claudekit, no-claude-dir, symlink-refused, created,
    repaired, merged, kept, error.
    """
    if not is_claudekit_repo(root):
        return "not-claudekit", ""
    if not os.path.isdir(os.path.join(root, ".claude")):
        return "no-claude-dir", ""

    path = os.path.join(root, SETTINGS_REL)
    if os.path.islink(path):
        # Same discipline as review-record.py's _safe_write: a symlink on this path is
        # a redirect to somewhere this script was never asked to write.
        return "symlink-refused", (
            "  settings.local.json is a symlink -- not healed. Inspect it by hand.")

    if not os.path.exists(path):
        try:
            _atomic_write(path, DEFAULT_SETTINGS)
        except OSError as exc:
            return "error", "  settings.local.json could not be created (%s)." % exc
        return "created", (
            "  Restored .claude/settings.local.json (%s=minimal). It takes effect at the "
            "NEXT session start." % PROFILE_KEY)

    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("top level is %s, not an object" % type(data).__name__)
    except (OSError, ValueError) as exc:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        aside = "%s.corrupt-%s" % (path, stamp)
        try:
            os.replace(path, aside)
            _atomic_write(path, DEFAULT_SETTINGS)
        except OSError as err:
            return "error", "  settings.local.json is malformed and unrepairable (%s)." % err
        return "repaired", (
            "  .claude/settings.local.json was malformed (%s); the original is at %s and a "
            "known-good default replaced it." % (exc, os.path.basename(aside)))

    env = data.get("env")
    if isinstance(env, dict) and isinstance(env.get(PROFILE_KEY), str):
        # A deliberate choice -- including "standard" or "strict" -- is never overridden.
        return "kept", ""
    if not isinstance(env, dict):
        env = {}
    env[PROFILE_KEY] = "minimal"
    data["env"] = env
    try:
        _atomic_write(path, data)
    except OSError as exc:
        return "error", "  settings.local.json could not be updated (%s)." % exc
    return "merged", (
        "  Added %s=minimal to .claude/settings.local.json; every other setting in it was "
        "left as it was. It takes effect at the NEXT session start." % PROFILE_KEY)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Heal the gitignored local hook-profile override (ClaudeKit repo only)")
    parser.add_argument("--root", default=os.getcwd(),
                        help="project root (default: cwd)")
    parser.add_argument("--quiet", action="store_true",
                        help="never print, even when the file was repaired")
    parser.add_argument("--print-action", action="store_true",
                        help="print the action token on stdout (for tests)")
    args = parser.parse_args()

    try:
        action, message = heal(args.root)
    except Exception as exc:                      # pragma: no cover - defensive
        # Advisory by contract: a crash here must not colour a session start.
        print("  settings.local.json healing skipped (%s)." % exc, file=sys.stderr)
        return 0
    if args.print_action:
        print(action)
    elif message and not args.quiet:
        print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
