#!/usr/bin/env bash
# -E (errtrace): the ERR trap is inherited by shell functions, so a failure
# inside a helper like render_template still triggers staging cleanup.
set -Eeuo pipefail

# ClaudeKit Installer
# Usage: ./install.sh [TARGET_DIR] [--full|--minimal] [--language LANG] [--with-mcp] [--with-i18n]

# Derived, never hardcoded. This sat at 2.1.0 through the 3.0.0 AND 3.1.0 releases, so
# every install manifest -- the receipt `ck diff` and `ck uninstall` read for provenance --
# recorded a version two releases stale. It is the FIFTH version site; hard rule 7 named
# three, then four. The rule now points at the test rather than listing them, and the test
# reads this file.
#
# Absent pyproject.toml is NOT fatal, and the first cut of this got that wrong: installing
# from a tarball or a copied tree ships install.sh without it, and an `exit 1` there turned
# provenance into a precondition -- the exact mistake
# test_installing_from_a_non_git_source_still_succeeds already existed to catch, and did.
# "unknown" matches how this file already treats an unpinnable commit: record the gap,
# never fabricate a value.
#
# The range is anchored to the [project] table. An unanchored ^version match would
# take a version = key from any [tool.*] table sorted above it, silently stamping the
# wrong version -- the same silent-staleness shape this block exists to remove.
VERSION=""   # never inherit an exported VERSION from the caller environment
_ck_pyproject="$(dirname "${BASH_SOURCE[0]}")/pyproject.toml"
if [[ -r "$_ck_pyproject" ]]; then
    VERSION="$(sed -n '/^\[project\]/,/^\[/{ s/^version = "\([^"]*\)"/\1/p; }' "$_ck_pyproject" | head -1)"
fi
VERSION="${VERSION:-unknown}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_SRC="$SCRIPT_DIR/.claude"

# curl|bash guard: piped execution has no source tree to copy from.
if [[ ! -d "$CLAUDE_SRC" ]]; then
    echo "ERROR: ClaudeKit source not found next to this script." >&2
    echo "Clone the repo and run ./install.sh from the checkout, e.g.:" >&2
    echo "  git clone https://github.com/OmarMokhtar-Saad/claudekit.git && cd claudekit && ./install.sh <target>" >&2
    exit 1
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_banner() {
    echo -e "${CYAN}"
    echo "  ╔═══════════════════════════════════════╗"
    echo "  ║         ClaudeKit v${VERSION}              ║"
    echo "  ║   Multi-Agent System for Claude Code  ║"
    echo "  ╚═══════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() { echo -e "${BLUE}[*]${NC} $1"; }
print_ok()   { echo -e "${GREEN}[✓]${NC} $1"; }
print_warn() { echo -e "${YELLOW}[!]${NC} $1"; }
print_err()  { echo -e "${RED}[✗]${NC} $1"; }

# Defaults
TARGET_DIR=""
MODE="full"
LANGUAGE=""
FORCE=false
WITH_MCP=false
WITH_I18N=false
ASSUME_YES=false

usage() {
    echo "Usage: $0 [TARGET_DIR] [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --full          Install all components (default)"
    echo "  --minimal       Install agents, commands, and operations only"
    echo "  --language LANG Pre-configure for language (python|typescript|java|go|kotlin|swift|rust|csharp|ruby|php)"
    echo "  --with-mcp      Install MCP server configurations"
    echo "  --with-i18n     Install internationalization files"
    echo "  --force         Overwrite existing .claude directory (backed up first)"
    echo "  --yes           Non-interactive: assume yes to prompts (for CI)"
    echo "  --help          Show this help"
    echo ""
    echo "Examples:"
    echo "  $0 /path/to/my-project --full --language python"
    echo "  $0 . --minimal"
    echo "  $0 ~/projects/my-app --language typescript"
}

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --full)     MODE="full"; shift ;;
        --minimal)  MODE="minimal"; shift ;;
        --language) LANGUAGE="$2"; shift 2 ;;
        --with-mcp) WITH_MCP=true; shift ;;
        --with-i18n) WITH_I18N=true; shift ;;
        --force)    FORCE=true; shift ;;
        --yes|--non-interactive) ASSUME_YES=true; shift ;;
        --help)     usage; exit 0 ;;
        -*)         print_err "Unknown option: $1"; usage; exit 1 ;;
        *)
            if [[ -n "$TARGET_DIR" ]]; then
                print_err "Unexpected argument: $1 (target directory already set to $TARGET_DIR)"
                exit 1
            fi
            TARGET_DIR="$1"; shift ;;
    esac
done

# Validate target
if [[ -z "$TARGET_DIR" ]]; then
    if [[ -t 0 ]] && [[ "$ASSUME_YES" != true ]]; then
        echo -n "Target project directory: "
        read -r TARGET_DIR
    else
        print_err "No target directory given (stdin is not a TTY). Pass it as an argument."
        exit 1
    fi
fi

TARGET_DIR="$(cd "$TARGET_DIR" 2>/dev/null && pwd)" || { print_err "Cannot access target directory"; exit 1; }

if [[ ! -d "$TARGET_DIR" ]]; then
    print_err "Directory does not exist: $TARGET_DIR"
    exit 1
fi

FINAL_DEST="$TARGET_DIR/.claude"
STAGING="$TARGET_DIR/.claude.staging.$$"
DEST="$STAGING"   # install writes to staging; atomically swapped into place on success
BACKUP=""

# Cleanup on failure removes ONLY the staging dir. The user's real .claude is
# never touched until the atomic swap succeeds — no more rm -rf of live data.
_cleanup_on_failure() {
    [[ -d "$STAGING" ]] && rm -rf "$STAGING"
    print_err "Installation failed. Your existing .claude (if any) was left untouched."
}
trap '_cleanup_on_failure' ERR
rm -rf "$STAGING" 2>/dev/null || true

