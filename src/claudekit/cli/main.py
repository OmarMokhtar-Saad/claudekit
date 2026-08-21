#!/usr/bin/env python3
"""ClaudeKit CLI — manage your ClaudeKit installation."""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

# When run as a raw script from a checkout (``python3 src/claudekit/cli/main.py``)
# rather than via the installed console script, the ``src`` root isn't on
# sys.path, so ``import claudekit.*`` would fail. Add it so sibling subpackages
# (e.g. claudekit.security) import cleanly in both modes.
if __package__ in (None, ""):
    _SRC_ROOT = Path(__file__).resolve().parents[2]
    if str(_SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(_SRC_ROOT))


def _resolve_version() -> str:
    """Single source of truth: installed package metadata, with a source-checkout fallback."""
    try:
        # Distribution name is "claude-kit" (the "claudekit" PyPI name was taken);
        # the import package and console scripts remain "claudekit"/"ck".
        return metadata.version("claude-kit")
    except metadata.PackageNotFoundError:
        return "2.1.0"


__version__ = _resolve_version()

# BEGIN GENERATED:counts - owned by scripts/gen-docs.py; never hand-edit.
# Regenerate with: python3 scripts/gen-docs.py
EXPECTED_AGENTS = 29
EXPECTED_COMMANDS = 42
EXPECTED_SKILLS = 76
# END GENERATED:counts

# Colors
class C:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    BOLD = '\033[1m'
    NC = '\033[0m'

def info(msg): print(f"{C.BLUE}[*]{C.NC} {msg}")
def ok(msg): print(f"{C.GREEN}[✓]{C.NC} {msg}")
def warn(msg): print(f"{C.YELLOW}[!]{C.NC} {msg}")
# "not applicable to this install" - neither a pass nor a problem. Without it,
# a mode-aware check has to fake a PASS, inflating the passed count.
def skip(msg): print(f"{C.CYAN}[-]{C.NC} {msg}")
def err(msg): print(f"{C.RED}[✗]{C.NC} {msg}", file=sys.stderr)


def find_claudekit_root():
    """Find the ClaudeKit source directory.

    Resolution order: ``$CLAUDEKIT_HOME`` (if it points at a real install),
    then the repo containing this file, then common home-directory locations.
    """
    # Explicit override wins.
    env_home = os.environ.get("CLAUDEKIT_HOME")
    if env_home:
        p = Path(env_home).expanduser()
        if (p / ".claude" / "agents").exists():
            return p
    # Walk up from this file looking for the repo/install root. Robust to the
    # src-layout nesting depth (src/claudekit/cli/main.py -> repo root).
    for parent in Path(__file__).resolve().parents:
        if (parent / ".claude" / "agents").exists():
            return parent
    # Assets bundled into the wheel land under <prefix>/share/claudekit.
    for base in {sys.prefix, getattr(sys, "base_prefix", sys.prefix)}:
        cand = Path(base) / "share" / "claudekit"
        if (cand / ".claude" / "agents").exists():
            return cand
    # Check common locations
    for path in [Path.home() / "claudekit", Path.home() / ".claudekit"]:
        if (path / ".claude" / "agents").exists():
            return path
    return None


def cmd_init(args):
    """Initialize ClaudeKit in a project."""
    target = Path(args.target or ".").resolve()
    if not target.is_dir():
        err(f"Directory does not exist: {target}")
        return 1

    root = find_claudekit_root()
    if root is None:
        err("Cannot find ClaudeKit source. Set CLAUDEKIT_HOME or run from the repo.")
        return 1

    install_script = root / "install.sh"
    if not install_script.exists():
        err(f"install.sh not found at {install_script}")
        return 1

    cmd = ["bash", str(install_script), str(target)]
    if args.mode:
        cmd.append(f"--{args.mode}")
    if args.language:
        cmd.extend(["--language", args.language])
    if args.force:
        cmd.append("--force")
    if getattr(args, "yes", False):
        cmd.append("--yes")

    result = subprocess.run(cmd)
    return result.returncode


