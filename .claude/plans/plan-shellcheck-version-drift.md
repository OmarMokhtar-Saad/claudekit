# plan-shellcheck-version-drift — three red CI jobs, one version difference

## What CI says and the local command does not

`gh pr checks 20`: `shellcheck` fail, `coverage` fail, `security-scan` fail. All three are the
same two shellcheck findings, because `tests/test_shell_lint.py` shells out to the binary, so
the version difference reddens the suite as well as the lint job.

```
.claude/hooks/dispatch.sh lines 132-138   SC2317 (info)  Command appears to be unreachable
.claude/hooks/ops-enforcement.sh line 56  SC2002 (style) Useless cat
```

Locally, `shellcheck install.sh .claude/hooks/*.sh` — the command CLAUDE.md's own block
prescribes — is **silent**, and stays silent at `-S style`. Local is ShellCheck 0.11.0; CI runs
`sudo apt-get install -y shellcheck`, whichever version Ubuntu ships, which still emits both.
So the documented way to check this cannot reproduce the gate that enforces it. That is the same
shape as the context-floor defect this branch already fixed: the documented invocation and the
enforcing one disagree.

## Ownership, measured

- `dispatch.sh` SC2317 is **ours**: the panic trap arrived in `34a4140` on this branch. It
  already carries `# shellcheck disable=SC2329` for "function never invoked"; the older
  shellcheck additionally flags every line of the body as unreachable, which the directive does
  not cover. The function IS invoked — indirectly, by the two `trap` lines immediately below it.
- `ops-enforcement.sh:56` is **pre-existing**, from `d878496`, and `main`'s own latest CI run is
  already failing. Not introduced here; fixed here because it is one line and it blocks this PR.

## Fix

- `dispatch.sh`: extend the directive to `SC2329,SC2317`, with the reason stated.
- `ops-enforcement.sh`: `tr -d '\r' < "$OPS_GLOBS_FILE" 2>/dev/null`. Behaviour is identical —
  a missing or unreadable marker still yields an empty value with nothing on stderr, so
  enforcement still fails **dormant** rather than erroring, which is what the comment above it
  promises.

## Files
- `.claude/hooks/dispatch.sh`
- `.claude/hooks/ops-enforcement.sh`

## Verification
Behavioural, not lint-only, because both files are the enforcement layer and hard rule 2 says a
blocking hook fails closed: run the dispatcher and ops-enforcement hook tests, plus a live
missing-marker probe to prove the redirect rewrite still fails dormant. The lint claim itself
cannot be verified locally at all — that is the finding — so CI is the oracle for SC2317.

## Not fixed here (backlogged)
Pinning shellcheck in CI so the local command can reproduce it. That is the root cause and it is
a CI change; doing it inside a PR that is already blocked on the symptom would mix the two.
