# Cursor CLI Authentication Issue After Login (macOS Keychain)

**Date**: 2026-08-09

## Question
After `cursor-agent login` succeeds with browser auth, subsequent commands (`cursor-agent status`, `-p "..."`) fail with "Error: Authentication required" and "Not logged in". Tokens stored in macOS Keychain. CLI version 2026.07.23. Is this a known bug? What are the fixes?

## Answer

**Status**: Confirmed known bug (under investigation by Cursor team).

**Root Cause**: CLI loses access to tokens in macOS Keychain after browser auth completes, likely due to Keychain locking, permission issues, or stale entries.

### Fix Steps (in order)

1. **Clear and re-authenticate**
   ```bash
   cursor-agent logout
   cursor-agent login  # Re-run browser auth
   ```

2. **Unlock Keychain (if locked)**
   ```bash
   security unlock-keychain
   ```

3. **Repair Keychain**
   - Open Keychain Access.app
   - Search for "cursor" items
   - Delete any stale entries
   - Re-login via `cursor-agent login`

4. **Use Environment Variable Workaround**
   ```bash
   export CURSOR_API_KEY=<your-api-key>
   cursor-agent -p "..."  # Bypasses Keychain
   ```

### Token Storage & Alternatives

- **Primary storage**: macOS Keychain (service name not publicly documented)
- **Config file**: `~/.cursor/cli-config.json` contains metadata only, not the token
- **Environment variable alternative**: `CURSOR_API_KEY` (recommended for CI/automation)
- **Other env vars**: `NO_OPEN_BROWSER=1` (headless login)

## Sources

- [Cursor couldn't find your saved login in the macOS keychain - Community Forum](https://forum.cursor.com/t/cursor-couldnt-find-your-saved-login-in-the-macos-keychain/167158)
- [errSecItemNotFound couldn't find your saved login in the macOS keychain - Bug Reports](https://forum.cursor.com/t/errsecitemnotfound-couldnt-find-your-saved-login-in-the-macos-keychain/167325)
- [Cursor CLI Authentication Docs](https://cursor.com/docs/cli/reference/authentication)
