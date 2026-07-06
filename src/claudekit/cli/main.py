#!/usr/bin/env python3
"""ClaudeKit CLI — manage your ClaudeKit installation."""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path


def _resolve_version() -> str:
    """Single source of truth: installed package metadata, with a source-checkout fallback."""
    try:
        return metadata.version("claudekit")
    except metadata.PackageNotFoundError:
        return "2.1.0"


__version__ = _resolve_version()

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
def err(msg): print(f"{C.RED}[✗]{C.NC} {msg}", file=sys.stderr)


def find_claudekit_root():
    """Find the ClaudeKit source directory."""
    # Check if we're inside the claudekit repo
    here = Path(__file__).resolve().parent.parent.parent
    if (here / ".claude" / "agents").exists():
        return here
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

    result = subprocess.run(cmd)
    return result.returncode


def cmd_doctor(args):
    """Run health checks on the current ClaudeKit installation."""
    print(f"\n{C.CYAN}ClaudeKit Doctor v{__version__}{C.NC}\n")

    checks_passed = 0
    checks_failed = 0
    checks_warned = 0

    def check(name, condition, fix_hint=""):
        nonlocal checks_passed, checks_failed, checks_warned
        if condition is True:
            ok(name)
            checks_passed += 1
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
        # Agents
        agents = list((claude_dir / "agents").glob("*.md")) if (claude_dir / "agents").is_dir() else []
        agent_count = len([a for a in agents if a.name not in ("HANDOFF_PROTOCOL.md", "QUICK_START.md")])
        check(f"Agents installed: {agent_count}",
              agent_count >= 9,
              f"Expected ≥9 agents, found {agent_count}")

        # Commands
        commands = list((claude_dir / "commands").glob("*.md")) if (claude_dir / "commands").is_dir() else []
        check(f"Commands installed: {len(commands)}",
              len(commands) >= 8,
              f"Expected ≥8 commands, found {len(commands)}")

        # Skills
        skills_dir = claude_dir / "skills"
        if skills_dir.is_dir():
            skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").exists()]
            check(f"Skills installed: {len(skill_dirs)}", len(skill_dirs) >= 27,
                  f"Expected ≥27 skills, found {len(skill_dirs)}")
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
        else:
            check("Skills registry", False, "Missing skills-registry.json")

        # Operations scripts
        scripts_dir = claude_dir / "operations" / "scripts"
        for script in ["validate-config-json.py", "execute-json-ops.py", "restore-backup.py", "shared.py"]:
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
                    check(f"Hook: {hook}", "warn", "Not installed (minimal mode?)")

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
            check("settings.json", "warn", "No Claude Code hooks configured")

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
            except json.JSONDecodeError as e:
                check("Hooks config.json", False, f"Invalid JSON: {e}")

    # Summary
    print(f"\n{'='*40}")
    total = checks_passed + checks_failed + checks_warned
    print(f"  Passed:   {C.GREEN}{checks_passed}{C.NC}/{total}")
    if checks_warned:
        print(f"  Warnings: {C.YELLOW}{checks_warned}{C.NC}/{total}")
    if checks_failed:
        print(f"  Failed:   {C.RED}{checks_failed}{C.NC}/{total}")
    print(f"{'='*40}\n")

    if checks_failed:
        err("Some checks failed. Fix the issues above.")
        return 1
    elif checks_warned:
        warn("All checks passed with warnings.")
        return 0
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
        color = ""
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
                    elif line.startswith("color:"):
                        color = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()[:80]
            except ValueError:
                pass
        print(f"  {C.CYAN}{name:20}{C.NC} model={model:8} {desc}")
    print()
    return 0


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
    p.add_argument("--language", help="Pre-configure language")
    p.add_argument("--force", action="store_true", help="Overwrite existing installation")

    # doctor
    sub.add_parser("doctor", help="Run health checks on installation")

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
        "config": cmd_config,
    }

    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