# Hook references in settings.json that must resolve to an installed file.
# Deliberately conservative: a token we cannot prove is a script is IGNORED,
# never required. Failing closed on an unprovable name would make `ck doctor`
# fail for everyone -- strictly worse than the delivery bug this guards.
_HOOK_REF_RE = re.compile(r"\.claude/hooks/([A-Za-z0-9._-]+)")
_HOOK_DENY_NAMES = {"compact-counter.txt", "settings.local.json"}
_HOOK_DENY_SUFFIXES = (".log", ".pyc", ".orig", ".rej", ".swp", "~")
_HOOK_SCRIPT_SUFFIXES = (".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".ts", ".rb", ".pl")
_HOOK_INTERP_RE = re.compile(
    r"(?:^|[\s\"'`;|&(])(?:python3|python|bash|sh|zsh|node|ruby|perl)\s+"
    r"(?:-[A-Za-z-]+\s+)*[\\\"'$]*[^\s\"'`;|&()]*$"
)


def _required_hook_scripts(text):
    """Names under .claude/hooks/ that ``text`` wires as executable scripts.

    A token counts only if it carries a known script extension or is directly
    preceded by an interpreter invocation; runtime-state names are subtracted.
    Hooks wired by absolute or ``~/`` paths are invisible here by design.
    """
    names = set()
    for match in _HOOK_REF_RE.finditer(text):
        name = match.group(1)
        if name in _HOOK_DENY_NAMES or name.endswith(_HOOK_DENY_SUFFIXES):
            continue
        prefix = text[max(0, match.start() - 80):match.start()]
        if name.endswith(_HOOK_SCRIPT_SUFFIXES) or _HOOK_INTERP_RE.search(prefix):
            names.add(name)
    return names


def _check_config_schema(data, check):
    """Apply the shipped `config.schema.json` to `.claude/hooks/config.json`.

    The schema shipped for weeks without a single executable applying it, so the
    config drifted out of conformance unnoticed. It is wired here rather than in a
    hook so it runs wherever `ck doctor` runs. `jsonschema` is an optional extra
    (`pip install 'claude-kit[validation]'`) because the runtime is dependency-free;
    when it is absent the check degrades to a warning instead of silently passing.
    """
    root = find_claudekit_root()
    schema_path = (root / "config.schema.json") if root else None
    label = "Hooks config.json matches config.schema.json"
    if schema_path is None or not schema_path.is_file():
        check(label, "warn", "config.schema.json not found in the ClaudeKit install")
        return
    try:
        import jsonschema
    except ImportError:
        check(label, "warn",
              "jsonschema not installed - run: pip install 'claude-kit[validation]'")
        return
    try:
        schema = json.loads(schema_path.read_text())
    except json.JSONDecodeError as e:
        check(label, False, f"config.schema.json is invalid JSON: {e}")
        return
    errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(data),
                    key=lambda e: list(e.path))
    if errors:
        detail = "; ".join(f"{'/'.join(str(x) for x in e.path) or '<root>'}: {e.message}"
                           for e in errors[:3])
        check(label, False, f"{len(errors)} schema violation(s): {detail}")
    else:
        check(label, True)


