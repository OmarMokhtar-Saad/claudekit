#!/usr/bin/env python3
"""panel-guard.py - PreToolUse (blocking, Agent/Task): keep the /review critics zero-context.

WHY THIS EXISTS
---------------
Audit 2026-11-11 (335 critic runs): only 2 prompts were the path-only contract; 118 passed a
coordinator brief, others pasted history and "300 words" limits that broke the PANEL format.
The EGM critics are only worth running when they see nothing but the plan.

WHAT IT DOES
------------
- plan-design-critic / plan-readiness-critic: allow only a prompt that is exactly
  `Plan: <absolute path>.md. Review it.` naming an existing file; anything else exits 2.
- reviewer naming a .claude/plans/plan-*.md: allow, with a one-line nudge to spawn both
  critics in the same message (unless CK_REVIEW_PANEL is off). Best effort; /review's
  numbered steps carry the duty.
- Anything else, or an unparseable payload: allow. stdlib, py3.9, no state.
"""
import json
import os
import re
import sys

CRITICS = {"plan-design-critic", "plan-readiness-critic"}
CRITIC_RE = re.compile(r"^Plan: (/.+\.md)\. Review it\.$")
PLAN_RE = re.compile(r"\.claude/plans/plan-[^\s`'\"]*\.md")
OFF = {"0", "off", "false"}
DENY = ('panel-guard: critics take exactly "Plan: <path>. Review it." — no history, briefs '
        "or word limits (zero-context contract). Run review-panel.py prompts for the line.")


def decide(payload):
    """(exit code, stdout, stderr)."""
    ti = payload.get("tool_input") if isinstance(payload, dict) else None
    if not isinstance(ti, dict):
        return 0, "", ""
    kind = ti.get("subagent_type")
    prompt = ti.get("prompt")
    if not isinstance(prompt, str):
        prompt = ""
    if kind in CRITICS:
        m = CRITIC_RE.match(prompt.strip())
        if m and os.path.isfile(m.group(1)):
            return 0, "", ""
        return 2, "", DENY
    if kind == "reviewer" and PLAN_RE.search(prompt):
        if (os.environ.get("CK_REVIEW_PANEL") or "").strip().lower() in OFF:
            return 0, "", ""
        note = ("panel-guard: /review panel — spawn plan-design-critic and plan-readiness-critic "
                'in this same message with "Plan: <path>. Review it." unless the panel is off.')
        out = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}
        return 0, json.dumps(out), ""
    return 0, "", ""


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    code, out, err = decide(payload)
    if out:
        print(out)
    if err:
        print(err, file=sys.stderr)
    if code == 2:
        sys.exit(2)
    return code


if __name__ == "__main__":
    sys.exit(main())
