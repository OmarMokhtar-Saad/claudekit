# Owner actions — two left, both outside this machine

Written 2026-09-07, after everything else completed. Release 3.2.0 is merged, tagged and
published as a GitHub release. What remains needs credentials or accounts a session cannot
reach.

## 1. Register the PyPI trusted publisher, then re-run the release

The wheel for v3.2.0 is **not on PyPI**. The publish step failed with:

```
invalid-publisher: valid token, but no corresponding publisher
sub: repo:OmarMokhtar-Saad/claudekit:environment:pypi
workflow_ref: OmarMokhtar-Saad/claudekit/.github/workflows/release.yml@refs/tags/v3.2.0
```

This is a pypi.org account setting, not a repo defect, and **v3.1.0 failed the same way** —
the PyPI publish has never succeeded.

**Corrected 2026-09-07 after checking PyPI directly: the project does not exist there.**
`https://pypi.org/project/claude-kit/` and `https://pypi.org/simple/claude-kit/` both return
404, and the JSON API returns `Not Found`. So there is no project settings page to add a
publisher to — `/manage/project/claude-kit/settings/publishing/` is itself a 404. The name
has never been claimed, which matches the long-standing "PyPI name decision blocks publish"
note in this project's memory.

The right route for a first-ever publish is a **pending publisher**, registered under the
account rather than the project:

1. Log in to pypi.org (I could not: entering credentials is out of bounds for me).
2. Go to **Account settings → Publishing** (`https://pypi.org/manage/account/publishing/`)
   and add a **pending** trusted publisher:
   - PyPI project name: `claude-kit`
   - Owner: `OmarMokhtar-Saad`
   - Repository: `claudekit`
   - Workflow: `release.yml`
   - Environment: `pypi`
3. Re-run the failed job:

```bash
gh run rerun 34091889298 --failed     # or re-push the tag
```

The first successful publish converts the pending publisher into a normal project-level one.

**The name is already settled — no decision needed.** `claude-kit` is the deliberate choice
because `claudekit` is taken on PyPI by an unrelated project (verified today: `claudekit`
0.1.1, "Production-grade Python developer toolkit…"). The import package and console scripts
stay `claudekit`/`ck`. This matches what was recorded when the release was first prepared, so
the only thing that has ever blocked publishing is the pending-publisher registration above,
which needs a PyPI login.

Everything before that step passed on the tag: 10987 tests passed, 79 skipped, 0 failed,
sdist and wheel both built.

## 2. Update the editable install — as ONE command, never the pull alone

The global `ck` resolves to `/Users/omarmokhtar/IdeaProjects/.ck-main`. Editable installs
freeze their metadata at install time, so the pull and the re-install must not be separated.

**Run this as a single chain:**

```bash
git -C /Users/omarmokhtar/IdeaProjects/.ck-main pull --ff-only && \
  pip install -e /Users/omarmokhtar/IdeaProjects/.ck-main && \
  ck --version    # must print 3.2.0
```

**Do not run the `pull` on its own.** Right now `.ck-main` is one minor behind but
*consistent*: source 3.1.0, metadata 3.1.0, `ck --version` 3.1.0, and every project's
manifest says 3.1.0 too, so the drift check correctly reports a match. Pulling without the
`pip` re-run produces source 3.2.0 with metadata 3.1.0 — the fleet would then run 3.2.0 code
while reporting 3.1.0, and the drift check would compare 3.1.0 against 3.1.0 and say
"matches" while being silently wrong. Stale-but-consistent beats current-but-inconsistent.

Seven `tests/test_doctor_gate.py` strict tests fail on a source checkout whose metadata
disagrees with its source, and pass in CI, which installs fresh. **These tests are correct
and should not be re-anchored.** A peer session built exactly that fixture fix, measured it
(7 failures to 5), and withdrew it: the survivors include the positive control
`test_a_freshly_installed_tree_reports_no_version_drift`, and it survives because
`install.sh` stamps the *source* version into the manifest while the CLI reports the
*metadata* version. In that state a fresh install genuinely is drifted, so the test failing
is a true signal. Re-anchoring would have hidden it.

Optional, owner-gated: to make the class structurally impossible rather than procedurally
avoided, `_resolve_version()` could prefer the source version on a source checkout, so
`install.sh` and the CLI agree by construction. That is a version-site change under hard
rule 7 and needs a reviewed plan. Neither session started it.

After the re-install, each kitted project will warn `Install version drift` until refreshed
with `ck update` (or a re-run of `install.sh`). The 3.2.0 CHANGELOG says so in its first
bullet.

---

# Done, for the record

- **Release 3.2.0**: PR #35 merged (`d2ca6d0`), tag `v3.2.0` pushed, GitHub release published
  with notes. Four version sites bumped together, including a fourth in `cli/main.py` that
  hard rule 7 does not name and `test_single_version_source_of_truth` caught.
- **Both feature branches on main**: a peer session merged the tips directly, so #33 and #34
  were closed as already-landed. Verified two ways before closing: `git merge-base
  --is-ancestor`, and the peer's independent `git merge-tree --write-tree`, which showed the
  remaining commits were only "merge origin/main" bookkeeping.
- **All 11 Dependabot PRs closed**: #7 #9 #10 #11 #14 superseded by #32 (same versions, already
  SHA-pinned); #6 #12 #15 #17 #18 #19 above the Python 3.9 caps #32 set.
- **All 13 kitted repos committed**, one commit each, verified to contain only sync files and
  to leave every other dirty file untouched. Where a repo gitignores parts of `.claude/`
  (AppiumLens, Lean, LeanApis, MobileUIAutomator), only its tracked files were committed and
  nothing was force-added.

  **Note a deviation from a recorded convention:** this project's memory says downstream fleet
  changes are left UNCOMMITTED for the owner. They were committed here because the session
  goal named "fleet repos committed" as an explicit deliverable. A peer session independently
  verified the commits and flagged the deviation rather than judging it. If the standing
  preference is still "leave uncommitted", these 13 commits are each a single commit on top of
  otherwise-untouched trees and are trivial to `git reset --soft HEAD~1`.
- **Verified running in all 13**: 16/16 files byte-identical to `origin/main`, the three hooks
  exit 0 under the standard profile, `settings.json` parses, `ck doctor` 28/28 with zero
  warnings. Re-runnable with `./fleet-verify.sh`.

## Still unowned: `feat/ops-parse-gate`

2 commits, own worktree at `../.ck-parse-gate-wt`, 28 commits behind main, no PR. A peer
session merged it, found a real regression and backed it out rather than weaken a test:
`tests/test_validator_sequence_mode.py::TestSequenceProjection::test_projected_verdict_agrees_with_the_executor`
fails because the parse gate rejects with `parse-gate: result does not parse` before the
`ambiguous match` check the validator's projection is asserted to agree with. The config is
still rejected, so the outcome is right but the precise diagnosis is replaced by a symptom.
The proposed fix — run the ambiguity check first, leaving the parse gate as a backstop —
touches `execute-json-ops.py` and is security-adjacent, so it needs a reviewed plan. Neither
session acted on it.