def cmd_doctor(args):
    """Run health checks on the current ClaudeKit installation."""
    print(f"\n{C.CYAN}ClaudeKit Doctor v{__version__}{C.NC}\n")

    checks_passed = 0
    checks_failed = 0
    checks_warned = 0
    checks_skipped = 0

    def check(name, condition, fix_hint=""):
        """True=pass, "skip"=not applicable to this install, "warn", else fail.

        "skip" is counted separately on purpose: it must not inflate the passed
        count (a minimal install is not as healthy as a full one) and it must not
        fail --strict (the absence it reports is by design).
        """
        nonlocal checks_passed, checks_failed, checks_warned, checks_skipped
        if condition is True:
            ok(name)
            checks_passed += 1
        elif condition == "skip":
            skip(f"{name} — {fix_hint}" if fix_hint else name)
            checks_skipped += 1
        elif condition == "warn":
            warn(f"{name} — {fix_hint}")
            checks_warned += 1
        else:
            err(f"{name} — {fix_hint}")
            checks_failed += 1

    # Python version
    py_ver = sys.version_info
    check(f"Python {py_ver.major}.{py_ver.minor}.{py_ver.micro}",
          py_ver >= (3, 8),
          "Python 3.8+ required")

    # Bash version
    try:
        result = subprocess.run(["bash", "--version"], capture_output=True, text=True)
        bash_ver = result.stdout.split("\n")[0]
        check(f"Bash available: {bash_ver[:60]}", True)
    except FileNotFoundError:
        check("Bash available", False, "Bash 4.0+ required")

    # Shell-lint tooling (used by the repo's own DoD gate, not installed by default)
    shellcheck_path = shutil.which("shellcheck")
    check("shellcheck available", True if shellcheck_path else "warn",
          "not on PATH — install with `brew install shellcheck` (macOS) or "
          "`apt-get install shellcheck` (Linux) to run the shell-lint DoD gate "
          "locally; CI runs it regardless")

    # Git
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        check(f"Git: {result.stdout.strip()}", True)
    except FileNotFoundError:
        check("Git available", False, "Git 2.0+ required")

    # .claude directory
    claude_dir = Path(".claude")
    check(".claude/ directory exists", claude_dir.is_dir(),
          "Run: claudekit init")

    if claude_dir.is_dir():
        # A `--minimal` install ships "agents, commands, and operations only", so no
        # skills, no hooks and no settings.json is the DESIGNED state there. Excusing
        # those absences takes two facts, both required:
        #   1. the manifest says mode == minimal, and
        #   2. the manifest's own file RECORD lists no skills, hooks or settings.json
        #      - i.e. this install never delivered them.
        # (2) is checked against the record, not the working tree, and that choice is
        # load-bearing in both directions. .claudekit-manifest.json is unsigned,
        # hand-editable JSON: flipping `mode` from full to minimal leaves `files` still
        # listing every skill and hook the full install recorded, so a half-delivered
        # full install stays red (the "shipped settings.json but not the hooks it
        # references" bug class). Conversely a user's OWN skill or hook dropped into a
        # minimal install does not revoke the excuse - it was never kit-managed.
        _manifest = _load_manifest(".") or {}
        _kit_optional = [rel for rel in (_manifest.get("files") or {})
                         if rel == "settings.json"
                         or rel.startswith(("skills/", "hooks/"))]
        minimal_install = _manifest.get("mode") == "minimal" and not _kit_optional

        # Agents
        agents = list((claude_dir / "agents").glob("*.md")) if (claude_dir / "agents").is_dir() else []
        agent_count = len([a for a in agents if a.name not in ("HANDOFF_PROTOCOL.md", "QUICK_START.md")])
        check(f"Agents installed: {agent_count}",
              agent_count >= EXPECTED_AGENTS,
              f"Expected ≥{EXPECTED_AGENTS} agents, found {agent_count}")

        # Commands
        commands = list((claude_dir / "commands").glob("*.md")) if (claude_dir / "commands").is_dir() else []
        check(f"Commands installed: {len(commands)}",
              len(commands) >= EXPECTED_COMMANDS,
              f"Expected ≥{EXPECTED_COMMANDS} commands, found {len(commands)}")

        # Skills
        skills_dir = claude_dir / "skills"
        skill_dirs = ([d for d in skills_dir.iterdir()
                       if d.is_dir() and (d / "SKILL.md").exists()]
                      if skills_dir.is_dir() else [])
        if minimal_install and len(skill_dirs) < EXPECTED_SKILLS:
            check(f"Skills installed: {len(skill_dirs)}", "skip",
                  "minimal install ships no skills")
        elif skills_dir.is_dir():
            check(f"Skills installed: {len(skill_dirs)}", len(skill_dirs) >= EXPECTED_SKILLS,
                  f"Expected ≥{EXPECTED_SKILLS} skills, found {len(skill_dirs)}")
        else:
            check("Skills directory", False, "Missing .claude/skills/")

        # Skills registry
        registry = claude_dir / "skills" / "skills-registry.json"
        if registry.exists():
            try:
                data = json.loads(registry.read_text())
                skill_ids = {s["id"] for s in data.get("skills", [])}
                for agent, skills in data.get("agentMapping", {}).items():
                    for sid in skills:
                        if sid not in skill_ids:
                            warn(f"  Registry: agent '{agent}' references unknown skill '{sid}'")
                            checks_warned += 1
                check(f"Skills registry valid: {len(skill_ids)} skills, {len(data.get('agentMapping', {}))} agents", True)
            except (json.JSONDecodeError, KeyError) as e:
                check("Skills registry", False, f"Invalid JSON: {e}")
        elif minimal_install:
            check("Skills registry", "skip", "not shipped in minimal mode")
        else:
            check("Skills registry", False, "Missing skills-registry.json")

        # Operations scripts
        scripts_dir = claude_dir / "operations" / "scripts"
        for script in ["validate-config-json.py", "execute-json-ops.py",
                       "extract-json-from-plan.py", "restore-backup.py", "shared.py",
                       "review-record.py"]:
            check(f"Script: {script}",
                  (scripts_dir / script).exists(),
                  f"Missing {scripts_dir / script}")

        # Hooks
        hooks_dir = claude_dir / "hooks"
        if hooks_dir.is_dir():
            for hook in ["pre-commit.sh", "post-implement.sh", "pre-push.sh", "pre-plan.sh", "post-tool-use.sh"]:
                hook_path = hooks_dir / hook
                if hook_path.exists():
                    is_exec = os.access(hook_path, os.X_OK)
                    check(f"Hook: {hook} {'(executable)' if is_exec else ''}",
                          True if is_exec else "warn",
                          f"Not executable. Run: chmod +x {hook_path}")
                else:
                    check(f"Hook: {hook}",
                          "skip" if minimal_install else "warn",
                          "not shipped in minimal mode" if minimal_install
                          else "Not installed (minimal mode?)")

        # settings.json
        settings = claude_dir / "settings.json"
        if settings.exists():
            try:
                data = json.loads(settings.read_text())
                hook_events = list(data.get("hooks", {}).keys())
                check(f"settings.json valid: {len(hook_events)} hook events", True)
            except json.JSONDecodeError as e:
                check("settings.json", False, f"Invalid JSON: {e}")
        else:
            check("settings.json",
                  "skip" if minimal_install else "warn",
                  "not shipped in minimal mode" if minimal_install
                  else "No Claude Code hooks configured")

        # Every hook COMMAND in settings.json must resolve to an installed FILE.
        # This is the mechanical guard for the whole bug class: a wired hook that
        # was never delivered makes Claude Code run `python3 <missing>`, which
        # exits 2 -- and exit 2 on PreToolUse blocks every tool call. The older
        # checks (hardcoded .sh list + "is settings.json valid JSON") reported a
        # healthy install on a completely blocked project. is_file(), not
        # exists(): a directory named foo.py is not a runnable hook.
        if settings.exists():
            try:
                settings_text = settings.read_text(encoding="utf-8")
            except OSError:
                settings_text = ""
            wired = _required_hook_scripts(settings_text)
            unresolved = sorted(n for n in wired if not (hooks_dir / n).is_file())
            if not wired:
                check("Wired hooks resolve", "warn",
                      "settings.json wires no hook scripts")
            elif unresolved:
                check(f"Wired hooks resolve ({len(wired)} referenced)", False,
                      "settings.json references missing hooks: "
                      + ", ".join(unresolved)
                      + " - every tool call is blocked. Run: claudekit update")
            else:
                check(f"Wired hooks resolve ({len(wired)} referenced)", True)

        # Config.json
        config = hooks_dir / "config.json" if hooks_dir.is_dir() else None
        if config and config.exists():
            try:
                data = json.loads(config.read_text())
                project = data.get("project", {})
                for cmd_name in ["build_cmd", "test_cmd", "lint_cmd"]:
                    val = project.get(cmd_name, "")
                    if not val:
                        warn(f"  config.json: {cmd_name} not configured")
                        checks_warned += 1
                check("Hooks config.json valid", True)
                _check_config_schema(data, check)
            except json.JSONDecodeError as e:
                check("Hooks config.json", False, f"Invalid JSON: {e}")

    # Summary
    print(f"\n{'='*40}")
    total = checks_passed + checks_failed + checks_warned + checks_skipped
    print(f"  Passed:   {C.GREEN}{checks_passed}{C.NC}/{total}")
    if checks_skipped:
        print(f"  Skipped:  {C.CYAN}{checks_skipped}{C.NC}/{total} (not applicable to this install)")
    if checks_warned:
        print(f"  Warnings: {C.YELLOW}{checks_warned}{C.NC}/{total}")
    if checks_failed:
        print(f"  Failed:   {C.RED}{checks_failed}{C.NC}/{total}")
    print(f"{'='*40}\n")

    if checks_failed:
        err("Some checks failed. Fix the issues above.")
        return 1
    elif checks_warned:
        if getattr(args, "strict", False):
            err("Warnings present and --strict is set.")
            return 1
        if checks_skipped:
            warn(f"All applicable checks passed with warnings "
                 f"({checks_skipped} not applicable to this install).")
        else:
            warn("All checks passed with warnings.")
        return 0
    else:
        if checks_skipped:
            ok(f"All applicable checks passed ({checks_skipped} not applicable "
               "to this install).")
        else:
            ok("All checks passed!")
        return 0


