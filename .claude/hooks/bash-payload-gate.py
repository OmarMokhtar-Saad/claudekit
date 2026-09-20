#!/usr/bin/env python3
"""bash-payload-gate.py - PreToolUse/Bash: a ceiling on the size of the command TEXT.

WHY THIS EXISTS
---------------
Every cap this project ships measures tool OUTPUT. `output_filter.py` caps Bash stdout at
2,000 chars (104 markers in the 2026-09-20 audit, provably firing); `read-window-guard.py`
caps a Read; `context-budget-gate.py` caps the window. Nothing caps what the model WRITES.

Measured over session qa-agents-20260920-1346 (transcript f1023f7b, 251 Bash calls):
`tool_use` parameters were 40.3% of the transcript body - 65,883 tokens, very nearly equal
to all tool RESULTS combined (73,542). 197,336 chars of command text, ~49,334 tokens.

That cost is not paid once. A token authored at request k is re-billed by every request
until the next compaction reset. The 48,464 tokens of oversized inline payloads in that
session carried 1.68M re-billed tokens - 6% of a 27.52M bill - for text that existed only
because a script was pasted into the command line instead of written to a file and run by
path. A file costs its bytes once, on disk, and the command that invokes it is 40 chars.

THE THRESHOLD IS MEASURED, NOT GUESSED
--------------------------------------
Command length over those 251 calls: p50 204, p75 475, p90 2,777, p95 3,954, max 11,507.
The distribution is bimodal - ordinary commands are two to five hundred characters, and
pasted scripts are thousands. THRESHOLD sits in the empty region between p75 and p90, so
it separates the two populations rather than taxing normal work:

    threshold 1,500 -> refuses 39/251 calls (15.5%), trims 89,700 chars (~22,425 tokens)

Raising it to 3,000 halves the yield (44,632 chars); lowering it to 800 gains 33% more but
starts catching genuine one-liners. 1,500 is the knee.

NOT A SANDBOX (project hard rule 6)
-----------------------------------
This is a budget, not a security control. It bounds the SIZE of a command, never its
meaning, and `iron-law-gate.py` remains the thing that decides whether a Bash call may
write at all. A caller who wants the bytes through can split them across two calls. The
point is to make the cheap path the default one, not to make the expensive path impossible.

FAIL DIRECTION
--------------
Fail OPEN everywhere. An unparseable payload, a missing field, or a bug in this file must
never deny the main agent its Bash tool - the blast radius of a false positive here is the
whole session, and the cost of a false negative is a few thousand tokens.
"""

import json
import os
import re
import sys

THRESHOLD = 1500

# Commands whose length is inherent rather than pasted. A commit message, a PR body and a
# patch ARE the payload; there is no cheaper spelling of them, so a cap would only force
# the caller into a worse one (a temp file for a two-paragraph message). Anchored at the
# start of the command, after optional leading env assignments.
EXEMPT = re.compile(
    r"""^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*        # leading VAR=value assignments
        (?:git\s+(?:commit|apply|am|tag)\b            # message/patch carriers
          |gh\s+(?:pr|issue|release)\s+(?:create|edit|comment)\b
          |patch\b
        )""",
    re.VERBOSE,
)

HINT = (
    "BLOCKED bash-payload-gate: this command is %d chars (ceiling %d). An inline payload is "
    "re-billed by every later request in the session - the 2026-09-20 audit measured 48,464 "
    "such tokens carrying 1.68M re-billed, 6%% of the session. Write the script to "
    "$CLAUDE_SCRATCHPAD (or the session scratchpad directory) and run it by path, or split "
    "the command. Override for one process tree with CK_RAW_INPUT=1.\n"
)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0

    try:
        if payload.get("tool_name") != "Bash":
            return 0
        if os.environ.get("CK_RAW_INPUT") == "1":
            return 0

        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        command = tool_input.get("command")
        if not isinstance(command, str):
            return 0

        size = len(command)
        if size <= THRESHOLD:
            return 0
        if EXEMPT.match(command):
            return 0
    except Exception:
        # The guard's own bug must never block a command.
        return 0

    sys.stderr.write(HINT % (size, THRESHOLD))
    # Spelled as a literal sys.exit(2), not `return 2`: 2 is the only code Claude
    # Code honours as a block, and test_blocking_tier_is_honest derives that
    # capability from the shipped file's text rather than from the registry label.
    sys.exit(2)


if __name__ == "__main__":
    sys.exit(main())