# Check for existing installation
if [[ -d "$FINAL_DEST" ]] && [[ "$FORCE" != true ]] && [[ "$ASSUME_YES" != true ]]; then
    if [[ -t 0 ]]; then
        print_warn "$FINAL_DEST already exists. It will be backed up before reinstall."
        echo -n "Continue? (y/N): "
        read -r confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            echo "Installation cancelled."
            exit 0
        fi
    else
        print_err "$FINAL_DEST exists. Re-run with --force or --yes to reinstall (it is backed up first)."
        exit 1
    fi
fi

# Detect language if not specified
detect_language() {
    if [[ -f "$TARGET_DIR/pyproject.toml" ]] || [[ -f "$TARGET_DIR/requirements.txt" ]] || [[ -f "$TARGET_DIR/setup.py" ]]; then
        echo "python"
    elif [[ -f "$TARGET_DIR/package.json" ]] || [[ -f "$TARGET_DIR/tsconfig.json" ]]; then
        echo "typescript"
    elif [[ -f "$TARGET_DIR/build.gradle.kts" ]] && grep -q "kotlin" "$TARGET_DIR/build.gradle.kts" 2>/dev/null; then
        echo "kotlin"
    elif [[ -f "$TARGET_DIR/build.gradle.kts" ]] || [[ -f "$TARGET_DIR/build.gradle" ]] || [[ -f "$TARGET_DIR/pom.xml" ]]; then
        echo "java"
    elif [[ -f "$TARGET_DIR/go.mod" ]]; then
        echo "go"
    elif [[ -f "$TARGET_DIR/Package.swift" ]]; then
        echo "swift"
    elif [[ -f "$TARGET_DIR/Cargo.toml" ]]; then
        echo "rust"
    elif find "$TARGET_DIR" -maxdepth 3 \( -name '*.csproj' -o -name '*.sln' \) -print -quit 2>/dev/null | grep -q .; then
        # .csproj/.sln commonly live in subdirs (src/App/App.csproj), so search a
        # few levels, not just the top of the project.
        echo "csharp"
    elif [[ -f "$TARGET_DIR/Gemfile" ]]; then
        echo "ruby"
    elif [[ -f "$TARGET_DIR/composer.json" ]]; then
        echo "php"
    else
        echo "generic"
    fi
}

if [[ -z "$LANGUAGE" ]]; then
    LANGUAGE=$(detect_language)
    print_step "Auto-detected language: ${LANGUAGE}"
fi

print_banner
print_step "Installing ClaudeKit v${VERSION}"
print_step "Target: $TARGET_DIR"
print_step "Mode: $MODE"
print_step "Language: $LANGUAGE"
echo ""

# Create directory structure
print_step "Creating directory structure..."
mkdir -p "$DEST"/{agents/_shared,commands,skills,hooks,operations/scripts,local,modes}

