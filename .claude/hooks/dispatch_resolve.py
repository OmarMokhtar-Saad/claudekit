"""Resolve which registered handlers apply to one hook event.

Invoked by ``.claude/hooks/dispatch.sh`` as ``python3 dispatch_resolve.py <registry>``
with the tool payload on **stdin**. It is a helper, not a hook: nothing registers it,
and it is never executed directly (hence no shebang).

Why this is a file and not a heredoc
------------------------------------
This logic used to live in a ``<<'PY'`` heredoc inside ``dispatch.sh``. The heredoc
occupied stdin, so the payload had to travel through the ENVIRONMENT instead — and
once it crossed ``ARG_MAX`` (1048576) ``execve`` returned ``E2BIG``, the resolver
failed to start, and a blocking event exited 2. Writing a >1 MB file was therefore
refused, with a message naming neither the size nor the cause.

The rejected alternative matters as much as the fix. Spilling the payload to a temp
file and passing its path was planned, reviewed twice and abandoned: it introduces
the first payload-sized write in the dispatcher, hence a new ``RLIMIT_FSIZE`` kill
surface, so the boundary emitted ``rc -25`` (SIGXFSZ) where it had emitted a correct
fail-closed ``rc 2``. A signal-killed hook emits neither 0 nor 2, breaking hard rule
2, and the host plausibly reads it as NON-blocking — trading a fail-CLOSED usability
bug for a possible fail-OPEN safety bug. A pipe has neither an ``ARG_MAX`` nor a
file-size limit and writes nothing, so it has none of those failure modes.

Stdin is drained FIRST, before any path that can exit
-----------------------------------------------------
Both ``exit 3`` paths below (unreadable registry, illegal registry row) would
otherwise leave the writing ``printf`` holding an unread pipe, which SIGPIPEs it and
leaks ``printf: write error: Broken pipe`` onto hook stderr. Reading stdin up front
closes that separately-filed defect without a ``2>/dev/null`` that would also hide
real errors.
"""
import json
import os
import re
import sys

# FIRST, unconditionally: see the module docstring. Never move this below anything
# that can exit or raise.
#
# .buffer + surrogateescape, NOT sys.stdin.read(). Text-mode stdin decodes with
# errors='strict' under a normal user locale (LANG=en_US.UTF-8), so one invalid
# UTF-8 byte in a payload raised UnicodeDecodeError, this exited 1, and every
# handler was silently skipped -- 10 handlers to 0 on a non-blocking event. The
# transport this replaced read os.environ, which decodes with surrogateescape and
# CANNOT raise: an undecodable payload simply became `readable = False` and every
# guard ran and decided for itself. Preserving that is the whole point; a payload we
# cannot decode must not be a payload that disarms the dispatcher.
_RAW = sys.stdin.buffer.read().decode("utf-8", "surrogateescape")

try:
    reg = json.load(open(sys.argv[1]))
except Exception as exc:
    sys.stderr.write("registry parse failure: %s\n" % exc)
    sys.exit(3)

event = os.environ["EVENT"]
tool = os.environ.get("TOOL_NAME", "")

# Command text for `command_matcher`. settings.json wrappers read a TOP-LEVEL
# "command" while the documented payload nests it under tool_input, so both are
# accepted. `readable = False` means "payload unreadable" and is deliberately
# distinct from a command of "" ("no command"): an unreadable payload must NOT
# filter a guard out. Running a guard that did not need to run is a wasted
# subprocess; skipping one that did is the failure mode this phase exists to remove.
try:
    payload = json.loads(_RAW or "")
    if not isinstance(payload, dict):
        raise ValueError("payload is not an object")
    readable = True
    command = payload.get("tool_input", {}).get("command")
    if command is None:
        command = payload.get("command")
    command = "" if command is None else str(command)
    tool = payload.get("tool_name") or payload.get("name") or tool
except Exception:
    readable, command = False, ""

# REGISTRY INVARIANT: a command_matcher may appear ONLY on an `advisory` row.
# Anything else -> exit 3 -> fail closed. Enforced rather than assumed, because the
# skip-on-unreadable-payload rule below is only safe while such a row cannot block:
# an invariant the code depends on and does not enforce IS the defect.
for _ev, _rows in sorted(reg.get("events", {}).items()):
    for _r in (_rows if isinstance(_rows, list) else []):
        if isinstance(_r, dict) and (_r.get("command_matcher") or "") and \
                _r.get("tier", "advisory") != "advisory":
            sys.stderr.write("illegal registry row %r on %s: tier=%r declares a "
                             "command_matcher; only advisory rows may carry a "
                             "precondition\n" % (_r.get("id"), _ev, _r.get("tier")))
            sys.exit(3)

for row in reg.get("events", {}).get(event, []):

    # RELEVANCE FILTER: an unreadable payload cannot be filtered on, so every
    # handler runs and decides for itself.
    matcher = row.get("matcher") or ""
    if readable and matcher and not re.search(matcher, tool or ""):
        continue

    # PRECONDITION: a command_matcher is a PRECONDITION, not a convenience filter.
    # With an unreadable payload there is no command text, so the precondition
    # cannot be evaluated and the handler is NOT APPLICABLE -- skipped, not "run
    # anyway". This asymmetry with the tool matcher above is deliberate; the
    # rationale, including the pre-push full-suite stall it prevents, is recorded
    # above the invocation in dispatch.sh.
    cmd_matcher = row.get("command_matcher") or ""
    if cmd_matcher and (not readable or not re.search(cmd_matcher, command)):
        continue
    args = row.get("args") or []
    if any((" " in a or "\t" in a or "\n" in a) for a in args):
        sys.stderr.write("handler %s: args may not contain whitespace\n" % row["id"])
        sys.exit(3)
    sys.stdout.write("\t".join([
        row["id"], row["file"], row.get("runner", "bash"), row.get("tier", "advisory"),
        " ".join(args),
    ]) + "\n")
