#!/usr/bin/env python3
"""review-panel.py - deterministic driver for the /review critic panel (EGM personas).

The panel (plan-design-critic + plan-readiness-critic beside reviewer) was prose in
review.md, and prose did not run: 92/95 sessions spawned reviewer alone, critics got
coordinator briefs instead of the plan path, and `=== PANEL ===` was printed 0/135 times.
This script owns the parts a model kept skipping:

  review-panel.py prompts [--no-panel] [PLAN]
      Resolve the plan (PLAN, else the newest .claude/plans/plan-*.md that is not a
      *.review.md / *.panel*.md), decide panel on/off (off: --no-panel, or env
      CK_REVIEW_PANEL in {0, off, false}), log one row to
      .claude/hooks/.state/review-panel.jsonl and print:
          PLAN: <realpath>
          PANEL: on|off (<why>)
          CRITIC_PROMPT: Plan: <realpath>. Review it.
      Exit 1 with `ERROR: no plan` when none is found.

  review-panel.py merge PLAN --reviewer REF [--critic NAME=REF]...
      REF = a Task agentId (transcript located like review-record.py does) or a file.
      Validates each critic reply (last non-empty line is a PANEL line, <= 3,000 chars),
      drops findings the reviewer's ISSUES already cover (shared path-like token AND >= 3
      shared content words of >= 5 letters), numbers the rest <critic>-r<round>-<n>, and
      applies the EGM stop rule (two consecutive clean rounds; no new Blocker; cap 5).
      Rounds are kept per plan in .claude/hooks/.state/review-panel-rounds.json and only
      advance when the plan bytes change. Advisory: exit 0 always, 2 on usage errors.

stdlib only, py3.9.
"""
import argparse
import datetime
import glob
import hashlib
import importlib.util
import json
import os
import re
import sys

PANEL_RE = re.compile(r"^PANEL: (\d+) blocker, (\d+) major\s*$")
INCOMPLETE_RE = re.compile(r"^PANEL: incomplete\b")
MAX_CHARS = 3000
CAP = 5
OFF = {"0", "off", "false"}
CRITICS = ("plan-design-critic", "plan-readiness-critic")
FINDING_RE = re.compile(
    r"^\s*(?:[-*+]\s+|\d+[.)]\s+)?(?:\*\*\[?|\[)(Blocker|Major|Nit)\]?(?:\*\*)?\]?\s*:?\s*(.*)$",
    re.I)
PATH_TOKEN_RE = re.compile(r"[\w./-]+\.(?:md|py|sh|json|ts|js|yml|yaml)\b|§\S+")
WORD_RE = re.compile(r"[a-z]{5,}")


def _root():
    return os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()


def _state_dir():
    path = os.path.join(_root(), ".claude", "hooks", ".state")
    os.makedirs(path, exist_ok=True)
    return path


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _newest_plan():
    pattern = os.path.join(_root(), ".claude", "plans", "plan-*.md")
    plans = [p for p in glob.glob(pattern)
             if not p.endswith(".review.md") and ".panel" not in os.path.basename(p)]
    return max(plans, key=os.path.getmtime) if plans else None


def panel_state(no_panel):
    """(on, why)."""
    if no_panel:
        return False, "--no-panel"
    env = (os.environ.get("CK_REVIEW_PANEL") or "").strip().lower()
    if env in OFF:
        return False, "CK_REVIEW_PANEL=%s" % env
    return True, "default"


