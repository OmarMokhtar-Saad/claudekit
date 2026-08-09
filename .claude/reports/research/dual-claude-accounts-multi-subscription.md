# Dual Claude Accounts on One Machine (2025-2026 State of Art)

**Date:** 2026-08-09  
**Question:** How to run TWO different Claude accounts/subscriptions in parallel on one machine with Claude Code?

## CLAUDE_CONFIG_DIR (Primary Method)

**Does it isolate credentials?** YES — completely separate configs per directory.

**Exact usage:**
```bash
# Add aliases to ~/.zshrc or ~/.bashrc
alias claude-work='CLAUDE_CONFIG_DIR=~/.claude-work claude'
alias claude-personal='CLAUDE_CONFIG_DIR=~/.claude-personal claude'

# Each terminal runs independently
claude-work     # Uses ~/.claude-work/ config
claude-personal # Uses ~/.claude-personal/ config
```

**Per-project alternative (direnv):**
```bash
# .envrc in project root
export CLAUDE_CONFIG_DIR=~/.claude-work
```

**Status:** Functional in Claude Code, but undocumented in `claude --help` as of March 2026 (GitHub issue #33430).

---

## Login & Token Storage

**Multi-session support:** YES — both accounts stay logged in simultaneously (different config dirs = different credential files).

**Credential storage by OS:**
- **macOS:** Encrypted macOS Keychain (primary); reads `~/.claude/.credentials.json` if present
- **Linux:** `~/.claude/.credentials.json` (mode 0600)
- **Windows:** `%USERPROFILE%\.claude\.credentials.json`
- **CLAUDE_CONFIG_DIR:** Moves `.credentials.json` to that directory on Linux/Windows; Keychain unaffected on macOS

**OAuth token flow:**
- `/login` opens browser for OAuth (saves token to credentials file)
- `/logout` clears credentials
- Token lifespan: ~3 years (warning at 3-day expiry)
- Long-lived token alternative: `claude setup-token` → `CLAUDE_CODE_OAUTH_TOKEN` env var

---

## Practical Patterns

1. **Shell aliases** (simplest)
   ```bash
   alias claude-work='CLAUDE_CONFIG_DIR=~/.claude-work claude'
   ```

2. **ANTHROPIC_API_KEY per shell** (if using API keys instead of subscriptions)
   ```bash
   # Terminal 1: work account
   export ANTHROPIC_API_KEY=sk-ant-work-key
   claude
   
   # Terminal 2: personal account
   export ANTHROPIC_API_KEY=sk-ant-personal-key
   claude
   ```
   Precedence: API_KEY wins over subscription OAuth.

3. **Separate OS users** — clean but overkill; CLAUDE_CONFIG_DIR is simpler.

4. **Containers/devcontainers** — works if each mounts different CLAUDE_CONFIG_DIR.

5. **direnv per project** — auto-set CLAUDE_CONFIG_DIR on cd.

---

## Rate Limiting & Quotas

- **Pro plan:** ~7-10x higher quota than free
- **Max plan:** ~3-4x higher than Pro
- **Each account has independent 5-hour rolling window**
- **Two Max subscriptions:** effectively doubles your rate limit

---

## ToS/Usage Policy

**No explicit prohibition found** in official Claude Code docs or Anthropic ToS against using multiple personal accounts on one machine. Supported use cases include:
- Company + personal projects
- Work + side projects  
- Team accounts + individual accounts

**Not allowed:** Sharing credentials, credential pooling across unrelated parties, or circumventing per-account limits.

---

## ANTHROPIC_API_KEY as Alternative

Works cleanly for multi-identity if you have Console API keys:
```bash
# Shell-scoped (each terminal separate)
ANTHROPIC_API_KEY=work-key claude <command>
ANTHROPIC_API_KEY=personal-key claude <command>
```

**Precedence in Claude Code:**
1. Cloud providers (Bedrock, Vertex, Foundry)
2. ANTHROPIC_AUTH_TOKEN
3. **ANTHROPIC_API_KEY** ← Checked here
4. apiKeyHelper script
5. CLAUDE_CODE_OAUTH_TOKEN
6. Subscription OAuth

---

## Gotchas on macOS

- Keychain credentials don't respect CLAUDE_CONFIG_DIR — if one account "bleeds" to the other, clear Keychain:
  ```bash
  # View stored items
  security find-internet-password -l claude | grep acct
  # Delete specific item if needed
  security delete-internet-password -l claude
  ```
- Workaround: Store `.credentials.json` plaintext in CLAUDE_CONFIG_DIR instead of Keychain (less secure).

---

## Summary Table

| Method | Setup | Parallel? | Isolation | Notes |
|--------|-------|-----------|-----------|-------|
| CLAUDE_CONFIG_DIR + aliases | Easy | YES | Perfect | Recommended; undocumented |
| ANTHROPIC_API_KEY per shell | Easy | YES | Perfect | Needs Console API keys |
| /login per directory | Medium | YES | Good | Manual token refresh |
| Separate OS users | Hard | YES | Perfect | Overkill; use CLAUDE_CONFIG_DIR |
| devcontainers | Medium | YES | Perfect | For team setups |

---

## Sources

- [Claude Code Docs — Authentication](https://code.claude.com/docs/en/authentication)
- [GitHub Issue #33430 — CLAUDE_CONFIG_DIR Documentation](https://github.com/anthropics/claude-code/issues/33430)
- [Medium — Setting Up Multiple Claude Code Accounts](https://medium.com/@buwanekasumanasekara/setting-up-multiple-claude-code-accounts-on-your-local-machine-f8769a36d1b1)
- [Blog — Run Multiple Claude Code Accounts in Parallel](https://badarneh.com/articles/run-multiple-claude-code-accounts-in-parallel)
