#!/usr/bin/env python3
"""route-hint.py - UserPromptSubmit (advisory): when a prompt asks for a search - "where is",
"find all", "how does X work", "which files" - add one line routing it to an `explore` subagent
on the fast tier before the parent starts reading files itself.

WHY THIS EXISTS
---------------
The cheapest point to delegate is before the first direct read: once the parent has pulled a
dozen files into its own context, every later turn pays for them. delegate-nudge.py catches the
habit late (60k context, 12 calls); this catches the request early, at no cost when the prompt
is not a search.

Matching is deliberately narrow (SEARCH below): a miss only means no hint, a false hit adds
one line to one turn. A search match alone is not enough: the prompt must also be broad
(where/all/every/across, or 2+ named files or directories) or the session already past 40k
context (BROAD, PATH, CONTEXT_FLOOR). `additionalContext` JSON on stdout, the form that reaches the model.

Advisory tier: exit 0 always, nothing on stderr. `CK_NO_ROUTE_HINT=1` silences it.
stdlib only, py3.9.
"""

import importlib.util
import json
import os
import re
import sys

SEARCH = re.compile(
    r"\b(where\s+(is|are|do|does)|find\s+(all|every|where|the\s+files?)|which\s+files?|"
    r"how\s+does\s+\S+(\s+\S+){0,3}\s+work|look\s+(for|through)|search\s+(for|the)|"
    r"trace\s+(where|how|the)|map\s+(out\s+)?(the|all)|audit\s+(the|all))\b",
    re.IGNORECASE)


# A search-shaped prompt still gets no hint when it is SHORT: one named place, no breadth word,
# and a small session. The qa-agents A/B measured it - answered directly on the balanced tier,
# $0.14; routed to explore uncapped, $0.20. Delegation pays once the search is broad or the
# context the parent would re-send each turn is already large.
BROAD = re.compile(r"\b(where|all|every|across)\b", re.IGNORECASE)
PATH = re.compile(r"(?<![\w/.])(?:[\w.-]+/[\w./-]*|[\w-]+\.[A-Za-z]{1,5})\b")
CONTEXT_FLOOR = 40000


def _report():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "delegation-report.py")
    spec = importlib.util.spec_from_file_location("ck_delegation_report", here)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _context(transcript):
    """Context of the latest assistant turn (0 when unknown): what the next turn re-sends."""
    if not isinstance(transcript, str) or not os.path.isfile(transcript):
        return 0
    try:
        report, context = _report(), 0
        for record in report._records(transcript):
            message = record.get("message") if record.get("type") == "assistant" else None
            usage = message.get("usage") if isinstance(message, dict) else None
            if isinstance(usage, dict):
                context = sum(v for k, v in usage.items() if k in report.CONTEXT_KEYS
                              and isinstance(v, int) and not isinstance(v, bool))
        return context
    except Exception:
        return 0


def _explore_call():
    try:
        report = _report()
        return report.explore_call(report._root())
    except Exception:
        return "Agent(subagent_type=explore, model=haiku, maxTurns 12)"


def main():
    if os.environ.get("CK_NO_ROUTE_HINT") == "1":
        return 0
    try:
        payload = json.load(sys.stdin)
        prompt = payload.get("prompt") if isinstance(payload, dict) else None
    except Exception:
        return 0
    if not isinstance(prompt, str) or not SEARCH.search(prompt):
        return 0
    if not (BROAD.search(prompt) or len(set(PATH.findall(prompt))) >= 2
            or _context(payload.get("transcript_path")) > CONTEXT_FLOOR):
        return 0
    note = ("[ck route] This reads as a search. Send it to %s and keep only its "
            "conclusion; read directly only the file you will edit. Silence for one process "
            "tree with CK_NO_ROUTE_HINT=1." % _explore_call())
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": note}}) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
