# Implementation Plan: task 008 batch 1 — one canonical tree

`main`, planned at HEAD `2e954fe`. Tier 3. Owner approved batch 1 in
`.ai/TASK-008-SIGNOFF.md` (2026-08-23) and approved the scope correction below in
session on the same date.

## Overview

`install.sh` copies `templates/` **and** `.claude/` into the same destination.
This plan makes `.claude/` the single source for commands, hooks, modes and
skills, so no destination file is decided by copy order, and deletes the
`templates/` copies of those four component classes.

## The sign-off sheet's premise is wrong in two places — measured, not assumed

The sheet describes `templates/skills|commands|hooks|modes` as a *duplicate* tree
and its three diverged skills as needing a three-way merge. Neither holds at
`2e954fe`.

| Claim in the sheet | Measured | Command |
|---|---|---|
| 3 skills diverged, need three-way merge | Each differs by exactly **one line** — the `description:` frontmatter. `.claude/` is a strict superset of the body. | `diff templates/skills/<n>/SKILL.md .claude/skills/<n>/SKILL.md \| grep -c '^<'` → `1`, `1`, `1` |
| `templates/commands` are duplicates (13) | **Zero** name overlap with `.claude/commands/` | name-by-name `cmp` loop, all `ONLY-TMPL` |
| `templates/hooks` are duplicates (4) | **Zero** overlap with `.claude/hooks/` | same loop |
| `templates/modes` are duplicates (7) | `.claude/modes/` **does not exist** | `ls -d .claude/modes` → No such file |
| copy order decides the winner | Already fixed for **skills** at `install.sh:232-245` (`continue` when the canonical `SKILL.md` exists). Still true structurally: two trees, one destination. | read the block |

So deleting `templates/commands|hooks|modes` as written would delete **24 shipped
components**, not duplicates. It would also leave a real drift in place: docs
report 42 commands (the generator reads `.claude/commands/`) while a `--full`
install lands 55.

**Owner decision (2026-08-23):** promote the 24 into `.claude/`, delete nothing
but the true duplicates. Content loss: zero. Counts move, and only the generator
moves them.

## Scope

1. **Promote** `templates/commands/*.md` (13) → `.claude/commands/`.
2. **Promote** `templates/hooks/*.sh` (4) → `.claude/hooks/` (unwired, exactly as
   they are today — `install.sh` already documents template hooks as installed
   but not wired).
3. **Promote** `templates/modes/*.md` (7) → new `.claude/modes/`. `install.sh`
   already has the `elif [[ -d "$CLAUDE_SRC/modes" ]]` fallback branch.
4. **`spec-driven-development`**: adopt the `templates/` description (the
   `Use when …` trigger form); keep the `.claude/` body. This is the union — the
   only operative content the `templates/` copy holds that `.claude/` lacks.
   `incident-response` and `token-optimization` need no change: their `.claude/`
   descriptions are already in trigger form and already better.
5. **`i18n-workflow`** (templates-only, 205 lines): fold the five sections
   `i18n-patterns` does not cover — Gender/Select, Relative Time, formats by
   ecosystem, quality checks, anti-patterns — into `.claude/skills/i18n-patterns/`,
   then delete the file. Promoting it verbatim would ship a near-duplicate, which
   `CLAUDE.md` forbids. Skill count stays 76.
6. **Delete** all 14 `templates/skills/*/SKILL.md`.
7. **`install.sh`**: drop the `templates/commands` copy, the
   `_copy_hook_assets "$SCRIPT_DIR/templates/hooks"` call, the `templates/skills`
   loop and the registry-reconcile block it needed (that block existed only
   because `i18n-workflow` shipped from `templates/` and was absent from the
   registry — `ck doctor --strict` exited 1 on a fresh install because of it), and
   make `.claude/modes` the modes source.
8. **Tests**: update the six files that assert the two-tree layout
   (`test_new_commands.py:47`, `test_new_skills.py:71`, `test_doctor_gate.py:425`,
   `test_install_receipts.py:402,430`, `test_project_graph.py:13`,
   `test_install.py:267`) to assert the one-tree invariant instead.
9. Regenerate counts with `scripts/gen-docs.py` and `scripts/gen-registry.py`.
   Never by hand (hard rule 8).

`templates/` keeps everything else: the per-language dirs, `mcp/`, `.agentignore`.

## Shape: many small configs, by design

`MAX_DELETIONS = 3` per ops.json (`validate-config-json.py:40`) and this plan
removes 38 files, so it executes as **17 sequential ops configs**, listed in
`ops-008-batch1-INDEX.md`. That cap is not routed around and is not raised. There
is no move operation in the schema, so each promotion is `file_create` +
`file_delete`, and every deleted file is backed up by the executor first.

Order matters: promote before deleting, `install.sh` last. At every intermediate
point `install.sh` still installs a complete tree — the `templates/` copy loops
are all guarded (`-d` test, or `2>/dev/null || true`), so a promoted-and-removed
source is a no-op, never a failure.

## Must be proven, not asserted

| # | Claim | Proof |
|---|---|---|
| 1 | `install.sh` no longer copies two trees to one destination | `grep -c 'templates/\(commands\|hooks\|modes\|skills\)' install.sh` → 0 |
| 2 | No content lost in the promotion | every promoted file byte-identical to its source: `cmp` per file, before deletion |
| 3 | The three "diverged" skills keep the union | diff each `.claude/` body against the `templates/` body → empty; description diff shown |
| 4 | `i18n-workflow`'s unique sections survive | each of the five headings present in `i18n-patterns/SKILL.md` |
| 5 | Registry referential integrity still clean | `gen-registry.py --check` |
| 6 | Counts are generator-derived | `gen-docs.py --check` after regeneration |
| 7 | A fresh `--full` install is complete and `ck doctor --strict` passes | run the installer into a temp dir |

## Risk

Low-to-medium. The content risk is zero (byte-identical promotion, proven by
`cmp`). The real risk is `install.sh` regression, which item 7 exercises end to
end rather than by reading the diff.

## Rollback

`git revert` of one commit, or `restore-backup.py` per shard. No consumer sees a
removed name: every promoted component keeps its filename, and `i18n-workflow` is
the only name that disappears — it enters the registry `renamed` alias map
pointing at `i18n-patterns`.

## Definition of Done

    python3 -m pytest tests/ -q
    ruff check src/ tests/ scripts/
    mypy
    python3 scripts/gen-docs.py --check
    python3 scripts/gen-registry.py --check
    python3 scripts/gen-model-policy.py --check
    python3 scripts/check-context-floor.py
    shellcheck install.sh .claude/hooks/*.sh

Plus a real `--full` install into a temp dir, then `ck doctor --strict` on it.