def cmd_validate(args):
    """Validate an ops.json config."""
    script = Path(".claude/operations/scripts/validate-config-json.py")
    if not script.exists():
        err("Validator not found. Run: claudekit init")
        return 1
    cmd = [sys.executable, str(script), args.config]
    if args.verbose:
        cmd.append("--verbose")
    return subprocess.run(cmd).returncode


def cmd_execute(args):
    """Execute an ops.json config."""
    script = Path(".claude/operations/scripts/execute-json-ops.py")
    if not script.exists():
        err("Executor not found. Run: claudekit init")
        return 1
    cmd = [sys.executable, str(script), args.config]
    if args.dry_run:
        cmd.append("--dry-run")
    if args.verbose:
        cmd.append("--verbose")
    return subprocess.run(cmd).returncode


def cmd_rollback(args):
    """Rollback from a backup."""
    script = Path(".claude/operations/scripts/restore-backup.py")
    if not script.exists():
        err("Restore script not found. Run: claudekit init")
        return 1
    cmd = [sys.executable, str(script)]
    if args.backup:
        cmd.extend(["--backup", args.backup])
    elif args.list:
        cmd.append("--list")
    else:
        cmd.append("--list")
    if args.force:
        cmd.append("--force")
    if args.dry_run:
        cmd.append("--dry-run")
    return subprocess.run(cmd).returncode