# Copy agents
AGENT_COUNT=$(ls -1 "$CLAUDE_SRC"/agents/*.md 2>/dev/null | grep -v -E '(QUICK_START|HANDOFF_PROTOCOL)' | wc -l | tr -d ' ')
print_step "Installing agents (${AGENT_COUNT})..."
cp "$CLAUDE_SRC"/agents/*.md "$DEST/agents/"
cp "$CLAUDE_SRC"/agents/_shared/*.md "$DEST/agents/_shared/"
print_ok "Agents installed"

# Copy commands. One tree: `.claude/commands/` is the only source, so no
# installed command is decided by copy order (task 008 batch 1).
print_step "Installing commands..."
cp "$CLAUDE_SRC"/commands/*.md "$DEST/commands/"
CMD_COUNT=$(ls -1 "$DEST/commands/"*.md 2>/dev/null | wc -l | tr -d ' ')
print_ok "$CMD_COUNT commands installed"

# Copy operations scripts
print_step "Installing operations scripts..."
cp "$CLAUDE_SRC"/operations/scripts/*.py "$DEST/operations/scripts/"
cp "$CLAUDE_SRC"/operations/scripts/*.json "$DEST/operations/scripts/"
print_ok "Operations scripts installed"

# Full mode: copy skills and hooks
if [[ "$MODE" == "full" ]]; then
    print_step "Installing skills..."
    # Copy skill directories from .claude/skills/
    for skill_dir in "$CLAUDE_SRC"/skills/*/; do
        if [[ -d "$skill_dir" ]]; then
            skill_name=$(basename "$skill_dir")
            mkdir -p "$DEST/skills/$skill_name"
            cp "$skill_dir"*.md "$DEST/skills/$skill_name/" 2>/dev/null || true
        fi
    done

    # Copy skills registry. It is generated from `.claude/skills/`, which is now
    # the only tree the loop above reads, so what ships and what the registry
    # lists cannot diverge and no post-install reconcile is needed. Before task
    # 008 batch 1, `i18n-workflow` shipped from `templates/skills/` and was absent
    # from the registry, so `ck doctor --strict` exited 1 on a fresh install.
    if [[ -f "$CLAUDE_SRC/skills/skills-registry.json" ]]; then
        cp "$CLAUDE_SRC/skills/skills-registry.json" "$DEST/skills/"
    fi
    SKILL_COUNT=$(find "$DEST/skills" -name "SKILL.md" 2>/dev/null | wc -l | tr -d ' ')
    print_ok "$SKILL_COUNT skills installed"

    # Profiles. Full mode only: they DECLARE the hook set, and hooks are a
    # full-mode component. The manifest walks the destination tree, so these
    # are receipted (and therefore uninstallable and `ck diff`-visible) with
    # no manifest change.
    print_step "Installing profiles..."
    # Created HERE, not in the unconditional mkdir above: profiles declare the
    # hook set, hooks are full-mode only, and an empty profiles/ in a --minimal
    # install is a `ck doctor` failure rather than a designed absence.
    mkdir -p "$DEST/profiles"
    for profile_dir in "$CLAUDE_SRC"/profiles/*/; do
        if [[ -d "$profile_dir" ]]; then
            profile_name=$(basename "$profile_dir")
            mkdir -p "$DEST/profiles/$profile_name"
            cp "$profile_dir"profile.json "$DEST/profiles/$profile_name/"
        fi
    done
    if [[ -f "$CLAUDE_SRC/profiles/README.md" ]]; then
        cp "$CLAUDE_SRC/profiles/README.md" "$DEST/profiles/"
    fi
    PROFILE_COUNT=$(find "$DEST/profiles" -name "profile.json" 2>/dev/null | wc -l | tr -d ' ')
    print_ok "$PROFILE_COUNT profiles installed"

    # Copy the issue-ledger entry-format contract. The ledger directory and its
    # entries self-materialize on the first `record`, but the README is the
    # documented entry format, so a full install must ship it.
    if [[ -f "$CLAUDE_SRC/knowledge/issues/README.md" ]]; then
        mkdir -p "$DEST/knowledge/issues"
        cp "$CLAUDE_SRC/knowledge/issues/README.md" "$DEST/knowledge/issues/"
        print_ok "Issue-ledger entry contract installed"
    fi

    print_step "Installing hooks..."
    # Structural copy, NOT an extension allowlist. The old *.sh/*.json/*.md
    # allowlist silently went stale when Python hooks were added: settings.json
    # wired reflection-gate.py, the installer never shipped it, and
    # `python3 <missing>` exits 2 -- which on PreToolUse means BLOCK. A fresh
    # install produced a project where every Edit, Write and Bash was blocked.
    # Ship everything; deny only runtime state and editor/merge debris.
    _copy_hook_assets() {
        _src_dir="$1"
        [[ -d "$_src_dir" ]] || return 0
        for _hook_src in "$_src_dir"/*; do
            [[ -f "$_hook_src" ]] || continue
            case "${_hook_src##*/}" in
                *.log|*.pyc|*.orig|*.rej|*.swp|*~) continue ;;
                compact-counter.txt|settings.local.json) continue ;;
            esac
            cp "$_hook_src" "$DEST/hooks/"
        done
    }
    _copy_hook_assets "$CLAUDE_SRC/hooks"
    # Executability follows the file's own shebang, not its extension, so a hook
    # written in any language is handled without another list to keep in sync.
    HOOK_COUNT=0
    for _hook_f in "$DEST"/hooks/*; do
        [[ -f "$_hook_f" ]] || continue
        _hook_line=""
        IFS= read -r _hook_line < "$_hook_f" || true
        case "$_hook_line" in
            "#!"*) chmod +x "$_hook_f"; HOOK_COUNT=$((HOOK_COUNT + 1)) ;;
        esac
    done
    # Counts executables, which legitimately differs from the "wired hooks"
    # count in the docs: shared libraries (reflection.py, lib.sh) and template
    # hooks are installed and executable but are not themselves wired.
    print_ok "$HOOK_COUNT hook scripts installed (executables, including shared libraries)"

    # Install settings.json — WITHOUT it, none of the hooks above ever fire.
    # (For years this was omitted, so every install shipped dead hooks.)
    if [[ -f "$CLAUDE_SRC/settings.json" ]]; then
        cp "$CLAUDE_SRC/settings.json" "$DEST/settings.json"
        print_ok "settings.json installed (hooks wired)"
        # Fail closed on a hook we can PROVE is wired-but-missing: settings.json
        # references hooks BY PATH, and a missing one makes Claude Code run
        # `python3 <missing>` -> exit 2 -> every tool call blocked.
        #
        # Deliberately conservative in the other direction: a token we cannot
        # prove is a script is IGNORED, never required. Requiring an unprovable
        # name would block every install, which is strictly worse than the
        # delivery bug this guards. Runtime state that hook commands legitimately
        # write to (e.g. hooks.log) is subtracted for the same reason.
        MISSING_HOOKS=$(python3 - "$DEST" <<'WIRED_PY'
import os
import re
import sys

dest = sys.argv[1]
path = os.path.join(dest, "settings.json")
if not os.path.exists(path):
    raise SystemExit(0)
with open(path, encoding="utf-8") as fh:
    text = fh.read()

DENY_NAMES = {"compact-counter.txt", "settings.local.json"}
DENY_SUFFIXES = (".log", ".pyc", ".orig", ".rej", ".swp", "~")
SCRIPT_SUFFIXES = (".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".ts", ".rb", ".pl")
INTERP = re.compile(
    r"(?:^|[\s\"'`;|&(])(?:python3|python|bash|sh|zsh|node|ruby|perl)\s+"
    r"(?:-[A-Za-z-]+\s+)*[\\\"'$]*[^\s\"'`;|&()]*$"
)

required = set()
for m in re.finditer(r"\.claude/hooks/([A-Za-z0-9._-]+)", text):
    name = m.group(1)
    if name in DENY_NAMES or name.endswith(DENY_SUFFIXES):
        continue
    if name.endswith(SCRIPT_SUFFIXES) or INTERP.search(text[max(0, m.start() - 80):m.start()]):
        required.add(name)

missing = sorted(n for n in required if not os.path.isfile(os.path.join(dest, "hooks", n)))
print("\n".join(missing))
WIRED_PY
)
        if [[ -n "$MISSING_HOOKS" ]]; then
            print_err "settings.json wires hooks that were not installed:"
            while IFS= read -r _missing_hook; do
                [[ -n "$_missing_hook" ]] || continue
                echo "        - $_missing_hook"
            done <<< "$MISSING_HOOKS"
            print_err "A wired-but-missing hook blocks every tool call (exit 2)."
            print_err "Refusing to leave a broken installation behind."
            # Bash does NOT run the ERR trap for the `exit` builtin, so the
            # staging dir must be cleaned up explicitly or it litters the project.
            _cleanup_on_failure
            exit 1
        fi
        print_ok "All wired hooks resolve to installed files"
    else
        print_warn "settings.json not found in source — hooks will not fire"
    fi
fi

# Copy modes. Promoted out of templates/ in task 008 batch 1, so `.claude/modes/`
# is the only source.
print_step "Installing behavioral modes..."
if [[ -d "$CLAUDE_SRC/modes" ]]; then
    cp "$CLAUDE_SRC"/modes/*.md "$DEST/modes/" 2>/dev/null || true
    MODE_COUNT=$(ls -1 "$DEST/modes/"*.md 2>/dev/null | wc -l | tr -d ' ')
    print_ok "$MODE_COUNT modes installed"
else
    print_warn "Modes directory not found, skipping"
fi

# Copy .agentignore template
if [[ -f "$SCRIPT_DIR/templates/.agentignore" ]]; then
    print_step "Installing .agentignore template..."
    cp "$SCRIPT_DIR/templates/.agentignore" "$TARGET_DIR/.agentignore"
    print_ok ".agentignore installed"
elif [[ -f "$SCRIPT_DIR/.agentignore" ]]; then
    cp "$SCRIPT_DIR/.agentignore" "$TARGET_DIR/.agentignore"
    print_ok ".agentignore installed"
fi

# Optionally copy MCP configurations
if [[ "$WITH_MCP" == true ]]; then
    print_step "Installing MCP server configurations..."
    if [[ -d "$SCRIPT_DIR/templates/mcp" ]]; then
        mkdir -p "$DEST/mcp"
        cp -r "$SCRIPT_DIR"/templates/mcp/* "$DEST/mcp/" 2>/dev/null || true
        print_ok "MCP configurations installed"
    elif [[ -d "$CLAUDE_SRC/mcp" ]]; then
        mkdir -p "$DEST/mcp"
        cp -r "$CLAUDE_SRC"/mcp/* "$DEST/mcp/" 2>/dev/null || true
        print_ok "MCP configurations installed"
    else
        print_warn "MCP directory not found, skipping"
    fi
fi

# Optionally copy i18n files
if [[ "$WITH_I18N" == true ]]; then
    print_step "Installing i18n files..."
    if [[ -d "$SCRIPT_DIR/i18n" ]]; then
        mkdir -p "$TARGET_DIR/i18n"
        cp -r "$SCRIPT_DIR"/i18n/* "$TARGET_DIR/i18n/" 2>/dev/null || true
        print_ok "i18n files installed"
    else
        print_warn "i18n directory not found, skipping"
    fi
fi

# Apply language template
print_step "Applying ${LANGUAGE} template..."
TEMPLATE_DIR="$SCRIPT_DIR/templates/$LANGUAGE"
if [[ ! -d "$TEMPLATE_DIR" ]]; then
    TEMPLATE_DIR="$SCRIPT_DIR/templates/generic"
fi

# Read template values (parse key=value safely, no arbitrary code execution)
if [[ -f "$TEMPLATE_DIR/config.env" ]]; then
    while IFS='=' read -r key value; do
        # Skip comments and empty lines
        [[ -z "$key" || "$key" =~ ^[[:space:]]*# ]] && continue
        # Trim whitespace
        key=$(echo "$key" | xargs)
        value=$(echo "$value" | sed 's/^["'\'']*//;s/["'\'']*$//')
        # Only allow known safe variable names
        case "$key" in
            BUILD_CMD|TEST_CMD|LINT_CMD|COVERAGE_CMD|FRAMEWORK|BUILD_SYSTEM|TEST_FRAMEWORK|EXAMPLE_FILE)
                declare "$key=$value"
                ;;
        esac
    done < "$TEMPLATE_DIR/config.env"
