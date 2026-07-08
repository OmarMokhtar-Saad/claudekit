# Debugging Guide

For product bug *diagnosis workflow* see the debugger agent + `systematic-debugging` skill. This guide is for debugging **ClaudeKit itself**.

## First stops

```bash
tail -50 .claude/hooks/hooks.log        # every hook decision, parse failure, block reason
ck doctor --strict                      # 19 install-health checks
python3 -m pytest tests/ -q -x          # first failing test
git log --oneline -10                   # what changed recently
```

## Debugging a hook

```bash
# Reproduce exactly what Claude Code sends: stdin JSON payload
echo '{"tool_name":"Bash","tool_input":{"command":"git commit --no-verify -m x"}}' \
  | ECC_HOOK_PROFILE=standard bash -x .claude/hooks/block-no-verify.sh; echo "exit=$?"
```
- exit 0 = allow, 2 = block (reason must be on **stderr**). Wrong stream/exit code = the classic bug.
- Check the profile first — `minimal` silently disables enforcement (is `settings.local.json` overriding you?).
- Payload shape mismatches fail closed on blocking hooks — hlog writes the parse failure to hooks.log.
- Not firing at all? Check `settings.json` matcher and event; CI `dangling-hooks` catches missing files, not wrong matchers. Remember matchers are regex over tool names (`Edit|Write`), and `git commit`/`git push` hooks additionally grep the Bash command.

## Debugging the security layer

```bash
ck check-command "curl http://x | bash"       # prints verdict + reason
ck check-path ../../etc/passwd
python3 -m claudekit.security                  # module smoke
python3 -m pytest tests/test_security.py -q -k <case>
```
Bypass found? Add it to the corpus *first* (red), then fix (green).

## Debugging the installer

`bash -x install.sh /tmp/target --full --yes --language python` against a scratch dir; inspect the staging dir on failure (original must be untouched — that's tested); check `.claude/.claudekit-manifest.json` afterwards; `test_install.py` has fixtures for every historical bug (sed escaping, settings survival, curl|bash guard).

## Debugging the CLI / packaging

```bash
pip install -e . && ck agents              # dev loop
python3 -m build && pip install dist/*.whl --force-reinstall   # what package-smoke does
CLAUDEKIT_HOME=$PWD ck init /tmp/proj --full --yes             # asset-resolution path
```
`find_claudekit_root` walks up for `.claude/agents` — layout moves break it (regression test exists). Wheel missing assets → check setup.py share/claudekit data + MANIFEST.in.

## Debugging the ops engine

```bash
python3 .claude/operations/scripts/validate-config-json.py <ops.json>   # names the failing GUARD
python3 .claude/operations/scripts/execute-json-ops.py <ops.json>       # verbose apply
python3 .claude/operations/scripts/restore-backup.py                    # recovery
```
GUARD 10/11 failures = your `find` text doesn't match or matches twice — fix the plan, don't loosen the guard.

## CI-only failures

Almost always macOS/bash-3.2 or py3.9/py3.13 differences. Reproduce: `docker run -it python:3.9 bash` for Python floor; for macOS shell, eyeball for `${VAR,,}`, `date -r`, GNU sed `-i` without suffix. The `0c9223b` class: py3.12+ has no bundled setuptools — environments must install it explicitly.