def cmd_agents(args):
    """List installed agents."""
    agents_dir = Path(".claude/agents")
    if not agents_dir.is_dir():
        err("No agents found. Run: claudekit init")
        return 1

    print(f"\n{C.BOLD}Installed Agents{C.NC}\n")
    for f in sorted(agents_dir.glob("*.md")):
        if f.name in ("HANDOFF_PROTOCOL.md", "QUICK_START.md"):
            continue
        # Parse frontmatter
        text = f.read_text()
        name = f.stem
        model = "unknown"
        desc = ""
        if text.startswith("---"):
            try:
                end = text.index("---", 3)
                fm = text[3:end]
                for line in fm.strip().split("\n"):
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("model:"):
                        model = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()[:80]
            except ValueError:
                pass
        print(f"  {C.CYAN}{name:20}{C.NC} model={model:8} {desc}")
    print()
    return 0


MANIFEST_NAME = ".claudekit-manifest.json"

# Kit-managed asset locations inside .claude/ (what installs create and what
# diff-without-a-manifest may safely compare against the kit source tree).
MANAGED_DIRS = ("agents", "commands", "skills", "hooks", "operations/scripts")
MANAGED_FILES = ("settings.json",)
# Never compared: expected to differ per-project or generated at runtime.
DIFF_IGNORED = {"hooks/config.json", "settings.local.json"}
DIFF_IGNORED_NAMES = {"compact-counter.txt", "cost-tracker.log"}  # hook runtime state


def _sha256(path):
    import hashlib
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def _manifest_base(target):
    """The install writes the manifest into <target>/.claude/ with file paths
    relative to that directory."""
    return Path(target) / ".claude"