fi

# Set defaults from template or fallbacks
# An unconfigured command stays EMPTY. The hooks skip an empty command and say so
# (pre-push.sh:130, post-implement.sh:80); a no-op print command exits 0 instead, so
# the push gate printed "[pre-push] Tests: PASSED" having run no tests at all.
BUILD_CMD="${BUILD_CMD:-}"
TEST_CMD="${TEST_CMD:-}"
LINT_CMD="${LINT_CMD:-}"
COVERAGE_CMD="${COVERAGE_CMD:-}"

# Rendered docs (CLAUDE.project.md, CONSTITUTION.md) are read by humans, never
# executed, so an empty value would render there as an empty backtick pair. Those
# renders - and only those - get a readable placeholder.
CMD_UNSET_DOC="(not configured - set it in .claude/hooks/config.json)"
BUILD_CMD_DOC="${BUILD_CMD:-$CMD_UNSET_DOC}"
TEST_CMD_DOC="${TEST_CMD:-$CMD_UNSET_DOC}"
LINT_CMD_DOC="${LINT_CMD:-$CMD_UNSET_DOC}"
COVERAGE_CMD_DOC="${COVERAGE_CMD:-$CMD_UNSET_DOC}"
PROJECT_NAME="${PROJECT_NAME:-$(basename "$TARGET_DIR")}"

# Render a {{PLACEHOLDER}} template with LITERAL substitution. Using Python's
# str.replace (not sed) so values containing sed-special chars (& | \ / newline)
# — e.g. a BUILD_CMD like `npm run build && npm test` — can't corrupt the output
# or inject sed commands. Substitutions are passed as CK_VAR_<NAME> env vars.
render_template() {
    local tpl="$1" out="$2"
    CK_TPL_IN="$tpl" CK_TPL_OUT="$out" python3 -c '
import os
with open(os.environ["CK_TPL_IN"]) as f:
    text = f.read()
for key, val in os.environ.items():
    if key.startswith("CK_VAR_"):
        text = text.replace("{{%s}}" % key[len("CK_VAR_"):], val)
with open(os.environ["CK_TPL_OUT"], "w") as f:
    f.write(text)
'
}

