# Task 008 batch 1 — ops config index

Plan: [`plan-008-batch1-one-tree.md`](plan-008-batch1-one-tree.md).

`MAX_DELETIONS = 3` per config (`validate-config-json.py:40`) and the batch removes
38 files, so it executes as the sequence below. The cap is not raised and not routed
around. There is no move operation in the schema, so each promotion is a
`file_create` of byte-identical content followed by a `file_delete` of the source,
and the executor backs up every deleted file first.

**Order is load-bearing:** promote first, delete second, `install.sh` and the tests
last. At every intermediate point `install.sh` still installs a complete tree — its
`templates/` copy loops are all guarded, so a promoted-and-removed source is a no-op.

| # | Config | Operations | Deletions |
| --- | --- | --- | --- |
| 1 | `008-b1-01-commands-1.json` | create×3, delete×3 | 3 |
| 2 | `008-b1-02-commands-2.json` | create×3, delete×3 | 3 |
| 3 | `008-b1-03-commands-3.json` | create×3, delete×3 | 3 |
| 4 | `008-b1-04-commands-4.json` | create×3, delete×3 | 3 |
| 5 | `008-b1-05-commands-5.json` | create×1, delete×1 | 1 |
| 6 | `008-b1-06-hooks-1.json` | create×3, delete×3 | 3 |
| 7 | `008-b1-07-hooks-2.json` | create×1, delete×1 | 1 |
| 8 | `008-b1-08-modes-1.json` | create×3, delete×3 | 3 |
| 9 | `008-b1-09-modes-2.json` | create×3, delete×3 | 3 |
| 10 | `008-b1-10-modes-3.json` | create×1, delete×1 | 1 |
| 11 | `008-b1-11-skills-descriptions-and-i18n.json` | edit×2, delete×1 | 1 |
| 12 | `008-b1-12-skills-delete-1.json` | delete×3 | 3 |
| 13 | `008-b1-13-skills-delete-2.json` | delete×3 | 3 |
| 14 | `008-b1-14-skills-delete-3.json` | delete×3 | 3 |
| 15 | `008-b1-15-skills-delete-4.json` | delete×3 | 3 |
| 16 | `008-b1-16-skills-delete-5.json` | delete×1 | 1 |
| 17 | `008-b1-17-installer-one-tree.json` | edit×1 | 0 |
| 18 | `008-b1-18-tests-one-tree.json` | edit×3 | 0 |
| 19 | `008-b1-19-tests-invariants.json` | edit×4 | 0 |

Total deletions: 38. Every config validates with
`python3 .claude/operations/scripts/validate-config-json.py <config>` before it runs,
and each spent config moves to `.claude/plans/archive/` with a README row.
