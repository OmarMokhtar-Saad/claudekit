# Implementation Plan: the 14-hook `log()` dedup

**Status:** **PARTIALLY EXECUTED 2026-08-24** — owner approved **item 3 only**, the three
`$LOG` hooks. Items 1, 2 and 4 were deliberately NOT done and remain open; the reasoning is in
"Why this might be the wrong thing to do" below, which is the section that produced the
decision.

Job 6 of handoff 9. Findings F38 / F106 in `review/code-review-triage.md`. **Deduplication with
no user-visible defect behind it** — that is the honest framing, and it is why this was deferred
rather than done, twice.

## Measured, not estimated

    $ 14 definitions, 7 distinct bodies, 4 behavioural families

| Family | Hooks | Detail |
| --- | --- | --- |
| Appender **+ stderr echo** on ERROR/WARN | 6 — `check-comment-replacement`, `post-implement`, `pre-commit`, `pre-plan`, `pre-push`, `prompt-injection-scanner` | `local level="$1"; shift`, appends, then `echo "[$HOOK_NAME] $*" >&2` for ERROR/WARN |
| Plain appender, no stderr | 2 — `auto-checkpoint`, `file-guard` | byte-identical to the above minus the stderr branch |
| Two-positional one-liner | 2 — `cost-tracker`, `desktop-notify` | `log() { echo "… [$1] $2" >> "$LOG_FILE"; }` — **drops `$3` onwards silently** |
| Hardcoded name, writes **`$LOG`** | 3 — `format-typecheck`, `security-reminder`, `session-start` | each hardcodes its own name, so 3 distinct bodies; all write `$LOG`, not `$LOG_FILE` |
| Delegates to `hlog` | 1 — `commit-quality` | `log() { hlog "$1" "$2"; }` — the target state, and note it also truncates at `$2` |

The handoff's "four distinct implementations" is right at the **family** level; by exact body
there are **seven**, because the three hardcoded-name variants differ from each other. Both
numbers are true of different questions.

`lib.sh` already ships the target:

    hlog() {
        local level="$1"; shift
        local name="${HOOK_NAME:-hook}"
        local logf="${LOG_FILE:-$(resolve_root)/.claude/hooks/hooks.log}"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$name] [$level] $*" >> "$logf" 2>/dev/null
    }

`hlog` is a strict superset of every family: it defaults the name, defaults the log path, and
uses `$*` so nothing truncates.

## The risk, which is the actual content of this plan

**Only 2 of the 14 source `lib.sh`** — `pre-commit.sh` and `commit-quality.sh`. Delegating means
adding a `. lib.sh` line to **12** hook scripts, and the list includes `pre-commit`, `pre-push`,
`prompt-injection-scanner` and `file-guard`. Each one then inherits **every other definition in
`lib.sh`**, not just `hlog`: `resolve_root`, `extract_json_field`, `deny`, and whatever lands
there later.

That is the part worth the owner's attention. `deny()` in particular is a *blocking* helper
(`exit 2`), and sourcing it into a hook that currently has no blocking path changes what a
name collision can do. A hook defining its own `deny` or `resolve_root` today would have it
silently replaced or replace `lib.sh`'s, depending on source order.

**Three behaviour changes are unavoidable if this is done as a straight delegation:**

1. The 2 plain-appender hooks **gain** stderr output on ERROR/WARN. `auto-checkpoint` and
   `file-guard` would start writing to stderr where they are silent today — visible in the
   transcript.
2. The 3 `$LOG` hooks change target variable. If any caller sets `$LOG` but not `$LOG_FILE`,
   their entries move file. (F107: **three** `LOG_FILE=` forms exist in this directory, so this
   is not hypothetical.)
3. The 3 truncating hooks (`cost-tracker`, `desktop-notify`, `commit-quality`) stop dropping
   arguments past `$2`. Strictly better, and still a change in output.

## Proposed shape, if approved