# Generate CLAUDE.md from template
print_step "Generating CLAUDE.md..."
if [[ -f "$TEMPLATE_DIR/CLAUDE.md" ]]; then
    CK_VAR_PROJECT_NAME="$PROJECT_NAME" \
    CK_VAR_LANGUAGE="$LANGUAGE" \
        render_template "$TEMPLATE_DIR/CLAUDE.md" "$DEST/local/CLAUDE.project.md"
else
    CK_VAR_PROJECT_NAME="$PROJECT_NAME" \
    CK_VAR_PROJECT_DESCRIPTION="A $LANGUAGE project using ClaudeKit" \
    CK_VAR_LANGUAGE="$LANGUAGE" \
    CK_VAR_FRAMEWORK="${FRAMEWORK:-N/A}" \
    CK_VAR_BUILD_SYSTEM="${BUILD_SYSTEM:-N/A}" \
    CK_VAR_TEST_FRAMEWORK="${TEST_FRAMEWORK:-N/A}" \
    CK_VAR_BUILD_CMD="$BUILD_CMD_DOC" \
    CK_VAR_TEST_CMD="$TEST_CMD_DOC" \
    CK_VAR_LINT_CMD="$LINT_CMD_DOC" \
    CK_VAR_COVERAGE_CMD="$COVERAGE_CMD_DOC" \
    CK_VAR_EXAMPLE_FILE_PATH="${EXAMPLE_FILE:-src/main.py}" \
        render_template "$CLAUDE_SRC/local/CLAUDE.template.md" "$DEST/local/CLAUDE.project.md"
fi
print_ok "CLAUDE.md generated"

# Generate CONSTITUTION.md from template
print_step "Generating CONSTITUTION.md..."
CK_VAR_PROJECT_NAME="$PROJECT_NAME" \
CK_VAR_DATE="$(date +%Y-%m-%d)" \
CK_VAR_LANGUAGE="$LANGUAGE" \
CK_VAR_LINT_CMD="$LINT_CMD_DOC" \
CK_VAR_TEST_CMD="$TEST_CMD_DOC" \
CK_VAR_COVERAGE_CMD="$COVERAGE_CMD_DOC" \
CK_VAR_BUILD_TIME_TARGET="< 60 seconds" \
    render_template "$CLAUDE_SRC/local/CONSTITUTION.template.md" "$DEST/local/CONSTITUTION.md"
print_ok "CONSTITUTION.md generated"

# Update hooks config with project commands
if [[ "$MODE" == "full" ]] && [[ -f "$DEST/hooks/config.json" ]]; then
    print_step "Configuring hooks for ${LANGUAGE}..."
    CK_CONFIG_PATH="$DEST/hooks/config.json" \
    CK_BUILD_CMD="$BUILD_CMD" \
    CK_TEST_CMD="$TEST_CMD" \
    CK_LINT_CMD="$LINT_CMD" \
    CK_COVERAGE_CMD="$COVERAGE_CMD" \
    python3 -c "
import json, os
config_path = os.environ['CK_CONFIG_PATH']
with open(config_path, 'r') as f:
    config = json.load(f)
config.setdefault('project', {})
config['project']['build_cmd'] = os.environ['CK_BUILD_CMD']
config['project']['test_cmd'] = os.environ['CK_TEST_CMD']
config['project']['lint_cmd'] = os.environ['CK_LINT_CMD']
config['project']['coverage_cmd'] = os.environ['CK_COVERAGE_CMD']
with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
" 2>/dev/null && print_ok "Hooks configured" || CK_CONFIG_REWRITE_FAILED=1

    # The shipped config.json carries CLAUDEKIT'S OWN project commands. Warning and
    # moving on would leave `python3 -m pytest tests/ -q` and `ruff check src/ tests/
    # scripts/` in the user's project, to be executed by their next commit or push.
    # Blank them instead; if even that write fails, refuse to install rather than hand
    # over a config that runs this repo's gates inside someone else's tree.
    if [[ "${CK_CONFIG_REWRITE_FAILED:-0}" == "1" ]]; then
        CK_CONFIG_PATH="$DEST/hooks/config.json" \
        CK_SOURCE_CONFIG="$CLAUDE_SRC/hooks/config.json" \
        python3 -c "
import json, os
# Read the PRISTINE source, never the destination: the write that just failed
# opened it with 'w', which truncates before json.dump, so the file may now be
# invalid JSON and re-reading it would turn a recoverable install into an abort.
with open(os.environ['CK_SOURCE_CONFIG']) as f:
    config = json.load(f)
config['project'] = {k: '' for k in ('build_cmd', 'test_cmd', 'lint_cmd', 'coverage_cmd')}
with open(os.environ['CK_CONFIG_PATH'], 'w') as f:
    json.dump(config, f, indent=2)
" 2>/dev/null \
            && print_warn "Could not auto-configure hooks; project commands left EMPTY (set them in .claude/hooks/config.json)" \
            || {
                print_err "Could not write $DEST/hooks/config.json; refusing to ship a config containing ClaudeKit's own build commands."
                # Bash does NOT run the ERR trap for the `exit` builtin, so the
                # staging dir must be cleaned up explicitly or it litters the project.
                _cleanup_on_failure
                exit 1
            }
    fi
fi

# Preserve the user's local override across a reinstall. settings.local.json is
# never shipped and is the intended customization surface (Claude Code merges it
# over settings.json), so carry it into the new install instead of leaving it
# behind in the backup.
if [[ -f "$FINAL_DEST/settings.local.json" ]]; then
    cp "$FINAL_DEST/settings.local.json" "$STAGING/settings.local.json" 2>/dev/null \
        && print_ok "Preserved settings.local.json"
fi