def cmd_prompts(args):
    plan = args.plan or _newest_plan()
    if not plan or not os.path.isfile(plan):
        print("ERROR: no plan")
        return 1
    plan = os.path.realpath(plan)
    on, why = panel_state(args.no_panel)
    row = {"ts": _now(), "plan": plan, "plan_sha256": _sha(plan),
           "panel": "on" if on else "off", "why": why}
    try:
        with open(os.path.join(_state_dir(), "review-panel.jsonl"), "a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError as exc:
        print("WARNING: panel log not written: %s" % exc, file=sys.stderr)
    print("PLAN: %s" % plan)
    print("PANEL: %s (%s)" % ("on" if on else "off", why))
    print("CRITIC_PROMPT: Plan: %s. Review it." % plan)
    return 0


# ---------------------------------------------------------------- reading replies

def _review_record():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "review-record.py")
    spec = importlib.util.spec_from_file_location("ck_review_record", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _last_assistant_text(transcript, rr):
    last = None
    with open(transcript, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            message = rec.get("message") if isinstance(rec, dict) else None
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            for text in rr._message_texts(message):
                if text.strip():
                    last = text
    return last


def read_reply(ref, reviewer=False):
    """Reply text for REF (a file, or a Task agentId/transcript), or None."""
    if os.path.isfile(ref) and not ref.endswith(".jsonl"):
        with open(ref, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    try:
        rr = _review_record()
        transcript = rr._task_transcript(ref)
    except Exception:  # noqa: BLE001 - a broken helper means "no transcript"
        return None
    if transcript is None:
        return None
    if reviewer:
        return rr._task_review(transcript)[0]
    return _last_assistant_text(transcript, rr)


def validate(reply):
    """(status, reason): status in valid | incomplete."""
    if reply is None or not reply.strip():
        return "incomplete", "empty or missing reply"
    if "API Error" in reply:
        return "incomplete", "API error"
    if len(reply) > MAX_CHARS:
        return "incomplete", "over %d chars (%d)" % (MAX_CHARS, len(reply))
    last = [ln for ln in reply.splitlines() if ln.strip()][-1].strip()
    if INCOMPLETE_RE.match(last):
        return "incomplete", "critic reported: %s" % last
    if not PANEL_RE.match(last):
        return "incomplete", "no PANEL line"
    return "valid", ""


def findings(reply):
    out = []
    for line in reply.splitlines():
        m = FINDING_RE.match(line)
        if not m:
            continue
        sev = m.group(1).capitalize()
        if sev in ("Blocker", "Major"):
            out.append((sev, m.group(2).strip().strip("*").strip()))
    return out


def reviewer_issues(text):
    if not text:
        return []
    lines, inside = [], False
    for line in text.splitlines():
        if line.strip().startswith("ISSUES:"):
            inside = True
            continue
        if inside:
            if line.strip().startswith("==="):
                break
            if line.strip():
                lines.append(line)
    return lines


def _tokens(text):
    return set(PATH_TOKEN_RE.findall(text)), set(WORD_RE.findall(text.lower()))


def covered(finding, issues):
    paths, words = _tokens(finding)
    for issue in issues:
        ipaths, iwords = _tokens(issue)
        if paths & ipaths and len(words & iwords) >= 3:
            return True
    return False


def _norm(text):
    return " ".join(re.sub(r"[^\w\s]", " ", text.lower()).split())


# ---------------------------------------------------------------- rounds + stop rule

def record_round(plan, sha, blockers, majors):
    """Round number k and the full round list for this plan (appends on new bytes)."""
    path = os.path.join(_state_dir(), "review-panel-rounds.json")
    try:
        with open(path) as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    rounds = data.setdefault(plan, [])
    row = {"sha": sha, "blockers": sorted(set(blockers)), "majors": majors, "ts": _now()}
    if rounds and rounds[-1].get("sha") == sha:
        rounds[-1] = row
    else:
        rounds.append(row)
    try:
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(data, fh, indent=1, sort_keys=True)
        os.replace(tmp, path)
    except OSError as exc:
        print("WARNING: rounds not saved: %s" % exc, file=sys.stderr)
    return len(rounds), rounds


def stop_line(rounds):
    k = len(rounds)

    def clean(r):
        return not r.get("blockers") and not r.get("majors")

    cur = rounds[-1]
    if k >= 2 and clean(cur) and clean(rounds[-2]):
        return "STOP: 2 consecutive clean rounds"
    if k >= 2 and not clean(cur) and set(cur.get("blockers", [])) <= set(rounds[-2].get("blockers", [])):
        return ("STOP: round %d raised no new Blocker — stop re-reviewing; carry remaining "
                "Majors as follow-ups" % k)
    if k >= CAP:
        return "CAP: round %d — list open findings and ask the owner" % k
    return "CONTINUE: fix uncovered Blockers, then re-run /review"


def cmd_merge(args):
    plan = os.path.realpath(args.plan)
    if not os.path.isfile(plan):
        print("ERROR: no plan %s" % args.plan, file=sys.stderr)
        return 2
    critics = []
    for spec in args.critic or []:
        if "=" not in spec:
            print("ERROR: --critic takes NAME=REF, got %r" % spec, file=sys.stderr)
            return 2
        critics.append(tuple(spec.split("=", 1)))
    issues = reviewer_issues(read_reply(args.reviewer, reviewer=True))

    notes, uncovered = [], []
    for name, ref in critics:
        reply = read_reply(ref)
        status, reason = validate(reply)
        if status != "valid":
            notes.append("%s: incomplete (%s)" % (name, reason))
            continue
        for sev, text in findings(reply):
            if not covered(text, issues):
                uncovered.append((name, sev, text))

    blockers = [_norm(t) for _, s, t in uncovered if s == "Blocker"]
    majors = sum(1 for _, s, _ in uncovered if s == "Major")
    k, rounds = record_round(plan, _sha(plan), blockers, majors)

    counters: dict = {}
    print("=== PANEL ===")
    for note in notes:
        print(note)
    for name, sev, text in uncovered:
        counters[name] = counters.get(name, 0) + 1
        print("%s-r%d-%d %s: [%s] %s" % (name, k, counters[name], name, sev, text))
    print("PANEL: %d blocker, %d major (uncovered); round %d; %s"
          % (len(blockers), majors, k, stop_line(rounds)))
    print("=== END PANEL ===")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="review-panel.py")
    sub = parser.add_subparsers(dest="cmd")
    p = sub.add_parser("prompts")
    p.add_argument("--no-panel", action="store_true")
    p.add_argument("plan", nargs="?")
    m = sub.add_parser("merge")
    m.add_argument("plan")
    m.add_argument("--reviewer", required=True)
    m.add_argument("--critic", action="append")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    if args.cmd == "prompts":
        return cmd_prompts(args)
    if args.cmd == "merge":
        return cmd_merge(args)
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
