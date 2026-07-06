---
description: "PRP Phase 3 — Smart commit using natural language file targeting. Stages relevant files and commits with a generated message."
argument-hint: "<natural-language description of what to commit>"
model: haiku
---

# PRP Commit Command

Phase 3 of the Product Requirements Process. Commits changes using natural language targeting — you describe what to commit in plain English and it finds and stages the right files.

## Mandatory Skills

- **using-superpowers** - Core capabilities
- **git-workflow** - Safe staging and commit protocol

## Task

Commit: $ARGUMENTS

---

## Execution Steps

### Step 1: Understand Intent

Parse the argument to identify:
- What changed (feature, fix, refactor, docs, test, chore)
- Which module or files are likely affected
- Commit type (feat/fix/refactor/test/docs/chore)

### Step 2: Find Relevant Files

```bash
# See all unstaged changes
git status --short

# See what's changed
git diff --stat
```

Map the user's description to specific files. Examples:
- "auth changes" → files in `src/auth/`, `tests/auth/`
- "JWT tokens" → files with `token` in path or content
- "the new middleware" → files matching `middleware.*` changed today
- "all tests" → `*.test.*` files

### Step 3: Smart Staging

```bash
# Stage only the relevant files (NOT git add -A)
git add <specific matched files>

# Verify what's staged
git diff --cached --stat
```

If the staging looks wrong, report what was found and ask for clarification.

### Step 4: Generate Commit Message

Follow conventional commits format:
```
<type>(<scope>): <description>

[optional body — only if the change needs explanation]

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
```

Type mapping:
- New feature → `feat`
- Bug fix → `fix`
- Refactor (no behavior change) → `refactor`
- Tests only → `test`
- Documentation → `docs`
- Build/tooling → `chore`

Scope: the module or area affected (e.g. `auth`, `api`, `db`)

Description: imperative mood, ≤ 72 chars, no period at end

### Step 5: Commit

```bash
git commit -m "$(cat <<'EOF'
<type>(<scope>): <description>

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

### Step 6: Confirm

```
COMMITTED
=========
<hash> <type>(<scope>): <description>
Files: <N> files changed, <N> insertions(+), <N> deletions(-)

Next: /prp-pr to create the pull request
```

---

## Usage Examples

- `/prp-commit "the JWT refresh token implementation"` — stages auth files, commits as feat(auth)
- `/prp-commit "fix the race condition in order processor"` — commits as fix(orders)
- `/prp-commit "add tests for the refresh token flow"` — commits as test(auth)
- `/prp-commit "update docs for the new auth API"` — commits as docs(auth)

## Notes

- NEVER uses `git add -A` or `git add .` — always stages specific files
- NEVER commits `.env`, key files, or secrets — runs commit-quality check first
- If multiple logical changes are present, ask which to include — don't bundle unrelated changes
- Respects the `commit-quality.sh` hook — debug artifacts block the commit