# Preserve the project's OWN content across a reinstall.
#
# local/CLAUDE.project.md and local/CONSTITUTION.md are SEEDED from templates on a fresh
# install and belong to the project thereafter -- this script's own closing message says
# "Review ... and customize". Re-rendering them on every `ck update` overwrote real
# content with the generic template: measured on the 2026-08-28 fleet update, one project
# had its architecture layers replaced by "# TODO: Define your architecture layers here"
# and its description replaced by the stock language template. Seeded-then-owned, so the
# existing file wins whenever there is one.
for _rel in local/CLAUDE.project.md local/CONSTITUTION.md; do
    if [[ -f "$FINAL_DEST/$_rel" ]]; then
        cp "$FINAL_DEST/$_rel" "$STAGING/$_rel" 2>/dev/null \
            && print_ok "Preserved $_rel"
    fi
done

# hooks/config.json is PARTIALLY kit-owned (adapt.py PARTIAL_OWNED_RELS, cli/main.py
# PARTIAL_OWNED -- `ck uninstall` already honours this; the installer did not). The kit
# owns the shipped structure and auto-configures `project` above, but `security` is the
# project's own command allowlist and cannot be regenerated. A whole-file overwrite
# silently dropped it from 4 of 13 projects in the same run (32, 15, 5 and 1
# allowedCommands). Carry ONLY that key across, so the kit's updates to the rest still land.
if [[ -f "$FINAL_DEST/hooks/config.json" ]] && [[ -f "$STAGING/hooks/config.json" ]]; then
    if CK_OLD_CONFIG="$FINAL_DEST/hooks/config.json" \
       CK_NEW_CONFIG="$STAGING/hooks/config.json" \
       python3 - <<'PRESERVE_SECURITY_PY'
import json, os, sys

with open(os.environ["CK_OLD_CONFIG"]) as fh:
    old = json.load(fh)
security = old.get("security")
# Nothing to carry (fresh-shaped or hand-removed) is the normal case, not a failure:
# exit 3 so the caller stays silent instead of claiming a preservation that did not happen.
if not isinstance(security, dict):
    sys.exit(3)
path = os.environ["CK_NEW_CONFIG"]
with open(path) as fh:
    new = json.load(fh)
new["security"] = security
with open(path, "w") as fh:
    json.dump(new, fh, indent=2)
    fh.write("\n")
PRESERVE_SECURITY_PY
    then
        print_ok "Preserved hooks/config.json security block"
    elif [[ $? -ne 3 ]]; then
        print_warn "Could not preserve the security block in hooks/config.json (see the backup)"
    fi
fi

# ---- Atomic swap: back up any existing .claude, move staging into place ----
if [[ -d "$FINAL_DEST" ]]; then
    BACKUP="$TARGET_DIR/.claude.bak-$(date +%Y%m%d-%H%M%S)"
    mv "$FINAL_DEST" "$BACKUP"
fi
mv "$STAGING" "$FINAL_DEST"
DEST="$FINAL_DEST"
trap - ERR   # past the destructive phase; nothing left to clean up

# ---- Install manifest (the receipt: what the kit owns, and which commit it came from) ----
# The manifest is an ownership RECEIPT, not an inventory. `ck uninstall` removes
# only files whose sha256 still matches, so anything recorded here is something
# the kit claims the right to delete later. Two consequences:
#   1. Files that are the USER's by definition must never be recorded (below).
#   2. The source commit is recorded so an install is traceable to an immutable
#      40-char SHA rather than to a mutable branch name.
CLAUDEKIT_SOURCE_COMMIT="$(git -C "$SCRIPT_DIR" rev-parse HEAD 2>/dev/null || echo "")"
# `|| true` on BOTH lines, and note the second is a PIPELINE: under `set -o
# pipefail` a failing `git` upstream of `head` fails the whole pipeline, which
# under `set -e` aborts the install. Installing from a non-git source (a tarball,
# or the temp kit copy the delivery tests build) is a supported case, not an error.
CLAUDEKIT_SOURCE_DIRTY="$(git -C "$SCRIPT_DIR" status --porcelain 2>/dev/null | head -1 || true)"
CLAUDEKIT_VERSION="$VERSION" \
CK_SRC_COMMIT="$CLAUDEKIT_SOURCE_COMMIT" \
CK_SRC_DIRTY="$CLAUDEKIT_SOURCE_DIRTY" \
python3 - "$FINAL_DEST" "$MODE" "$LANGUAGE" <<'MANIFEST_PY' && print_ok "Install manifest written" || print_warn "Manifest generation failed"
import hashlib, json, os, sys, datetime

# Local-only by definition: the user's own settings, and runtime output. Recording
# these would make `ck update` overwrite a per-project permission allowlist and
# `ck uninstall` delete a log - which is exactly what happened before, and cost a
# hand-preservation pass across 17 projects during the 2026-07-31 rollout.
# Must stay in step with SKIP_NAMES in the preserve block below.
NEVER_MANAGED = {"hooks.log", "settings.local.json", ".claudekit-manifest.json"}

dest, mode, lang = sys.argv[1], sys.argv[2], sys.argv[3]
files = {}
for root, _, names in os.walk(dest):
    for n in names:
        path = os.path.join(root, n)
        rel = os.path.relpath(path, dest)
        if n in NEVER_MANAGED or n.endswith(".pyc"):
            continue
        try:
            with open(path, "rb") as fh:
                files[rel] = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            pass

# An unpinnable source is recorded as unpinnable. Fabricating a commit - or
# omitting the field so a reader assumes one - would make provenance a guess.
commit = os.environ.get("CK_SRC_COMMIT") or None
source = {"commit": commit, "pinned": bool(commit)}
if commit and os.environ.get("CK_SRC_DIRTY"):
    # A dirty checkout does not correspond to its own commit, so the pin is a
    # nearest-ancestor, not an identity. Say so rather than imply reproducibility.
    source["dirty"] = True
    source["pinned"] = False