def _load_manifest(target):
    """Load a target project's install manifest, or return None."""
    mpath = _manifest_base(target) / MANIFEST_NAME
    if not mpath.exists():
        return None
    try:
        return json.loads(mpath.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _managed_files(base):
    """Paths (relative to ``base``, POSIX separators) of kit-managed assets
    under a .claude tree. Skips runtime artifacts and per-project overrides."""
    found = []
    for rel in MANAGED_FILES:
        if (base / rel).is_file():
            found.append(rel)
    for d in MANAGED_DIRS:
        droot = base / d
        if not droot.is_dir():
            continue
        for root, dirs, names in os.walk(droot):
            dirs[:] = [x for x in dirs if x != "__pycache__"]
            for n in names:
                if n.endswith((".pyc", ".log")) or n in DIFF_IGNORED_NAMES:
                    continue
                rel = (Path(root) / n).relative_to(base).as_posix()
                if rel not in DIFF_IGNORED:
                    found.append(rel)
    return found


def _diff_against_source(target, root):
    """Manifest-less fallback: compare a project's managed assets against the
    kit source tree. Provenance is unknown (no install-time hashes), so a
    difference only means "not the current kit version"."""
    base = _manifest_base(target)
    kit = root / ".claude"
    proj = set(_managed_files(base))
    kitf = set(_managed_files(kit))
    identical, differs, custom, not_installed = [], [], [], []
    for rel in sorted(proj | kitf):
        if rel in proj and rel in kitf:
            (identical if _sha256(base / rel) == _sha256(kit / rel) else differs).append(rel)
        elif rel in proj:
            custom.append(rel)
        else:
            not_installed.append(rel)
    return identical, differs, custom, not_installed


def _classify_manifest(target, manifest):
    """Compare installed files against the manifest.

    Returns (modified, missing, unchanged) lists of paths relative to .claude/.
    """
    base = _manifest_base(target)
    modified, missing, unchanged = [], [], []
    for rel, expected in sorted(manifest.get("files", {}).items()):
        path = base / rel
        if not path.exists():
            missing.append(rel)
            continue
        actual = _sha256(path)
        if actual == expected:
            unchanged.append(rel)
        else:
            modified.append(rel)
    return modified, missing, unchanged


def cmd_diff(args):
    """Show local modifications to ClaudeKit-managed files (vs. the manifest,
    falling back to a kit-source comparison for pre-manifest installs)."""
    target = Path(args.target or ".").resolve()
    manifest = _load_manifest(target)
    root = find_claudekit_root()

    if manifest is None:
        if root is None or not (root / ".claude").is_dir():
            err(f"No {MANIFEST_NAME} found in {target} and no kit source available "
                "for fallback comparison. Set CLAUDEKIT_HOME or run: claudekit init")
            return 1
        if not (_manifest_base(target)).is_dir():
            err(f"No .claude/ directory in {target}. Run: claudekit init")
            return 1
        identical, differs, custom, not_installed = _diff_against_source(target, root)
        print(f"\n{C.CYAN}ClaudeKit diff{C.NC} — no install manifest (pre-manifest "
              f"install); comparing against kit source at {root}\n")
        warn("Provenance unknown: 'differs' may be a local edit OR an older kit version.")
        for rel in differs:
            warn(f"differs:       {rel}")
        for rel in custom:
            info(f"custom:        {rel}")
        for rel in not_installed[:15]:
            print(f"    not installed: {rel}")
        if len(not_installed) > 15:
            print(f"    ... and {len(not_installed) - 15} more not installed")
        print(f"\n  {len(identical)} identical, {len(differs)} differ, "
              f"{len(custom)} custom, {len(not_installed)} not installed.")
        info("Run `claudekit update` to refresh (backs up first, preserves custom assets).")
        return 0

    modified, missing, unchanged = _classify_manifest(target, manifest)
    print(f"\n{C.CYAN}ClaudeKit diff{C.NC} — installed v{manifest.get('version', '?')} "
          f"({manifest.get('mode', '?')} mode)\n")
    base = _manifest_base(target)
    kit = (root / ".claude") if root else None
    for rel in modified:
        label = "modified"
        if kit is not None:
            kit_hash = _sha256(kit / rel) if (kit / rel).exists() else None
            expected = manifest.get("files", {}).get(rel)
            actual = _sha256(base / rel)
            if actual == kit_hash:
                label = "kit-updated"      # already matches the newer kit source
            elif kit_hash == expected:
                label = "locally modified"  # kit unchanged; the edit is local
            elif kit_hash is not None:
                label = "both changed"      # local edit AND the kit moved on
        warn(f"{label}: {rel}")
    for rel in missing:
        err(f"missing:  {rel}")
    custom = sorted(set(_managed_files(base)) - set(manifest.get("files", {})))
    for rel in custom:
        info(f"custom:   {rel}")
    if not modified and not missing:
        ok(f"All {len(unchanged)} managed files match the manifest"
           + (f" ({len(custom)} custom files besides)." if custom else "."))
    else:
        print(f"\n  {len(modified)} modified, {len(missing)} missing, "
              f"{len(unchanged)} unchanged, {len(custom)} custom.")
    return 0


def cmd_uninstall(args):
    """Remove ClaudeKit-managed files, acting ONLY on files the receipt owns.

    The manifest records a sha256 per installed file. That receipt is what makes
    ownership decidable: a file whose digest still matches is ours and ours only,
    so removing it destroys nothing the user wrote. A file whose digest has
    changed is MIXED ownership - our text plus their edits - and a file that is
    not in the manifest at all is theirs.

    Before this, uninstall deleted every path the manifest LISTED without ever
    comparing a digest, so a prompt a user had spent a week tuning was removed as
    readily as an untouched one. Deleting on unverified ownership is the failure
    mode the receipt exists to prevent, and it fails closed here: mixed ownership
    stops the whole operation rather than guessing.
    """
    import datetime
    target = Path(args.target or ".").resolve()
    manifest = _load_manifest(target)
    if manifest is None:
        err(f"No {MANIFEST_NAME} found in {target}. Nothing to uninstall.")
        return 1

    listed = sorted(manifest.get("files", {}).keys())
    if not listed:
        warn("Manifest lists no files.")
        return 0

    modified, missing, unchanged = _classify_manifest(target, manifest)

    if args.dry_run:
        info(f"[dry-run] {target}")
        info(f"  {len(unchanged)} receipt-owned file(s) would be removed")
        for rel in unchanged:
            print(f"    {rel}")
        if modified:
            info(f"  {len(modified)} locally-modified file(s) would be KEPT")
            for rel in modified:
                print(f"    {rel}")
        if missing:
            info(f"  {len(missing)} manifest file(s) already absent")
        return 0

    # Fail closed on mixed ownership. --force is the only way past it, and it is
    # named for what it does rather than hidden behind --yes, which merely skips
    # a prompt.
    # getattr, not attribute access: cmd_* take a Namespace that callers build by
    # hand as well as one argparse builds, and a missing new flag must not raise.
    force = getattr(args, "force", False)
    keep_modified = getattr(args, "keep_modified", False)

    if modified and not (force or keep_modified):
        err(f"Refusing to uninstall: {len(modified)} managed file(s) have local "
            f"modifications, so they are no longer solely ClaudeKit's to delete:")
        for rel in modified:
            print(f"    {rel}")
        info("Choose explicitly:")
        info("  --keep-modified   remove only the files the receipt still owns")
        info("  --force           remove them too (your edits are backed up first)")
        return 1

    removable = list(unchanged) if not force else [
        rel for rel in listed if (_manifest_base(target) / rel).exists()]

    if not args.yes:
        extra = " (including locally-modified files)" if force and modified else ""
        resp = input(f"Remove {len(removable)} ClaudeKit files from {target}{extra}? [y/N] ")
        if resp.strip().lower() not in ("y", "yes"):
            info("Aborted.")
            return 0

    base = _manifest_base(target)
    stamp = args.stamp or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = target / "backups" / f"uninstall-{stamp}"
    removed = 0
    for rel in removable:
        path = base / rel
        if not path.exists():
            continue
        dest = backup / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.replace(dest)
            removed += 1
        except OSError as e:
            warn(f"could not remove {rel}: {e}")

    kept = [rel for rel in modified if (base / rel).exists()]
    if kept:
        # The manifest must not outlive the files it describes as removed, but a
        # kept file with no receipt would read as user-authored on the next
        # install. Rewrite the receipt to cover exactly what is still ours.
        remaining = {rel: manifest["files"][rel] for rel in kept}
        manifest["files"] = remaining
        try:
            (base / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2))
        except OSError as e:
            warn(f"could not rewrite manifest: {e}")
    else:
        (base / MANIFEST_NAME).unlink(missing_ok=True)

    if base.exists():
        for root, _dirs, _files in os.walk(base, topdown=False):
            try:
                if not os.listdir(root):
                    os.rmdir(root)
            except OSError:
                pass

    ok(f"Removed {removed} file(s). Backup at {backup}")
    if kept:
        info(f"Kept {len(kept)} locally-modified file(s):")
        for rel in kept:
            print(f"    {rel}")
    return 0


