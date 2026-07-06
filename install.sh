#!/usr/bin/env bash
# -E (errtrace): the ERR trap is inherited by shell functions, so a failure
# inside a helper like render_template still triggers staging cleanup.
set -Eeuo pipefail

# ClaudeKit Installer
# Usage: ./install.sh [TARGET_DIR] [--full|--minimal] [--language LANG] [--with-mcp] [--with-i18n]

VERSION="2.1.0"
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

# Copy commands (core + templates)
print_step "Installing commands..."
cp "$CLAUDE_SRC"/commands/*.md "$DEST/commands/"
if [[ -d "$SCRIPT_DIR/templates/commands" ]]; then
    cp "$SCRIPT_DIR"/templates/commands/*.md "$DEST/commands/" 2>/dev/null || true
fi
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
    # Copy skill directories from templates/skills/
    if [[ -d "$SCRIPT_DIR/templates/skills" ]]; then
        for skill_dir in "$SCRIPT_DIR"/templates/skills/*/; do
            if [[ -d "$skill_dir" ]]; then
                skill_name=$(basename "$skill_dir")
                mkdir -p "$DEST/skills/$skill_name"
                cp "$skill_dir"*.md "$DEST/skills/$skill_name/" 2>/dev/null || true
            fi
        done
    fi
    # Copy skills registry
    if [[ -f "$CLAUDE_SRC/skills/skills-registry.json" ]]; then
        cp "$CLAUDE_SRC/skills/skills-registry.json" "$DEST/skills/"
    fi
    SKILL_COUNT=$(find "$DEST/skills" -name "SKILL.md" 2>/dev/null | wc -l | tr -d ' ')
    print_ok "$SKILL_COUNT skills installed"

    print_step "Installing hooks..."
    cp "$CLAUDE_SRC"/hooks/*.sh "$DEST/hooks/" 2>/dev/null || true
    cp "$CLAUDE_SRC"/hooks/*.json "$DEST/hooks/" 2>/dev/null || true
    cp "$CLAUDE_SRC"/hooks/*.md "$DEST/hooks/" 2>/dev/null || true
    # Copy template hooks
    if [[ -d "$SCRIPT_DIR/templates/hooks" ]]; then
        cp "$SCRIPT_DIR"/templates/hooks/*.sh "$DEST/hooks/" 2>/dev/null || true
    fi
    chmod +x "$DEST"/hooks/*.sh 2>/dev/null || true
    HOOK_COUNT=$(ls -1 "$DEST/hooks/"*.sh 2>/dev/null | wc -l | tr -d ' ')
    print_ok "$HOOK_COUNT hooks installed"

    # Install settings.json — WITHOUT it, none of the hooks above ever fire.
    # (For years this was omitted, so every install shipped dead hooks.)
    if [[ -f "$CLAUDE_SRC/settings.json" ]]; then
        cp "$CLAUDE_SRC/settings.json" "$DEST/settings.json"
        print_ok "settings.json installed (hooks wired)"
    else
        print_warn "settings.json not found in source — hooks will not fire"
    fi
fi

# Copy modes from templates
print_step "Installing behavioral modes..."
if [[ -d "$SCRIPT_DIR/templates/modes" ]]; then
    cp "$SCRIPT_DIR"/templates/modes/*.md "$DEST/modes/" 2>/dev/null || true
    MODE_COUNT=$(ls -1 "$DEST/modes/"*.md 2>/dev/null | wc -l | tr -d ' ')
    print_ok "$MODE_COUNT modes installed"
elif [[ -d "$CLAUDE_SRC/modes" ]]; then
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
BUILD_CMD="${BUILD_CMD:-echo 'No build command configured'}"
TEST_CMD="${TEST_CMD:-echo 'No test command configured'}"
LINT_CMD="${LINT_CMD:-echo 'No lint command configured'}"
COVERAGE_CMD="${COVERAGE_CMD:-echo 'No coverage command configured'}"
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
    CK_VAR_BUILD_CMD="$BUILD_CMD" \
    CK_VAR_TEST_CMD="$TEST_CMD" \
    CK_VAR_LINT_CMD="$LINT_CMD" \
    CK_VAR_COVERAGE_CMD="$COVERAGE_CMD" \
    CK_VAR_EXAMPLE_FILE_PATH="${EXAMPLE_FILE:-src/main.py}" \
        render_template "$CLAUDE_SRC/local/CLAUDE.template.md" "$DEST/local/CLAUDE.project.md"
fi
print_ok "CLAUDE.md generated"

# Generate CONSTITUTION.md from template
print_step "Generating CONSTITUTION.md..."
CK_VAR_PROJECT_NAME="$PROJECT_NAME" \
CK_VAR_DATE="$(date +%Y-%m-%d)" \
CK_VAR_LANGUAGE="$LANGUAGE" \
CK_VAR_LINT_CMD="$LINT_CMD" \
CK_VAR_TEST_CMD="$TEST_CMD" \
CK_VAR_COVERAGE_CMD="$COVERAGE_CMD" \
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
" 2>/dev/null && print_ok "Hooks configured" || print_warn "Could not auto-configure hooks (update .claude/hooks/config.json manually)"
fi

# Preserve the user's local override across a reinstall. settings.local.json is
# never shipped and is the intended customization surface (Claude Code merges it
# over settings.json), so carry it into the new install instead of leaving it
# behind in the backup.
if [[ -f "$FINAL_DEST/settings.local.json" ]]; then
    cp "$FINAL_DEST/settings.local.json" "$STAGING/settings.local.json" 2>/dev/null \
        && print_ok "Preserved settings.local.json"
fi

# ---- Atomic swap: back up any existing .claude, move staging into place ----
if [[ -d "$FINAL_DEST" ]]; then
    BACKUP="$TARGET_DIR/.claude.bak-$(date +%Y%m%d-%H%M%S)"
    mv "$FINAL_DEST" "$BACKUP"
fi
mv "$STAGING" "$FINAL_DEST"
DEST="$FINAL_DEST"
trap - ERR   # past the destructive phase; nothing left to clean up

# ---- Install manifest (records version + per-file sha256 for `ck update`) ----
CLAUDEKIT_VERSION="$VERSION" python3 - "$FINAL_DEST" "$MODE" "$LANGUAGE" <<'MANIFEST_PY' && print_ok "Install manifest written" || print_warn "Manifest generation failed"
import hashlib, json, os, sys, datetime
dest, mode, lang = sys.argv[1], sys.argv[2], sys.argv[3]
files = {}
for root, _, names in os.walk(dest):
    for n in names:
        path = os.path.join(root, n)
        rel = os.path.relpath(path, dest)
        if rel == ".claudekit-manifest.json":
            continue
        try:
            with open(path, "rb") as fh:
                files[rel] = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            pass
manifest = {
    "version": os.environ.get("CLAUDEKIT_VERSION", "unknown"),
    "installed_at": datetime.datetime.now().isoformat(timespec="seconds"),
    "mode": mode,
    "language": lang,
    "files": files,
}
with open(os.path.join(dest, ".claudekit-manifest.json"), "w") as fh:
    json.dump(manifest, fh, indent=2)
MANIFEST_PY

# Update .gitignore
print_step "Updating .gitignore..."
GITIGNORE="$TARGET_DIR/.gitignore"
ENTRIES=(
    "# ClaudeKit"
    ".claude/reports/"
    ".claude/hooks/hooks.log"
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
echo ""
echo "  Start using ClaudeKit in Claude Code:"
echo "    /plan Add a new feature"
echo "    /debug Fix the login bug"
echo "    /coordinator Complex multi-step task"
echo ""