manifest = {
    "version": os.environ.get("CLAUDEKIT_VERSION", "unknown"),
    "installed_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "mode": mode,
    "language": lang,
    "source": source,
    "files": files,
}
with open(os.path.join(dest, ".claudekit-manifest.json"), "w") as fh:
    json.dump(manifest, fh, indent=2)
MANIFEST_PY

# ---- Preserve project-custom assets from the previous install ----
# Files in the backup that (a) don't exist in the new tree and (b) weren't
# kit-managed (per the old manifest; for pre-manifest backups, heuristic:
# anything under agents/ commands/ skills/) are copied back. They are NOT
# added to the manifest — `ck diff` reports them as custom. The backup keeps
# everything regardless, so this is fully reversible.
if [[ -n "${BACKUP:-}" && -d "${BACKUP:-}" ]]; then
    python3 - "$BACKUP" "$FINAL_DEST" <<'PRESERVE_PY' || print_warn "Custom-asset preservation failed (files remain in the backup)"
import json, os, shutil, sys
backup, dest = sys.argv[1], sys.argv[2]
old_manifest = None
mpath = os.path.join(backup, ".claudekit-manifest.json")
if os.path.exists(mpath):
    try:
        with open(mpath) as fh:
            old_manifest = set(json.load(fh).get("files", {}))
    except (ValueError, OSError):
        old_manifest = None
# The legacy fallback, used ONLY when the backup carries no manifest. It was
# ("agents", "commands", "skills"), which silently dropped a project's custom
# hooks/ and operations/ on every pre-manifest update -- measured: rest-framework
# lost hooks/format-compile.sh and hooks/quick-verify.sh that way. Widened to the
# directories that hold AUTHORED content.
#
# `reports/` is deliberately NOT here: this repo treats reports as generated, not
# source ("re-derive, don't cite" -- CLAUDE.md), and the installer itself writes
# `.claude/reports/` into .gitignore below. Resurrecting a scratch report a user had
# cleaned up, and relabelling it "custom" in `ck diff`, is not preservation.
ASSET_DIRS = ("agents", "commands", "skills", "hooks", "operations", "modes",
              "local", "plans", "knowledge", "defects")
# Must stay in step with NEVER_MANAGED in the manifest block above.
SKIP_NAMES = {"hooks.log", "settings.local.json", ".claudekit-manifest.json"}
restored = []
failed = []


# realpath, not abspath: `_within` normalises both sides itself, but leaving an
# unresolved root here is a footgun for the next direct user of it (macOS
# /var -> /private/var is what made every legitimate link read as an escape).
project_root = os.path.dirname(os.path.realpath(dest))
refused = []


def _within(child, parent):
    """Both sides through realpath, which is the whole trick.

    On macOS a temp dir is /var/folders/... -- itself a symlink to /private/var/...
    Resolving only the child made every legitimate link look like an escape, and the
    refusal policy silently ate three passing tests before this was normalised.
    """
    child = os.path.realpath(child)
    parent = os.path.realpath(parent)
    return child == parent or child.startswith(os.path.join(parent, ""))


def link_refusal(path, target):
    """Why this symlink must NOT be recreated, or None to carry it over.

    The preserve loop was the one place in this repo that would rebuild an arbitrary
    symlink target verbatim. `security/path_guard.py` rejects targets that escape the
    project root and `review-record.py:_safe_write` refuses to write THROUGH a link at
    any level; recreating whatever a backup happens to contain is the same class of
    trust, so it gets the same answer. A refusal is reported, never silent -- the file
    stays in the backup and the operator is told which and why.
    """
    dest_of_link = os.path.join(os.path.dirname(path), os.readlink(path))
    resolved = os.path.realpath(dest_of_link)
    if not _within(resolved, project_root):
        return "target escapes the project"
    # A DIRECTORY link whose target contains the link's own location is a cycle:
    # `plans/x/shadow/.claude -> <project>/.claude` resolves back to the tree it lives
    # in. This script never descends it (followlinks=False, and it is pulled out of
    # `dirs`), but baking a self-reference into the installed tree hands the next
    # `find -L`, `du`, or followlinks=True walker an infinite descent.
    if os.path.isdir(dest_of_link) and _within(os.path.realpath(target), resolved):
        return "self-referential directory link (target is an ancestor of it)"
    return None


def carry_over(path, target):
    """Copy one backup entry into the new tree. Symlinks stay symlinks.

    `shutil.copy2` DEREFERENCES: on a link it copies the target's bytes, silently
    turning the project's symlink into a regular file -- and on a DANGLING link it
    raises FileNotFoundError. Recreating the link from `os.readlink` preserves what
    the project actually had and cannot fail on a target that no longer exists.

    No overwrite handling: the caller skips any rel that already lexists in dest, and
    this script is synchronous, so `target` is always absent here.
    """
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.islink(path):
        os.symlink(os.readlink(path), target)
    else:
        shutil.copy2(path, target)


def preserve(path, rel):
    """Apply the refusal policy, then carry the entry over. Returns True if restored."""
    target = os.path.join(dest, rel)
    if os.path.islink(path):
        why = link_refusal(path, target)
        if why is not None:
            refused.append((rel, why))
            return False
    carry_over(path, target)
    return True


