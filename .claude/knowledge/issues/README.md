# Issue Knowledge Ledger (project-local)

One markdown file per issue this project has **diagnosed, fixed, and verified**, so a later
session looks the answer up instead of re-diagnosing a bug we already solved.

- **Scope:** project-local only. Cross-project promotion to `~/.claude/skills/learned/` is a
  deliberate future phase — do not write outside this directory.
- **No index, no vector store.** Retrieval is plain keyword/signature grep
  (`.claude/operations/scripts/knowledge-ledger.py`), stdlib-only, zero runtime deps.
- **Never auto-injected.** The ledger is *pulled* by the debugger agent (Phase 0) on demand;
  it is never appended to CLAUDE.md or preloaded into context.

## Entry format

File name: `<slug>.md`, slug matching `^[a-z0-9][a-z0-9._-]{0,63}$`.

```markdown
---
signature: "AttributeError: 'NoneType' object has no attribute 'items' in ops executor"
root_cause: "extract_json_field returned '' and the caller never checked"
fix: "fail closed on parse error (rc 3) and assert dict before .items()"
files: [.claude/hooks/lib.sh, tests/test_hooks_behavioral.py]
date: 2026-08-01
verified: true
---

# <slug>

## Signature / ## Root cause / ## Fix / ## Files / ## Scoring
```

`signature` is the searchable error string or symptom phrase. `files` is what pruning uses.

## Writing an entry (the gate)

Entries are written **only** at the Verifier PASS checkpoint of the
Implementer -> Verifier -> GitOps pipeline, and only when the reusability/novelty rubric in
`.claude/skills/continuous-learning/SKILL.md` clears the threshold (**combined >= 10** by default; the script reads
`continuous_learning.issue_ledger.min_combined_score` from `.claude/hooks/config.json` and falls
back to 10 when that key is absent):

```bash
python3 .claude/operations/scripts/knowledge-ledger.py record \
  --slug null-deref-in-ops-executor \
  --signature "AttributeError: 'NoneType' object has no attribute 'items'" \
  --root-cause "..." --fix "..." \
  --files ".claude/hooks/lib.sh,tests/test_hooks_behavioral.py" \
  --reusability 7 --novelty 8 --verified
```

The script refuses (exit 1) without `--verified`, below the rubric threshold, or when the
signature is already recorded.

## Reading (debugger Phase 0)

```bash
python3 .claude/operations/scripts/knowledge-ledger.py search "AttributeError NoneType items"
```

Exit 0 = match printed (report the known root cause/fix); exit 3 = no match, diagnose fresh.

## Hygiene

Ledger pruning rides the periodic backlog/docs-drift sweep (see `.ai/BACKLOG.md`, P3):

```bash
python3 .claude/operations/scripts/knowledge-ledger.py prune          # report (exit 1 if stale)
python3 .claude/operations/scripts/knowledge-ledger.py prune --apply  # move to ./archive/
```

An entry is stale when **every** file in its `files:` list no longer exists. Entries with an
empty `files:` list are never auto-pruned.
