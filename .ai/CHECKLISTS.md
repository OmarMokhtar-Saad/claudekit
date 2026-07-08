# Checklists

## Definition of Done (any change)

- [ ] `python3 -m pytest tests/ -q` → 516+ pass, 0 fail
- [ ] `ruff check src/ tests/ scripts/` clean · `mypy` clean
- [ ] `python3 scripts/gen-docs.py --check` clean
- [ ] `shellcheck install.sh .claude/hooks/*.sh` clean (if shell touched)
- [ ] CHANGELOG `[Unreleased]` entry (user-visible changes)
- [ ] Affected docs updated (README/docs/ for users; `.ai/` for maintainers)
- [ ] Conventional commit + Co-Authored-By (AI work)
- [ ] Evidence captured: commands run, output seen — no unverified claims

## Pull request

- [ ] One concern per PR; description links the task/issue (`review/tasks/0XX` where applicable)
- [ ] Tests prove the change behaviorally (block AND allow paths for guards)
- [ ] No new hardcoded counts, near-duplicate assets, GNU-only shellisms, runtime deps
- [ ] Grep for renamed/removed asset names → zero stale references
- [ ] Reviewer checklist ([REVIEW_GUIDE.md](REVIEW_GUIDE.md)) for the touched asset class applied

## Release ([PLAYBOOK.md](PLAYBOOK.md) has the full recipe)

- [ ] Owner approval · [ ] DoD gate on main · [ ] CHANGELOG dated · [ ] 3 version locations agree
- [ ] Local wheel dry-run (build → clean venv install → `ck init` + `doctor`)
- [ ] Tag pushed → release.yml green → PyPI install verified from a clean venv
- [ ] GitHub Release notes · [ ] STATUS/SESSION_STATE updated

## New agent

- [ ] Justified vs extending an existing agent (consolidation era!) · [ ] frontmatter complete (name/description + 2 examples/model/tools-minimal/color)
- [ ] Mandatory-skill section, output contract, handoff formats · [ ] coordinator routing + QUICK_START + INVOCATION rows
- [ ] `gen-docs.py --check` · [ ] registry `usedBy` updated if skills reference it

## New skill

- [ ] Not a near-duplicate (check [SKILLS.md](SKILLS.md) categories) · [ ] SKILL.md with trigger-rich description
- [ ] Registered in skills-registry.json (path validates in CI) · [ ] `usedBy` accurate

## New hook

- [ ] Sources lib.sh · [ ] stdin JSON parsing · [ ] blocking = `deny` (exit 2 + stderr) + fail closed · [ ] profile-gated
- [ ] bash-3.2/macOS-safe · [ ] shellcheck clean · [ ] registered in settings.json (right event/matcher)
- [ ] Behavioral test: blocks bad, allows good, fails closed on garbage

## Security-sensitive change

- [ ] Bypass-corpus test added first · [ ] coverage ≥85% holds · [ ] no interpreters/launchers allowlisted
- [ ] fail-closed preserved · [ ] SECURITY.md framing still honest · [ ] CHANGELOG Security section

## Session handover

- [ ] [SESSION_STATE.md](SESSION_STATE.md) updated (state/pending/blocked/risks/next)
- [ ] [CHANGELOG_AI.md](CHANGELOG_AI.md) session entry · [ ] [STATUS.md](STATUS.md) if snapshot changed · [ ] [DECISIONS.md](DECISIONS.md) for new decisions
- [ ] Tree green (DoD gate) or failures documented in SESSION_STATE
