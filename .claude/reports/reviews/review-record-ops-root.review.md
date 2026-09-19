REVIEW REPORT
=============

Plan: .claude/plans/plan-review-record-ops-root.md
Ops Config: .claude/plans/ops-review-record-ops-root.json
Reviewer: reviewer-agent (full review, Tier 3: approval-gate security surface)
Date: 2026-09-19

Skills: no Skill tool in this runtime, so using-superpowers and validate-operations-config were not
loaded. The review followed reviewer.md and _shared/reviewer-reference.md directly.

PRE-VALIDATION: PASS
  [x] plan.md exists
  [x] ops.json exists; parseable (10 code_edit ops, baseline stamped for all 10 paths)
  [x] Operations match steps: Step1 = op1, Step2 = op2, Step3 = op3, Step4 = ops 3-9, Step5 = op10.
      No orphaned ops and no phantom steps.
  [x] Required sections present (Overview, Steps, Testing Strategy, Rollback Plan, Risk Assessment)
  [x] No hardcoded secrets. No deletions.

SCORES:
  Plan Quality:  [█████████████████████░░░░] 87/100 (weight: 40%)
  Architecture:  [██████████████████████░░░] 90/100 (weight: 30%)
  Security:      [█████████████████████░░░░] 84/100 (weight: 30%)
  ──────────────────────────────────────
  TOTAL:         [█████████████████████░░░░] 87.0/100

DECISION: REVISE (one MAJOR finding open; score below 90)

VERIFIED AGAINST THE REPO (these are no longer UNVERIFIED items in the plan)
  - Every call site of record_paths, _records_dir, _rejections_dir, emit_brief, author_path,
    load_author and load_author_role is covered by op 1: review-record.py:269, 274, 327, 388, 626,
    662, 796, 902, 945, 958, 961, 968, 1004, 1029, 1034, 1074, 1082, 1141, 1184, 1188. The only
    outside caller is execute-json-ops.py:985, which op 2 covers. The rejection-query
    `_rejections_dir()` calls (1347, 1475, 1617, 1718, 1736) stay on the cwd walk, matching the
    declared out-of-scope items.
  - Exit 7 is unused. The only literal return in the 5-7 range is `return 5` (review-record.py:793),
    and the file has no EXIT_ constants.
  - The refusal sits after the `--only-non-approving` exit-5 block (review-record.py:788-793) and
    before `slug = ops_slug(...)` (795). Nothing is written before it, so "writes nothing" holds by
    construction. `verdict_origin = "owner"` survives into the record (811, `verdict_origin or
    "rubric"`).
  - `os` and `subprocess` are already imported (review-record.py:52, 54), so the new `_git_toplevel`
    compiles. `hasattr` still fails closed on a module without `_records_root`
    (execute-json-ops.py:977-982).
  - `args.config` is made absolute before the chdir (execute-json-ops.py:1570, 1579). "does not
    authorise execution" is the executor's code-4 text (1012). An explicit `--root` skips the
    cross-tree refusal (1433-1437), so test (e)'s `--root <main>` with a sibling config is a legal run.
  - The test anchor at tests/test_review_record.py:725 is the last line of the file, so op 3's
    add_after really appends at module level. Helpers `SCRIPTS_DIR`, `RECORD`, `REVIEW_OK`,
    `_run(stdin=)` and `_fixture` exist with the shapes the new tests use (lines 13-49). `_fixture`
    creates `.claude/`, so negative twin (f) resolves to tmp_path.
  - The bare-APPROVED caller inventory is complete: both quote styles across the repo return only
    the sites ops 3-9 edit. No hook in .claude/hooks references review-record. No test asserts
    `verdict_origin == "rubric"` on a bare approval (test_rejection_briefs.py:318-321 uses
    REVISE). The write_verdict signature test (test_rejection_briefs.py:814-816) is a subset
    check, so the new kwarg passes it.
  - `## [Unreleased]` is unique (CHANGELOG.md:13).
  - Mutant traces (predicted, NOT executed; this agent has no Bash). Mutant 1 turns tests (a) and
    (d) red. Mutant 2 turns only (e) red: the config is outside plans/ and the slug has no plan
    doc, so `_gate_applies` is False. The plan's reasoning is sound. Mutant 3 turns test
    `bare_approval_is_refused` red.

