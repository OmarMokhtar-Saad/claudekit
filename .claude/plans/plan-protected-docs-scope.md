# Implementation Plan: scope the protected-docs pattern to named documents

`main`, planned at HEAD `2e954fe`. **Tier 3 — security surface.** Prerequisite for
task 008; owner approved the narrowing on 2026-08-23 after the blocker below was
measured. Revised after review round 1 (80/100 CONDITIONAL) — see § Review history.

## The blocker, measured

`shared.py:16` protects `*.md` by **basename, anywhere in the tree**
(`is_protected_file` runs `fnmatch` over `os.path.basename`). There is no override:
no flag, no env var, no per-operation escape — `grep -rn 'allow_protected|force_protected|CLAUDEKIT_.*PROTECT'` over the repo returns nothing.

    Operation 2 (file_delete): BLOCKED - Cannot delete protected file: templates/commands/analyze.md
       Protected patterns: .gitignore, *.md, Makefile, ...

**Receipts** (round-1 review would not take these on prose, and was right not to).
Both are reproducible from the repo root — the reviewer agents have no Bash, so the
commands are recorded here rather than only their output:

    $ python3 - <<'EOF'
    import json, glob
    total = md = 0
    for f in sorted(glob.glob('.claude/plans/archive/*.json')):
        try: d = json.load(open(f))
        except ValueError: continue
        for o in d.get('operations', []):
            if isinstance(o, dict) and o.get('type') == 'file_delete':
                total += 1
                md += o['path'].endswith('.md')
    print(len(glob.glob('.claude/plans/archive/*.json')), total, md)
    EOF

    $ for f in .claude/plans/ops-008-batch1/*.json; do
        python3 .claude/operations/scripts/validate-config-json.py "$f" >/dev/null 2>&1 \
          && echo PASS || echo FAIL
      done | sort | uniq -c


    $ # every file_delete ever recorded in an archived ops config
    archived configs scanned : 97
    file_delete operations   : 0
    of those ending in .md   : 0

    $ for f in .claude/plans/ops-008-batch1/*.json; do validate-config-json.py $f; done
    16 REJECTED, 3 APPROVED — every rejection is "Cannot delete protected file: *.md"

Zero deletions of any kind have ever run through this engine. The prose corpus is
100% markdown, so the Iron Law (implementation flows through the ops engine) and
hard rule 4 (protected files stay protected) together make task 008 — all four
batches — unexecutable.

## Change

Three edits, one idea: name the documents, don't glob the extension.

1. **`PROTECTED_PATTERNS`** — replace the `*.md` glob with the conventional
   identity-document set: `README.md`, `CHANGELOG.md`, `CLAUDE.md`, `AGENTS.md`,
   `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `LICENSE`,
   `LICENSE.md`, `NOTICE.md`, `MAINTAINERS.md`, `GOVERNANCE.md`, `AUTHORS.md`,
   `SUPPORT.md`. Bare `LICENSE` was never covered before and is added — the old
   glob protected `LICENSE.md` and permitted `LICENSE`, which no one intended.
2. **Case-insensitive matching.** `fnmatch.fnmatch` normalises case only on
   Windows, so on Linux CI the guard refused `README.md` and permitted
   `readme.md`, while on macOS it refused both. Measured before the change:
   `is_protected_file("makefile")` → `False`, `is_protected_file("Contributing.MD")`
   → `False`. That is a security control whose answer depends on the developer's
   filesystem. The `*.md` glob hid half of it; naming the documents exposes it, so
   it is fixed here rather than inherited. This **widens** protection.
3. **`CLAUDEKIT_EXTRA_PROTECTED`** — a colon-separated env extension, exactly the
   shape `ALLOWED_RUN_COMMANDS` / `CLAUDEKIT_RUN_COMMAND_EXTRA_ALLOW` already uses
   at `shared.py:38-56`. Widening only: there is no mechanism to remove a default,
   so a project config can add `RUNBOOK.md` but can never unprotect `README.md`.
   This is what makes the list safe to ship without a census of 16 consumers —
   which I did not do and do not claim to have done.

`validate-config-json.py`'s rejection message is switched to the effective set, so
a project that extended the list sees what actually blocked it.

**`src/claudekit/security/path_guard.py` is NOT touched.** It carries a different
list for a different surface (`.git/config`, `.ssh/`, `.env`) and has no `*.md`
entry. Widening this change into it adds blast radius for no gain.

## What this deliberately gives up

A downstream project's `docs/design.md` is no longer refused; a plan can delete it
with a stated reason. That is the cost, and it is the point — the guard exists to
stop an agent destroying a project's identity documents, not to freeze every
paragraph of prose in the tree. A project that disagrees names its own files in
`CLAUDEKIT_EXTRA_PROTECTED`. Three controls still stand in front of any deletion:
`MAX_DELETIONS = 3` per config, the mandatory `reason` field, and the executor's
pre-delete backup.

## Must be proven, not asserted

1. Every named document refused **at any depth** — `docs/deep/README.md`.
2. Refusal **does not depend on casing** — `readme.md`, `License.md`,
   `Contributing.MD`, `makefile`, `DOCKERFILE` all refused.
3. Component prose now deletable — `.claude/skills/*/SKILL.md`,
   `.claude/agents/*.md`, `templates/commands/*.md`.
4. The default list pinned by **equality**, not a superset check, so a mutant that
   adds or reorders an entry fails. (Round 1 caught `>=` here; a superset assertion
   passes against exactly the mutant this plan says it guards against.)
5. `CLAUDEKIT_EXTRA_PROTECTED` widens and **cannot narrow**; its effect does not
   leak past the test.
6. **The gate binds.** Delete one name from the shipped list and watch the suite go
   red. A rule that passes against a mutant is worse than none, and that has
   shipped twice in this repo. Evidence recorded, not claimed. This is an
   execution-time proof no plan reviewer can perform — neither round-1 nor round-2
   had Bash — so it routes to `code-reviewer` after implementation, per the
   review-routing rule in `CLAUDE.md` (plans → `reviewer`, code + mutation proofs →
   `code-reviewer`).

## Risk

Medium — a security-surface narrowing, so it gets a full reviewer pass. Two
independent checks that it did not overshoot: the pre-existing assertions at
`tests/test_validator.py:21-23` (`README.md`, `CHANGELOG.md`) survive untouched,
and items 2 and 3 above are widenings, not narrowings.

## Rollback

Revert `shared.py`, `validate-config-json.py` **and** `tests/test_validator.py`
together — the new tests assert the narrowed list, so reverting the source alone
leaves the suite red. One commit, one `git revert`.

## Review history

Round 2: **93/100 APPROVED**, no CRITICAL or MAJOR findings. Its two MINORs — the
receipts being pasted output with no reproducible command, and the mutation proof
being unverifiable from a plan review — are addressed above (commands recorded;
proof routed to `code-reviewer`).

Round 1: **80/100 CONDITIONAL.** Six findings, all addressed:
`[CRITICAL]` list not derived from a consumer survey → the list is now declared a
default, six more conventional names added, and `CLAUDEKIT_EXTRA_PROTECTED` gives
each consumer its own widening.
`[CRITICAL]` case-sensitivity regression (`readme.md` silently unprotected) →
matching is now case-insensitive, measured before/after, and tested.
`[MAJOR]` `>=` did not pin the list → equality assertion on the full ordered list.
`[MAJOR]` headline counts unverifiable → receipts pasted above (97 configs, 0
deletions; 16 of 19 rejected).
`[MINOR]` rollback omitted the test file → stated.
`[MINOR]` bare `LICENSE` never in scope → it is now protected, not just noted.

## Definition of Done

Every command in `CLAUDE.md` § Definition of Done, plus the mutation proof.
