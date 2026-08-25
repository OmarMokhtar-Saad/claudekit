# D4 — Fleet CI security gating: evaluation and one pilot

**Date:** 2026-08-25 · **Scope:** evaluation + a single pilot repo, per plan §D4. Rollout is
a separate plan and is NOT proposed here.

## Verdict

**Adopt for the GitHub half of the fleet, pilot on AppiumLens. Do not plan a nine-repo
rollout — the plan's premise does not hold.**

## The premise that failed, measured

§D4 says "the 9 Java/Kotlin fleet repos' CI". Two independent blockers, both measured:

| Repo | Stack | Forge | Existing workflows | Action can run? |
|---|---|---|---|---|
| AppiumLens | Java (2054) | **GitHub** | 4 | ✅ **pilot** |
| ApiForge | Java (27) | **GitHub** | **0** | ⚠ needs CI stood up first |
| Lean | Java (238) | **GitHub** | **0** | ⚠ needs CI stood up first |
| LeanApis | Java (219) | **GitHub** | **0** | ⚠ needs CI stood up first |
| Eatizaz | Java (97) | **GitLab** | 0 | ❌ never |
| AutomationApp | Java (112) | **GitLab** | 0 | ❌ never |
| MobileUIAutomator | Java (73) | **GitLab** | 0 | ❌ never |
| SehhatyApp | Java (235) | **GitLab** | 0 | ❌ never |
| shsmartassistant-qa | Kotlin (27) | **no remote** | 1 (local) | ❌ nothing to gate |

1. **A GitHub Action cannot run on GitLab.** Four of the nine are GitLab-hosted. No amount
   of configuration changes that; they would need a GitLab CI equivalent, which is a
   different tool and a different plan.
2. **Eight of nine have no GitHub Actions workflows at all** — including **ApiForge, the
   pilot the plan suggested**. Piloting there means standing up CI from scratch, which is
   not what "add a security gate to existing CI" evaluates.

So the addressable set today is **AppiumLens only**, and the realistic near-term set is
four GitHub repos, three of which need CI first.

## ⚠ Unrelated hazard found while measuring — worth acting on

**`SehhatyApp` and `Eatizaz` share the same git remote:**

```
SehhatyApp  origin  git@gitlab.com:omar.mokhtarsaad92/eatizaz.git
Eatizaz     origin  git@gitlab.com:omar.mokhtarsaad92/eatizaz.git
```

These are different codebases (235 vs 97 Java files). Pushing `SehhatyApp` would publish it
over `Eatizaz`'s repository. This has nothing to do with D4 — it surfaced while surveying
remotes — but it is the highest-severity thing in this document.

## What the Action is, and where it fits

Anthropic's `anthropics/claude-code-security-review` is diff-aware: it reviews only the
changed lines in a PR and posts line-level comments. That makes it complementary to, not a
replacement for, what the kit already has:

| Layer | Runs | Sees | Blocks a merge |
|---|---|---|---|
| `security-checklist` skill | in-session, always loaded | whatever the agent is doing | no |
| `differential-security-review` skill | in-session, on request | the diff, via the agent | no |
| **this Action** | **CI, per PR** | **the diff** | **yes, if made required** |

The gap it closes is real: everything the kit ships today depends on an agent choosing to
look. A CI gate does not.

**Cost:** it calls the Anthropic API per PR, so it needs an `ANTHROPIC_API_KEY` repository
secret and it bills per run. On a busy repo that is a real line item; scope it with `paths:`
so it fires on source changes, not on every docs commit.

## The pilot

`AppiumLens/.github/workflows/claude-security-review.yml`, written and left **uncommitted**
alongside every other downstream change. It is the right pilot: GitHub-hosted, already runs
four workflows (so CI conventions exist to match), and is the largest Java codebase in the
fleet at 2054 tracked files.

**It cannot run until the owner adds `ANTHROPIC_API_KEY` to the repository secrets.** Until
then it will fail fast with a clear message rather than silently passing — a security gate
that skips when unconfigured is worse than no gate, because the green check is a lie.

## Recommended next steps, in order

1. **Fix the SehhatyApp/Eatizaz shared remote.** Unrelated, higher severity.
2. Add `ANTHROPIC_API_KEY` to AppiumLens and let the pilot run for a few real PRs.
3. Judge it on *findings that mattered per dollar*, not on finding count.
4. Only then decide about Lean / LeanApis / ApiForge — each needs CI stood up first.
5. For the GitLab four, treat "a security gate for GitLab CI" as its own evaluation.
