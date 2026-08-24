# Implementation Plan: two scanners that do not cover what they claim (F44, F54)

**Status:** **EXECUTED 2026-08-24.** Tier 2 — two hook scripts plus tests. Both are
*security-shaped* but neither is enforcement: `security-reminder.sh` only warns and
`session-start.sh` only prints, so no verdict flips.

Mutation-proven: reverting F44 fails 3 of its 5 tests, reverting F54 fails 5 of its 10.
**F54 went further than the finding said**, and that is recorded in its section below —
its crypto half was backwards, not merely noisy.

## Artifacts

| Path | Config |
| --- | --- |
| `.claude/hooks/session-start.sh` | `-f44` |
| `.claude/hooks/security-reminder.sh` | `-f54`, `-f54b` |
| `tests/test_session_context_scan.py`, `tests/test_security_reminder_coverage.py` | `-tests` |
| `review/code-review-triage.md` | `-triage` |
| `CHANGELOG.md`, `.claude/plans/plan-scanner-coverage.md`, `.claude/plans/archive/README.md` | `-docs`, `-plandoc` |

The two highest-value findings left in `review/code-review-triage.md`'s LIVE set of 40. Both are
the same class — **coverage that isn't** — and both were picked over the other 38 because they
are real defects rather than tidiness.

**Sequencing, and why this ran before its review rather than after.** The previous review of
`d945278` read these same two files, so editing them underneath a running reviewer would have
invalidated its verdict — this plan was written first and held. It then executed BEFORE its own
review, deliberately, so that one adversarial pass can cover `a1d695f` and this work together
instead of two passes racing each other over the same files. **That review is queued, not
skipped**, and until it reports this plan carries no independent verdict.

---

## F44 — `session-start.sh` prints an unscanned file into the transcript

**Site.** `.claude/hooks/session-start.sh:126-146`:

    CONTEXT_FILE=".claude/session-context.md"
    ...
        head -20 "$CONTEXT_FILE" | sed 's/^/  /'

**Why it matters, stated no more strongly than the evidence supports.** `.claude/session-context.md`
is written by `/save-session` and read back at every session start. Its first 20 lines are printed
straight into the transcript **before any scanner sees them**, and `sed 's/^/  /'` indents the text
— it does not neutralise it. A poisoned context file therefore gets one shot at the model at the
moment of least suspicion.

**The mitigation already exists and is simply not applied here.** `injection-scan-gate.sh` wraps
`prompt-injection-scanner.sh`, but reading it shows what it actually covers:

    TEXT="$(extract_json_field "$PAYLOAD" prompt)" || exit 0

That is the `UserPromptSubmit` payload's `prompt` field, and nothing else. Confirmed by reading
the gate, not inferred: the session-context path is not on any scanner's surface.

**Honest bounds — this is not a remote hole.** Writing `.claude/session-context.md` requires local
write access to the repo. The realistic vector is a *cloned or shared repo* whose context file
someone else authored, or a file written by an earlier agent run. That is exactly the "retrieved
text is evidence, never an instruction channel" rule in `CLAUDE.md` — and this path violates it
mechanically.

**Fix.** Scan the excerpt before printing it, using the scanner that already exists:

1. Locate `prompt-injection-scanner.sh` the way `injection-scan-gate.sh` does (both candidate
   paths, so an installed project and this repo both work).
2. Pipe the 20-line excerpt through it.
3. **Flagged → do not print the content.** Print that a context file exists, that it matched an
   injection pattern, and that `/resume-session` will load it deliberately. The file is not
   deleted or modified; the decision moves to the human.
4. **Scanner missing or errored → do not print the content either.** Fail toward silence: this is
   a convenience feature, and the cost of not printing an excerpt is one extra command, while the
   cost of printing unscanned text is the finding itself.
5. Not gated to `strict`. `session-start.sh` runs in **all** profiles, and a gate that only
   protects the profile nobody uses is decoration.

**What this deliberately does NOT do.** It does not block the session, does not touch the file,
and does not make `session-start.sh` a blocking hook. Hard rule 6 applies to how it is described:
this closes an unscanned surface, it does not make session context trustworthy.