FINDINGS

  Major (must fix):
    1. The goal's security property is not delivered, and the plan does not say so.
       - The stated goal is "an agent can never self-issue an approval". But `--owner-approved`
         is an ordinary argparse flag (op 1, parser edit), and nothing checks who passed it. An
         agent with Bash can pass it, or can pipe its own `=== REVIEW ===` block through
         `--from-review -`.
       - The refusal stderr (op 1, write_verdict edit) names `--owner-approved` to the agent it
         has just refused.
       - The help text, the plan Overview ("explicit human-only") and the CHANGELOG bullet all
         present it as a human-only path.
       - Risk Assessment leaves out this residual risk, which is the main one. Hard rule 6
         requires honest security framing.
       - Fix, either one:
         (a) Make it binding. Add a PreToolUse Bash deny (exit 2, stderr) for `review-record.py`
             commands carrying `--owner-approved`. The user's own `!` shell does not go through
             PreToolUse, so the human path survives. Add a behavioural hook test.
         (b) Reframe it everywhere (plan Overview and Risk, the CHANGELOG bullet, the help text,
             the write_verdict comment) as an advisory speed bump that redirects agents to a
             reviewer and is not enforcement. Drop the flag name from the agent-facing stderr and
             point a human at `--help` instead.

  Minor (should fix):
    2. The writer and the executor disagree for ops files outside git.
       - write_verdict falls back to the plan's git toplevel. The executor's pre-lookup,
         `_records_root(config_file)` (op 2), passes no plan and so falls back to the cwd walk.
         check_approval also hands cmd_check `plan="plan-<slug>.md"`, a path relative to the
         cwd (execute-json-ops.py:997).
       - Failure case: an outside-git config, a plan in tree A, and the executor run in tree B.
         The lookup misses a REJECTED record and, with no plan doc for the slug, the config runs
         ungated. That is the fail-open class test (e) exists to kill.
       - The `_records_root` docstring's "they cannot disagree" is therefore false.
       - Fix: drop the plan fallback (ops toplevel, then the cwd walk), or have check_approval
         pass the real plan path.
    3. The plan and ops.json disagree on the edit count. The plan says "op 1, 23 edits"; ops.json
       op 1 has 25. The plan .md predates the final ops.json; update the count.
    4. The CHANGELOG heading mislabels existing entries. Op 10 inserts `### Changed` directly
       under `## [Unreleased]` (CHANGELOG.md:13). That section has no `###` subsections: its
       ~355 lines are flat bullets down to line 369. Every existing Unreleased entry would then
       read as "Changed". Drop the heading and add plain bullets wrapped like their neighbours.
    5. `verdict_origin: "owner"` is a new value. Readers of that field (the flow-analyst trend
       rules, rejection stats) know rubric, gate-token and reconstructed; it is unverified
       whether they handle or exclude "owner". Grep the consumers, or document the value next to
       the `--verdict-origin` choices (review-record.py:1771-1774).

  Notes:
    - The local `_git_toplevel` copy is well justified: no import cycle, and the tree gate keeps
      working when this module is unusable. The optional `root=None` defaults keep outside callers
      unchanged.
    - The plan says the validator was NOT RUN. The caller reports the baseline stamped. I
      confirmed the multi-occurrence anchors (`author_path(slug)` x3, `_rejections_dir()` x5) are
      disambiguated with context, but mechanical uniqueness proof is the validator's job.

FOLLOW_UPS: mypy on the untyped `_git_toplevel(start)` / `_records_root` / `root=None` params
  (unverified; depends on the mypy config); the full suite and the mutation runs belong to
  code-reviewer (nothing was executed here).

FEEDBACK FOR PLANNER:
  - Resolve Major 1 with (a) or (b). Option (b) is the smaller edit and still makes the plan
    honest.
  - Fix Minor 2 by removing the plan fallback in `_records_root`. That makes the "one root"
    claim true.
  - Fix the edit count (Minor 3) and the CHANGELOG heading (Minor 4).
  - The ops.json is otherwise accurate against the tree. Re-stamp after editing (stamp before
    recording a verdict).

=== REVIEW ===
SCORE: 87
DECISION: REVISE
CRITICAL_MAJOR_COUNT: 1
ISSUES:
- [MAJOR] --owner-approved is agent-typeable, the refusal stderr names it, --from-review - accepts agent-authored blocks; goal "agent can never self-issue" unmet and unstated in Risk — enforce via PreToolUse deny or reframe as advisory
- [MINOR] outside-git ops: write falls back to plan toplevel, executor pre-lookup/cmd_check use cwd; can miss a REJECTED record and run ungated; _records_root "cannot disagree" is false — drop the plan fallback
- [MINOR] plan says op 1 has 23 edits; ops.json op 1 has 25
- [MINOR] CHANGELOG op inserts ### Changed above ~355 lines of flat Unreleased bullets, relabelling every existing entry — use plain bullets
- [MINOR] new verdict_origin value "owner" unverified against flow-analyst/rejection-stats consumers
=== END REVIEW ===
