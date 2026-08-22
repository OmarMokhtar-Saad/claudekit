#!/usr/bin/env python3
"""Resolve capability tiers to concrete models in the agent frontmatter.

`.claude/model-policy.json` is the single source of truth. It states, separately,
what each role is *accountable for* and which *capability tier* the assignment
earns; a tier resolves to a vendor model id in exactly one table. Claude Code's
agent frontmatter only understands concrete ids, so this script projects the
table onto `.claude/agents/*.md` and `--check` fails when the two disagree.

That indirection is the point: changing which model a tier means is a one-line
edit here instead of a sweep across 29 prompts, and policy prose elsewhere in
the repo names tiers, never vendors.

Usage:
    python3 scripts/gen-model-policy.py            # rewrite `model:` lines in place
    python3 scripts/gen-model-policy.py --check    # exit 1 if frontmatter drifted
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AGENTS_DIR = os.path.join(ROOT, ".claude", "agents")
POLICY = os.path.join(ROOT, ".claude", "model-policy.json")

MODEL_LINE_RE = re.compile(r"^model:[ \t]*([^\s\r]+)[ \t]*(?=\r?$)", re.M)
# The lookahead keeps a CRLF file's `\r` OUTSIDE the match, so rewriting the
# model value cannot strip the line ending. With newline="" on both ends, a
# rewrite touches exactly the bytes of the value and nothing else.


def frontmatter_span(text):
    """(start, end) of the YAML frontmatter body, or None if there isn't one.

    The `model:` pattern is only meaningful inside frontmatter. Searched against
    a whole file it would also match a fenced example in an agent's prose - and
    an agent that had LOST its frontmatter `model:` line would then have its BODY
    rewritten while the script reported success, which is the one outcome the
    missing-line defect path exists to prevent.
    """
    for opener in ("---\r\n", "---\n"):
        if text.startswith(opener):
            end = text.find("\n---", len(opener))
            return (len(opener), end) if end != -1 else None
    return None


def load_policy(path):
    """Parse the policy table, failing closed on any structural defect.

    A malformed table must never silently degrade to "leave the frontmatter
    alone" - that would let an unreviewed model binding survive the gate.
    """
    with open(path, encoding="utf-8") as handle:
        policy = json.load(handle)
    tiers = policy.get("capability_tiers")
    roles = policy.get("roles")
    if not isinstance(tiers, dict) or not tiers:
        raise ValueError("model-policy.json: capability_tiers must be a non-empty object")
    if not isinstance(roles, dict) or not roles:
        raise ValueError("model-policy.json: roles must be a non-empty object")
    for name, tier in sorted(tiers.items()):
        if not isinstance(tier, dict) or not tier.get("model"):
            raise ValueError("model-policy.json: tier %r has no model" % name)
    for name, role in sorted(roles.items()):
        if not isinstance(role, dict):
            raise ValueError("model-policy.json: role %r is not an object" % name)
        if role.get("tier") not in tiers:
            raise ValueError(
                "model-policy.json: role %r names unknown tier %r" % (name, role.get("tier")))
        escalate = role.get("escalate_to")
        if escalate is not None and escalate not in tiers:
            raise ValueError(
                "model-policy.json: role %r escalates to unknown tier %r" % (name, escalate))
        if not role.get("accountable_for"):
            raise ValueError("model-policy.json: role %r declares no accountability" % name)
    for site in policy.get("callsite_overrides", {}).get("sites", []):
        if not isinstance(site, dict) or not site.get("path") or not site.get("reason"):
            raise ValueError(
                "model-policy.json: every callsite override needs a path and a reason")
    return policy


def agent_files(agents_dir):
    """agent name -> path, for real agent files only (frontmatter, not shared docs)."""
    found = {}
    for fname in sorted(os.listdir(agents_dir)):
        path = os.path.join(agents_dir, fname)
        if not fname.endswith(".md") or not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as handle:
            head = handle.read(4)
        if head != "---\n":
            continue  # QUICK_START / HANDOFF_PROTOCOL are prose, not agents
        found[fname[:-3]] = path
    return found


def resolve(policy):
    """role -> concrete model id for its declared tier."""
    tiers = policy["capability_tiers"]
    return {name: tiers[role["tier"]]["model"] for name, role in policy["roles"].items()}


def sync(check_only):
    policy = load_policy(POLICY)
    wanted = resolve(policy)
    files = agent_files(AGENTS_DIR)

    problems = []
    for name in sorted(set(files) - set(wanted)):
        problems.append("agent %r has no role entry in model-policy.json" % name)
    for name in sorted(set(wanted) - set(files)):
        problems.append("model-policy.json names role %r with no agent file" % name)
    if problems:
        for line in problems:
            print("DRIFT: %s" % line, file=sys.stderr)
        print("Every agent must have exactly one role entry. Fix .claude/model-policy.json.",
              file=sys.stderr)
        return 1

    # Two-phase: compute every write and the complete defect list BEFORE touching
    # disk. A single-pass loop would rewrite the alphabetically-early agents and
    # only then discover that a later one has no `model:` line at all - leaving a
    # partially applied policy behind an exit code of 1. Fail closed means nothing
    # is written, not "most of it was written".
    planned, defects = [], []
    for name in sorted(wanted):
        path = files[name]
        with open(path, encoding="utf-8", newline="") as handle:
            text = handle.read()
        span = frontmatter_span(text)
        match = MODEL_LINE_RE.search(text, *span) if span else None
        if match is None:
            defects.append("%s: no `model:` line in frontmatter" % name)
            continue
        if match.group(1) == wanted[name]:
            continue
        planned.append((name, path,
                        text[:match.start()] + "model: " + wanted[name] + text[match.end():],
                        match.group(1)))

    if defects:
        for line in defects:
            print("ERROR: %s" % line, file=sys.stderr)
        print("Nothing was written. Every agent needs a `model:` line in its frontmatter.",
              file=sys.stderr)
        return 1

    if check_only:
        if planned:
            for name, _path, _text, current in planned:
                print("DRIFT: %s: frontmatter says %s, policy says %s"
                      % (name, current, wanted[name]), file=sys.stderr)
            print("Run: python3 scripts/gen-model-policy.py", file=sys.stderr)
            return 1
        print("Model policy in sync: %d agent roles." % len(wanted))
        return 0

    for name, path, text, _current in planned:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        print("Updated %s -> %s" % (name, wanted[name]))
    print("Model policy applied: %d agent roles, %d rewritten." % (len(wanted), len(planned)))
    return 0


def main():
    check_only = "--check" in sys.argv[1:]
    try:
        return sync(check_only)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
