---
signature: "assumed subprocess.run inherited the parent env"
root_cause: ""
fix: ""
files: []
date: 2026-09-12
status: wontfix
origin: workflow
verified: false
---

# reflection-4e2c41055d84

## Signature

assumed subprocess.run inherited the parent env

## Root cause

(not diagnosed yet - status: wontfix)

## Fix

(not fixed yet - status: wontfix)

## Files

- (none recorded)

## Not fixed (wontfix)

Workflow lesson, not a live defect. Traced 2026-09-12: every subprocess.run in src/, .claude/hooks/, .claude/operations/scripts/ and tests/ builds env from dict(os.environ) (xpipe.py:174,267; test_rejection_briefs.py:41). The sole bare env dict, test_concurrency_guard.py:1657, is a deliberate PATH-pinned sandbox. Never diagnosed, so no root_cause/fix recorded.
