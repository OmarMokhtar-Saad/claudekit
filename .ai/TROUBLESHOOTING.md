# Troubleshooting

Symptom → cause → fix. Maintainer-focused; user-facing variants belong in docs/.

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Edit/Write blocked on Tier 3 source ("PLAN GATE") | No approved plan.md names the file | Write `.claude/plans/plan-<slug>.md` with `Tier:` and `Files:`, get it reviewed, record it with `review-record.py plan-write`; no profile bypasses it |
| Hooks never fire in a user project | Old install without settings.json (pre-v2.1 installer bug) | Re-run installer / `ck update`; verify with `ck doctor` |
| "Blocking" hook doesn't block | exit 1 or message on stdout; or profile=minimal | exit 2 + stderr via `deny`; check profile |
| Hook blocks everything unexpectedly | Fail-closed on payload parse failure | Check hooks.log for the parse error; payload shape changed? |
| `ck init` "cannot find asset tree" | Running outside checkout without wheel assets or CLAUDEKIT_HOME | `pip install claudekit-agents` (bundles assets) or set `CLAUDEKIT_HOME` |
| `docs-drift` CI job fails | A doc hard-codes a stale count | `python3 scripts/gen-docs.py` and update, or fix the asset change |
| `validate-registry` fails | Renamed/moved skill still referenced in skills-registry.json | Update `path`/`usedBy`; grep for the old id |
| `permission-gate` fails | `--dangerously-skip-permissions` reintroduced | Remove it; use scoped `--allowedTools` per INVOCATION.md |
| `dangling-hooks` fails | settings.json references a missing script | Restore the script or remove the registration |
| Tests pass locally, fail on macOS CI | bash-4+ism or GNU tool flag | See [DEBUGGING_GUIDE.md](DEBUGGING_GUIDE.md) §CI-only |
| test_packaging fails on py3.12+ | setuptools not preinstalled | `pip install setuptools` in the env (CI does; `0c9223b`) |
| Commit rejected: message format | commit-quality conventional-commit check | `type(scope): subject`; or check for staged secrets — same hook blocks those |
| `ck update` wants to overwrite my edits | You modified managed files (manifest hash mismatch) | Note the `ck diff` list; installer backs up first; re-apply local changes after |
| Reviewer keeps rejecting a plan | Missing `Files:` list on a Tier 3 plan (auto-reject) or sub-90 dimensions | Read the scored report; use `/refine` to loop automatically |
| Wheel installs but `ck agents` finds nothing | Assets not bundled (MANIFEST/setup.py drift) | Check `<prefix>/share/claudekit`; run package-smoke locally |
| PyPI publish fails on tag | Trusted Publishing config mismatch (first run untested) | Check the PyPI publisher settings against release.yml env |

Still stuck: hooks.log → `ck doctor --strict` → the matching test file ([TESTING_GUIDE.md](TESTING_GUIDE.md) map) → `review/` audit for historical context on that subsystem.
