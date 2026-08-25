# Rejection brief — `e2e-lane-a`

Append-only; one section per non-approving review round. The session id is a local transcript filename (`transcript-miner.py <session-id> --around e2e-lane-a`), never a credential. Absolute paths and session tokens never appear here.

<!-- round: -1 -->
## Round -1 — CONDITIONAL (87)

- recorded: 2026-08-25T10:08:04Z
- session: bfab483e-36df-43d1-86ab-269d6040db4c
- prompt_version: unknown
- trail: 87/CONDITIONAL
- defect_type / trigger: (unclassified — assigned by /flow-retro or a human; a guessed classification is worse than an absent one)

### Findings
- [MAJOR] Mutation-proof overclaim. `.claude/plans/plan-e2e-lane-a.md:145-159` states each mutant was applied and "the suite re-run", and concludes "no mutant flipped a test outside its declared set". That is f
- [MAJOR] Group F/G drop leaves the executor lock covered by NOTHING. `ExecutionLock` <redacted> is project-wide and real (confirmed: `fcntl.flock(LOCK_EX|LOCK_NB
- [MAJOR] E2E-34 declared ALREADY-COVERED but the hook's cross-project deny branch is untested. `plan-e2e-lane-a.md:80` cites `test_worktree_manager.py::TestIsolationProof` and `test_security.py`; those cover t
- [MINOR] E2E-28 deferral is weaker than stated. `plan-e2e-lane-a.md:64-66` claims no deterministic version is possible without an injection point, but the invariant is timing-independent: send SIGINT mid-batch
- [MINOR] E2E-16 is PARTIAL, not ALREADY-COVERED (`plan-e2e-lane-a.md:76`). `test_packaging.py:91` and `test_hook_delivery.py:33` prove `settings.local.json` never ships, but the case's actual point — the repo'
- [MINOR] Group B row overstates equivalence in two spots (`plan-e2e-lane-a.md:74`): E2E-07 requires stderr that distinguishes "verdict does not authorise" from "no record", and `test_ops_approval_gate.py:123-1
- [MINOR] Plan accuracy nits: `:83` says `TestAgentRegistration` "parses agent frontmatter as YAML", but `tests/test_behavior_spec.py:148-156` explicitly does a structural check with no YAML parser; `:60` quote
- [MINOR] The corpus-lint self-check re-implements the matcher inline (ops.json op 1, `test_no_shipped_agent_or_command_instructs_a_payload_reprint`) instead of calling a shared predicate, so a future change to
- [MINOR] Refutation outcome, for the record: I could NOT construct a path where the fixture writes into the real repo — `settings.json` wires hooks as `"$ROOT/.claude/hooks/..."` with `ROOT=${CLAUDE_PROJECT_DI

### 5-whys (a writing template, not a clustering method)
1. Why was this rejected? 
2. Why? 
3. Why? 
4. Why? 
5. Root cause: 

