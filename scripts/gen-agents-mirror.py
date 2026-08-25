#!/usr/bin/env python3
"""Keep the Codex corpus mirror (.agents/skills/) in MEMBERSHIP parity with .claude/skills/.

Membership, deliberately -- not content. 28 of the mirror's files carry intentional Codex
adaptations (`.Codex/` paths, `AGENTS.md`, "Codex" for "Claude"), so a content-equality
generator would silently destroy them. What CAN be checked mechanically is that every live
skill has a mirror entry and no mirror entry outlives its source. Content drift between an
adapted pair is a judgement call and is reported, never auto-resolved.

    python3 scripts/gen-agents-mirror.py           # add missing, report the rest
    python3 scripts/gen-agents-mirror.py --check   # exit 1 on any membership drift

Zero third-party dependencies; Python 3.9+.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIVE = os.path.join(ROOT, ".claude", "skills")
MIRROR = os.path.join(ROOT, ".agents", "skills")

# The adaptation the mirror already applies, derived from the files themselves rather than
# assumed: `.claude/` -> `.Codex/` and the product name. Ordered longest-first so the path
# rule wins before the bare-name rule can touch it.
SUBSTITUTIONS = (
    (re.compile(r"\.claude/"), ".Codex/"),
    (re.compile(r"\bClaude Code\b"), "Codex"),
    (re.compile(r"\bClaude\b"), "Codex"),
)


def skill_ids(base):
    if not os.path.isdir(base):
        return set()
    return {d for d in os.listdir(base)
            if os.path.isfile(os.path.join(base, d, "SKILL.md"))}


def adapt(text):
    for pattern, repl in SUBSTITUTIONS:
        text = pattern.sub(repl, text)
    return text


def main():
    check = "--check" in sys.argv
    live, mirror = skill_ids(LIVE), skill_ids(MIRROR)
    missing = sorted(live - mirror)
    stale = sorted(mirror - live)

    # Reported, never auto-fixed: an adapted file legitimately differs from its source.
    drifted = []
    for sid in sorted(live & mirror):
        a = os.path.join(MIRROR, sid, "SKILL.md")
        b = os.path.join(LIVE, sid, "SKILL.md")
        with open(a, encoding="utf-8") as fa, open(b, encoding="utf-8") as fb:
            if adapt(fb.read()) != fa.read():
                drifted.append(sid)

    if check:
        ok = True
        for sid in missing:
            print(f"MISSING from the Codex mirror: {sid}", file=sys.stderr)
            ok = False
        for sid in stale:
            print(f"STALE in the Codex mirror (no .claude/skills/{sid}): {sid}",
                  file=sys.stderr)
            ok = False
        if not ok:
            print("FAIL: .agents/skills/ membership drifted. "
                  "Run: python3 scripts/gen-agents-mirror.py", file=sys.stderr)
            return 1
        print(f"OK: Codex mirror has every live skill ({len(live)}), no stale entries. "
              f"{len(drifted)} adapted file(s) differ in content, which is expected.")
        return 0

    for sid in missing:
        src = os.path.join(LIVE, sid, "SKILL.md")
        dst_dir = os.path.join(MIRROR, sid)
        os.makedirs(dst_dir, exist_ok=True)
        with open(src, encoding="utf-8") as fh:
            body = adapt(fh.read())
        with open(os.path.join(dst_dir, "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write(body)
        print(f"  added {sid}")

    # Removal is owner-gated everywhere else in this repo, so it is reported, not done.
    for sid in stale:
        print(f"  STALE (remove by hand -- deletions are owner-gated): {sid}")

    print(f"Codex mirror: +{len(missing)} added, {len(stale)} stale, "
          f"{len(drifted)} adapted file(s) with content drift.")
    if drifted:
        print("  content drift is NOT auto-resolved -- an adapted file is supposed to "
              "differ. Triage per file:")
        for sid in drifted[:10]:
            print(f"    {sid}")
        if len(drifted) > 10:
            print(f"    ... and {len(drifted) - 10} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
