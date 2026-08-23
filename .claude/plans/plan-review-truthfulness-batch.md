# plan-review-truthfulness-batch — the three non-blocking findings of PR #20's composed review

Findings MAJ-1, MAJ-3, MIN-1, MIN-4, MIN-5 from the composed-diff review (REJECTED, 82/100).
The blocking finding is handled separately in `plan-uninstall-partial-owned-deadend.md`.

## MAJ-1 — the readiness score ranks a `--minimal` install above the `--full` superset of it

Measured, same machine, same kit, two fresh installs:

```
MINIMAL:  Readiness: 100/100   --min-score 100 -> rc=0
FULL:     Readiness:  95/100   --min-score 100 -> rc=1 ;  --min-score 96 -> rc=1
```

Skips leave the denominator, so `--minimal` removes exactly the checks that can *warn*
(skills, registry, hooks, settings.json) while `--full` keeps the three blank project-command
warnings it ships with by design — a fact this branch's own test pins
(`tests/test_doctor_gate.py:451`). `docs/cli.md:54` sells `--min-score` as "a fleet-wide floor
in CI", and no floor can express "a complete kit": 96+ rejects the more complete install, 95
and below is cleared by the less complete one. `_readiness_score`'s docstring contract ("must
neither inflate nor depress") holds absolutely and breaks relatively.

**Decision, and why the reviewer's preferred fix is refused.** The reviewer's option (b) was to
make the three unconfigured project commands a `"skip"` on an install whose manifest shows they
were never configured, making the fresh-full baseline 100. Rejected: those warnings are the
mechanism that gets a user to fill in `build/test/lint_cmd`, and `install.sh` closes by saying
that `ck doctor --strict` exiting 1 on them is *deliberate*. Turning the nag into a skip buys a
comparable number by removing the only thing that asks for the configuration.

So take option (a) and make the number honest instead of comparable: print the applicable
count next to it, and say plainly in `docs/cli.md` that scores compare within an install mode,
not across them. A `--min-score` floor is then a per-mode floor, which is what it actually is.

## MAJ-3 — `cmd_adapt`'s docstring asserts the opposite of what the fresh branch does

`main.py:1084-1086` says the Fresh branch "reports that `ck init` must run first" and that
invoking the installer is "deferred and NOT owner-approved ... a NAMED skip". Forty-six lines
below, that branch calls `cmd_init(mode="full", force=False, yes=True)`; measured on an empty
directory, `ck adapt` writes `.claude/`, `.gitignore`, `.agentignore` and exits 0. The behaviour
is right, justified at 1133-1140, tested and in the CHANGELOG. The *comment* is false — and this
repo's review process treats these rationale comments as evidence, so a load-bearing comment
contradicting its own function is worse than none. Same omission in `--help` (:2098-2099), which
promises only "Configure ClaudeKit for this project".

## MIN-1 — `check-plan-artifacts.py` checked ZERO configs in this PR's own CI run

```
$ python3 scripts/check-plan-artifacts.py --check
check-plan-artifacts: no ops configs to check      rc=0
```

Executed configs move to `.claude/plans/archive/`, which the glob at :169-172 does not cover, so
the gate that mechanises the three-entry recurrence ratchet is inert on the run that gates the
merge. Pointed at the archive it works and is honest (`OK (92 config(s))`). Second, related
hole: a config that resolves to no plan is a silent PASS by design (Tier 1 ships one), so a plan
file renamed by accident produces a green run with every operation unchecked, indistinguishable
in the output from a real pass.

Fix: recurse into the archive, and print the number of *paths* verified plus a `NOTE:` naming
each config that resolved to no plan — a vacuous run must not look identical to a real one.

## MIN-4 — two literals kept in step by comment only

`main.py:1400` says PARTIAL_OWNED "MUST STAY IN STEP WITH claudekit.adapt.PARTIAL_OWNED_RELS".
Nothing compares them. Divergence makes `adapt` write into a file `uninstall` deletes — the exact
class the comment names. One assertion closes it.

## MIN-5 — the floor gate's rationale cites a fact that is not true

`check-context-floor.py:83-84` says "CLAUDE.md's command block prescribes the bare form".
`CLAUDE.md:22` and `ci.yml:90` both prescribe `--check`. The fix was right; the stated motive
was not, and the real one is better: the flag was accepted and then silently ignored.

## Files
- `src/claudekit/cli/main.py` — score line + docstring caveat, adapt docstring, adapt `--help`
- `docs/cli.md` — the within-mode caveat
- `scripts/check-context-floor.py` — comment
- `scripts/check-plan-artifacts.py` — archive coverage + unresolved-plan NOTE
- `tests/test_doctor_score.py`, `tests/test_check_plan_artifacts.py`, `tests/test_adapt.py`
- `CHANGELOG.md` — delete the 17 duplicated `[Unreleased]` lines, and correct the
  `Readiness:` line format the surviving entry describes

(`CHANGELOG.md` was missing from this list until review round 2, which means the gate
this very change repairs FAILED on this change — `plan-omits-its-own-artifact`, the exact
class it mechanises. Recorded rather than quietly fixed: it is the strongest evidence the
gate now binds.)

## Mutation proof
- Score: assert the doctor output carries the applicable count, not just `Readiness:`. Reverting
  the print leaves `Readiness: 95/100` and the test fails.
- Gate: assert the default run reports a non-zero config count. Reverting the rglob returns
  "no ops configs to check" and the test fails. A second test builds a config whose plan is
  missing and asserts the NOTE names it — reverting makes the run silently green.
- Drift: `set(main.PARTIAL_OWNED) == set(adapt.PARTIAL_OWNED_RELS)` fails the moment either moves.