def cmd_update(args):
    """Re-install ClaudeKit over an existing project, preserving local edits via backup."""
    target = Path(args.target or ".").resolve()
    manifest = _load_manifest(target)
    if manifest is None and not (_manifest_base(target)).is_dir():
        err(f"No .claude/ directory in {target}. Use `claudekit init` for a fresh install.")
        return 1

    root = find_claudekit_root()
    if root is None:
        err("Cannot find ClaudeKit source. Set CLAUDEKIT_HOME or run from the repo.")
        return 1
    install_script = root / "install.sh"
    if not install_script.exists():
        err(f"install.sh not found at {install_script}")
        return 1

    if manifest is None:
        warn(f"No {MANIFEST_NAME} in {target} — pre-manifest (legacy) install.")
        info("The installer will back up the existing .claude/ and write a fresh "
             "install (full mode) with a manifest; custom agents/commands/skills "
             "are preserved from the backup.")
        if not args.yes:
            resp = input("Continue with legacy update? [y/N] ")
            if resp.strip().lower() not in ("y", "yes"):
                info("Aborted.")
                return 0
    else:
        modified, missing, _ = _classify_manifest(target, manifest)
        if modified:
            warn(f"{len(modified)} locally-modified managed files will be overwritten "
                 "(the installer backs up the previous .claude/ first):")
            for rel in modified:
                print(f"    {rel}")
            if not args.yes:
                resp = input("Continue with update? [y/N] ")
                if resp.strip().lower() not in ("y", "yes"):
                    info("Aborted.")
                    return 0

    mode = (manifest.get("mode") if manifest else None) or "full"
    cmd = ["bash", str(install_script), str(target), f"--{mode}", "--force", "--yes"]
    lang = manifest.get("language") if manifest else None
    if lang and lang != "auto":
        cmd.extend(["--language", lang])
    result = subprocess.run(cmd)
    if result.returncode == 0:
        ok(f"Updated {target} to v{__version__} ({mode} mode).")
    return result.returncode


def cmd_eval(args):
    """Run the behavioral eval harness (task 010). Requires the kit source tree."""
    root = find_claudekit_root()
    if root is None or not (root / "scripts" / "run-evals.py").exists():
        err("Eval harness not found. Evals run from the ClaudeKit source tree "
            "(set CLAUDEKIT_HOME or run inside the repo).")
        return 1
    cmd = [sys.executable, str(root / "scripts" / "run-evals.py")]
    if args.list:
        cmd.append("--list")
    if args.dry_run:
        cmd.append("--dry-run")
    if args.only:
        cmd.extend(["--only", args.only])
    return subprocess.run(cmd, cwd=root).returncode


def cmd_check_command(args):
    """Validate a shell command against the security denylist (speed bump)."""
    from claudekit.security.cli import check_command
    return check_command(args.command_str)


def cmd_check_path(args):
    """Validate a file path against the path guard."""
    from claudekit.security.cli import check_path
    return check_path(args.path_str)