for root, dirs, names in os.walk(backup):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    # A symlink to an EXISTING directory is classified as a directory, so it lands in
    # `dirs` and a loop over `names` alone can never carry it over -- measured: 36 of
    # them under one project's plans/, silently dropped on every update. (A DANGLING
    # dir-symlink is classified as a file and does reach `names`, which is why this
    # only shows up for links whose target still exists.) Handled here and removed
    # from `dirs` so the walk cannot descend through them into the live tree.
    for d in list(dirs):
        link_path = os.path.join(root, d)
        if not os.path.islink(link_path):
            continue
        dirs.remove(d)
        link_rel = os.path.relpath(link_path, backup)
        if os.path.lexists(os.path.join(dest, link_rel)):
            continue
        if old_manifest is not None:
            if link_rel in old_manifest:
                continue
        elif link_rel.split(os.sep)[0] not in ASSET_DIRS:
            continue
        try:
            if preserve(link_path, link_rel):
                restored.append(link_rel)
        except Exception as e:
            failed.append((link_rel, e))
    for n in names:
        if n in SKIP_NAMES or n.endswith(".pyc"):
            continue
        path = os.path.join(root, n)
        rel = os.path.relpath(path, backup)
        # lexists, not exists: a DANGLING symlink already in the new tree is present
        # and must be left alone, where `exists` would read it as absent.
        if os.path.lexists(os.path.join(dest, rel)):
            continue
        if old_manifest is not None:
            # Precise: old-kit files (removed/renamed since) are NOT resurrected.
            if rel in old_manifest:
                continue
        elif rel.split(os.sep)[0] not in ASSET_DIRS:
            continue
        # Per-entry, and this is the whole point. One unreadable entry used to abort
        # the LOOP: a single dangling symlink under plans/ cost qa-agents 656 custom
        # files -- its own agents, 281 files under operations/, 118 under reports/ --
        # because everything the walk had not yet reached was abandoned, under one
        # yellow line saying the files "remain in the backup". A permissions error or
        # a race with another process aborts identically; the symlink was only the
        # trigger. Isolating each entry makes the damage proportional to the fault.
        # Broad on purpose: nothing this function can raise may end the loop.
        try:
            if not preserve(path, rel):
                continue
        except Exception as e:
            failed.append((rel, e))
            continue
        restored.append(rel)
for rel in sorted(restored):
    print("    preserved: " + rel)
if restored and old_manifest is None:
    print("    (pre-manifest backup: preserved files may include assets from an")
    print("     older kit version -- run `ck diff` to review the custom list)")
if refused:
    print("    %d symlink(s) NOT recreated (kept in the backup):" % len(refused))
    for rel, why in sorted(refused)[:10]:
        print("      %s -- %s" % (rel, why))
    if len(refused) > 10:
        print("      ... and %d more" % (len(refused) - 10))
if failed:
    # A count and names, not just "something failed". The old message gave no scale,
    # so losing one scratch file and losing 656 read identically.
    print("    WARNING: %d file(s) could NOT be preserved; they remain in the backup:"
          % len(failed))
    for rel, e in sorted(failed, key=lambda p: p[0])[:10]:
        print("      %s (%s)" % (rel, e.__class__.__name__))
    if len(failed) > 10:
        print("      ... and %d more" % (len(failed) - 10))
PRESERVE_PY
fi

# Update .gitignore
print_step "Updating .gitignore..."
GITIGNORE="$TARGET_DIR/.gitignore"
ENTRIES=(
    "# ClaudeKit"
    ".claude/reports/"
    ".claude/hooks/hooks.log"
    ".claude/profiles/local.json"
    ".claude/locks/"
    ".claude-core.lock"
    "backups/"
    "operations/**/state.json"
)

if [[ -f "$GITIGNORE" ]]; then
    for entry in "${ENTRIES[@]}"; do
        if ! grep -qF "$entry" "$GITIGNORE" 2>/dev/null; then
            echo "$entry" >> "$GITIGNORE"
        fi
    done
else
    printf '%s\n' "${ENTRIES[@]}" > "$GITIGNORE"
fi
print_ok ".gitignore updated"

# Disable cleanup trap on success
trap - ERR

# Summary
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ClaudeKit installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Location: $DEST"
echo "  Mode:     $MODE"
echo "  Language: $LANGUAGE"
[[ -n "$BACKUP" ]] && echo "  Backup:   previous .claude saved to $BACKUP"
echo ""
echo "  Installed (counts computed from the installed tree):"
echo "    - ${AGENT_COUNT} agents"
echo "    - ${CMD_COUNT} commands"
echo "    - ${MODE_COUNT:-0} behavioral modes"
if [[ "$MODE" == "full" ]]; then
    echo "    - ${SKILL_COUNT} skills"
    echo "    - ${HOOK_COUNT} hooks"
    [[ -f "$DEST/settings.json" ]] && echo "    - settings.json (hooks wired)"
fi
echo "    - Operations scripts (validate, execute, restore)"
if [[ "$WITH_MCP" == true ]]; then
    echo "    - 5 MCP server configurations"
fi
if [[ "$WITH_I18N" == true ]]; then
    echo "    - i18n files (6 languages)"
fi
echo ""
echo "  Next steps:"
echo "    1. Review .claude/local/CLAUDE.project.md and customize"
echo "    2. Review .claude/local/CONSTITUTION.md and customize"
if [[ "$MODE" == "full" ]]; then
    echo "    3. Review .claude/hooks/config.json and update commands"
fi

# Say it out loud rather than let the user discover it from a red gate. Empty is the
# honest state for a project whose commands could not be detected, and a project whose
# gates run nothing SHOULD be told so. The blanked-on-failure path (above) leaves the
# shell variables populated while the on-disk config is empty, so it is checked too.
if [[ "$MODE" == "full" ]] && { [[ -z "$BUILD_CMD$TEST_CMD$LINT_CMD" ]] || \
        [[ "${CK_CONFIG_REWRITE_FAILED:-0}" == "1" ]]; }; then
    echo ""
    echo "  NOTE: .claude/hooks/config.json has no build/test/lint command configured,"
    echo "  so the pre-commit and pre-push hooks will SKIP those steps and say so -"
    echo "  they will never report a pass for a step they did not run - and"
    echo "  'ck doctor --strict' will exit 1 until you fill them in. That is deliberate."
fi
echo ""
echo "  Start using ClaudeKit in Claude Code:"
echo "    /plan Add a new feature"
echo "    /debug Fix the login bug"
echo "    /coordinator Complex multi-step task"
echo ""