Ordered by risk, smallest first, each its own ops config so the suite runs between them:

1. The 2 plain appenders and the 6 appender+stderr hooks → `. lib.sh` + delete the local `log()`.
   These already match `hlog` semantically; item 1 above is the only visible delta.
2. The 3 two-positional hooks → same, accepting the un-truncation.
3. The 3 `$LOG` hooks → same, **plus** normalising `$LOG` to `$LOG_FILE` in each file, so item 2
   cannot bite.
4. `commit-quality.sh`'s `log() { hlog "$1" "$2"; }` → call `hlog` directly, deleting the shim.

**Before any of it: a collision audit.** For each of the 12, grep for a local definition of every
name `lib.sh` exports and stop if any collide. I have not run that audit — it is the first task
if this is approved, and its result could reduce the scope.

**Test shape.** Per family, a behavioural test invoking the real hook with a real payload and
asserting the log line lands in the right file with the right hook name — plus, for family 3, an
argument past `$2` surviving. Mutation-proven by reverting one hook to its local `log()` and
watching the test fail.


## Artifacts — EXECUTED 2026-08-24, owner-approved "item 3 only"

Scope as approved: **the three `$LOG` hooks only.** Items 1, 2 and 4 were NOT done.

| Path | Config |
| --- | --- |
| `.claude/hooks/format-typecheck.sh` | `ops-hook-log-dedup.json` |
| `.claude/hooks/security-reminder.sh` | `ops-hook-log-dedup.json` |
| `.claude/hooks/session-start.sh` | `ops-hook-log-dedup.json` |
| `tests/test_hook_log_delegation.py` | `ops-hook-log-dedup-test.json`, `-test2.json` |

**The collision audit the plan promised was run first** and came back clean: each of the three
defines only `log()`, and none collides with any of `lib.sh`'s eleven exports (`resolve_root`,
`hlog`, `extract_json_field`, `deny`, `ck_*`).

**My behavioural test was vacuous on its first draft, and the mutation proof is what showed it.**
Restoring the local `log()` in `session-start.sh` failed only the two *structural* assertions;
`test_logs_land_beside_the_hook_not_in_the_cwd` still passed against the defect. Cause: the old
code appended with `2>/dev/null`, so with no `.claude/hooks/` directory in the foreign cwd the
write failed silently and the "no stray log" assertion was trivially true. The fixture now
creates that directory on purpose, and the same mutation fails **three** tests. A test that
passes against the defect it names is worse than no test.

## Why this might be the wrong thing to do

Stated plainly, because the plan is a decision aid and not an advocacy document:

- **No user-visible defect behind it.** All 14 implementations work. The finding is that they
  *could* diverge, and F107 shows they already have in the log-path variable — but nothing is
  broken today.
- **It widens the blast radius of `lib.sh`.** Today an error in `lib.sh` breaks 11 hooks; after
  this it breaks 23. `lib.sh` becomes load-bearing for `pre-push` (which runs the full test
  suite) and `file-guard`.
- **The 16 downstream repos consume these hooks.** A `. lib.sh` line is a new file dependency in
  every one of them, and fleet-sync is separately owner-gated.
- The counter-argument, which is real: **half a refactor is a trap.** `lib.sh` exists, so the
  next maintainer will reasonably assume it is authoritative, edit `hlog`, and change the
  behaviour of 2 hooks out of 14. That is how the divergence gets *worse* rather than staying
  flat.

**My recommendation: approve item 3 only** (the three `$LOG` hooks), because that one has a
defect behind it — F107's third log-path form is a real inconsistency, and `command-log-audit.sh`'s
cwd-relative `AUDIT_LOG` (F55) is the same class already causing an audit trail to land in the
wrong directory. Items 1, 2 and 4 are tidiness on working code, and tidiness that widens a blast
radius across 16 downstream repos should wait for a reason. **The owner's call, either way.**