def cmd_config(args):
    """Show or edit configuration."""
    config_path = Path(".claude/hooks/config.json")
    if not config_path.exists():
        err("No config found. Run: claudekit init --full")
        return 1

    if args.key:
        data = json.loads(config_path.read_text())
        keys = args.key.split(".")
        val = data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                err(f"Key not found: {args.key}")
                return 1
        print(json.dumps(val, indent=2) if isinstance(val, (dict, list)) else val)
    else:
        print(config_path.read_text())
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog="claudekit",
        description=f"ClaudeKit CLI v{__version__} — Multi-agent orchestration for Claude Code",
    )
    parser.add_argument("--version", action="version", version=f"claudekit {__version__}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # init
    p = sub.add_parser("init", help="Install ClaudeKit into a project")
    p.add_argument("target", nargs="?", default=".", help="Target directory (default: .)")
    p.add_argument("--mode", choices=["full", "minimal"], default="full")
    p.add_argument("--full", dest="mode", action="store_const", const="full",
                   help="Full install (default)")
    p.add_argument("--minimal", dest="mode", action="store_const", const="minimal",
                   help="Minimal install (agents + commands + operations)")
    p.add_argument("--language", help="Pre-configure language")
    p.add_argument("--force", action="store_true", help="Overwrite existing installation")
    p.add_argument("--yes", "--non-interactive", dest="yes", action="store_true",
                   help="Assume yes to prompts (non-interactive)")

    # doctor
    p = sub.add_parser("doctor", help="Run health checks on installation")
    p.add_argument("--strict", action="store_true",
                   help="Treat warnings as failures (exit 1)")

    # validate
    p = sub.add_parser("validate", help="Validate an ops.json config")
    p.add_argument("config", help="Path to ops.json")
    p.add_argument("-v", "--verbose", action="store_true")

    # execute
    p = sub.add_parser("execute", help="Execute an ops.json config")
    p.add_argument("config", help="Path to ops.json")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")

    # rollback
    p = sub.add_parser("rollback", help="Rollback from backup")
    p.add_argument("--backup", help="Backup directory")
    p.add_argument("--list", action="store_true", help="List available backups")
    p.add_argument("--force", action="store_true", help="Skip confirmation")
    p.add_argument("--dry-run", action="store_true")

    # agents
    sub.add_parser("agents", help="List installed agents")

    # diff
    p = sub.add_parser("diff", help="Show local edits to managed files (vs. manifest)")
    p.add_argument("target", nargs="?", default=".", help="Project directory (default: .)")

    # update
    p = sub.add_parser("update", help="Re-install over an existing project (backs up first)")
    p.add_argument("target", nargs="?", default=".", help="Project directory (default: .)")
    p.add_argument("--yes", "--non-interactive", dest="yes", action="store_true",
                   help="Assume yes to prompts")

    # uninstall
    p = sub.add_parser("uninstall", help="Remove managed files (backs them up first)")
    p.add_argument("target", nargs="?", default=".", help="Project directory (default: .)")
    p.add_argument("--yes", "--non-interactive", dest="yes", action="store_true",
                   help="Assume yes to prompts")
    p.add_argument("--dry-run", action="store_true", help="List files without removing")
    p.add_argument("--keep-modified", action="store_true",
                   help="Remove only files the manifest receipt still owns, "
                        "leaving locally-modified ones in place")
    p.add_argument("--force", action="store_true",
                   help="Remove managed files even where local modifications mean "
                        "ClaudeKit no longer solely owns them (backed up first)")
    p.add_argument("--stamp", help=argparse.SUPPRESS)  # deterministic backup name (tests)

    # eval
    p = sub.add_parser("eval", help="Run behavioral evals against the prompt corpus "
                                    "(costs real API calls; --dry-run is free)")
    p.add_argument("--list", action="store_true", help="List available evals")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate definitions + workspace build without running agents")
    p.add_argument("--only", help="Run a single eval by id")

    # check-command
    p = sub.add_parser("check-command",
                       help="Validate a shell command (exit 0 allow / 2 block)")
    p.add_argument("command_str", metavar="command", help="Command string to validate")

    # check-path
    p = sub.add_parser("check-path",
                       help="Validate a file path (exit 0 allow / 2 block)")
    p.add_argument("path_str", metavar="path", help="File path to validate")

    # config
    p = sub.add_parser("config", help="Show or query configuration")
    p.add_argument("key", nargs="?", help="Config key (dot notation, e.g. project.build_cmd)")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    commands = {
        "init": cmd_init,
        "doctor": cmd_doctor,
        "validate": cmd_validate,
        "execute": cmd_execute,
        "rollback": cmd_rollback,
        "agents": cmd_agents,
        "diff": cmd_diff,
        "update": cmd_update,
        "uninstall": cmd_uninstall,
        "eval": cmd_eval,
        "check-command": cmd_check_command,
        "check-path": cmd_check_path,
        "config": cmd_config,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