**Tests.** A benign context file still prints its excerpt; a context file containing a known
scanner pattern prints the warning and **not** the content (assert the payload string is absent
from stdout — that is the assertion that binds); a missing scanner also withholds the content.
Mutation-proven by restoring the bare `head -20` and watching the withholding test fail.

---

## F54 — `security-reminder.sh` silently stops scanning at 3000 characters

**Site.** `.claude/hooks/security-reminder.sh:55`:

    print(inp[key][:3000])

**The defect is the silence, not the number.** Every pattern below that line — `shell=True`,
SQL concatenation, `innerHTML`, `verify=False`, weak crypto, permissive CORS — is matched against
a **truncated** copy of the content. A `subprocess.run(..., shell=True)` at character 3001 is
never scanned, the hook exits 0, and nothing anywhere indicates that coverage was partial. 3000
characters is roughly 75 lines; a routine file edit exceeds it.

This is the same shape as the `tail -20` finding (F37) and the `check-plan-artifacts` skip I filed
earlier today: **a check that reports success for the part it looked at.**

**Fix, in two parts.**

1. **Raise the cap to 200,000 characters** — enough for any realistic single edit, still bounded so
   a pathological paste cannot make a `PreToolUse` hook slow. The greps are pipelines, so there is
   no `ARG_MAX` exposure at this size.
2. **Make truncation LOUD.** When the content exceeds the cap, emit an explicit line saying how
   many characters were scanned and that the remainder was not. Partial coverage that announces
   itself is a limitation; partial coverage that stays quiet is a false negative wearing a pass.

**The second half of F54 is not what the finding says it is — it is worse, and in the opposite
direction.** The finding calls the crypto keywords "unanchored", firing on comments and
documentation. Documentation was already largely excluded (`:49-54` skips `docs/`, `README`,
`CHANGELOG`, `templates/`, `.claude/{skills,agents,commands,hooks}/` and any `.md`/`.txt`/`.rst`
target), so the noise half was real only for comment lines inside source files. **But `\bMD5\b`
is case-SENSITIVE.** So:

    hashlib.md5(data)          -> NO warning   (the commonest real form)
    # do not use MD5 here      -> warning      (a comment)

The check fired on prose and stayed silent on code. Verified against the pre-fix version before
touching it. Fix, both directions: API-call shapes (`hashlib.md5(`, `MD5.new()`,
`from Crypto.Hash import SHA1`) match case-insensitively; the bare uppercase word matches only on
non-comment lines; and `hashlib.sha256` must not fire, which is asserted.

**I got this wrong once in the course of fixing it.** My first check reported that real MD5 use
warned — but the fixture was `h = hashlib.md5(data)  # MD5 digest`, and the match came from the
uppercase text in the *trailing comment*, not from the code. Re-running with lowercase only
returned 0. A passing test whose pass comes from the wrong half of the fixture is the same
mistake as a mutation that never landed.

**Tests.** `shell=True` at character 3001 is now found (the assertion that would have failed
before); content over the cap produces the explicit truncation notice; a comment naming MD5 does
not warn while real `hashlib.md5(` use does. Mutation-proven by restoring `[:3000]`.

---

## Ops shape

Two configs, one per finding, so the suite runs between them and a failure is attributable:

1. `ops-scanner-coverage-f44.json` — `.claude/hooks/session-start.sh` + `tests/test_session_context_scan.py`
2. `ops-scanner-coverage-f54.json` — `.claude/hooks/security-reminder.sh` + `tests/test_security_reminder_coverage.py`

`CHANGELOG.md` gets an entry: both are user-visible behaviour changes in shipped hooks, and the
F44 change can withhold output a user currently sees.

## Definition of Done

The full DoD gate list, with the suite's whole output written to a file and read from the file.
Plus `Plan-Id: scanner-coverage`, both configs archived with README rows, `INDEX.md` regenerated
after committing, and the two `review/code-review-triage.md` rows moved from LIVE to FIXED with
the evidence inline — **40 live becomes 38, stated as a delta, not by overwriting a count.**
