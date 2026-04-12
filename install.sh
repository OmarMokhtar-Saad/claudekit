#!/usr/bin/env bash
set -euo pipefail

# ClaudeKit Installer
# Usage: ./install.sh [TARGET_DIR] [--full|--minimal] [--language LANG] [--with-mcp] [--with-i18n]

VERSION="2.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_SRC="$SCRIPT_DIR/.claude"

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

usage() {
    echo "Usage: $0 [TARGET_DIR] [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --full          Install all components (default)"
    echo "  --minimal       Install agents, commands, and operations only"
    echo "  --language LANG Pre-configure for language (python|typescript|java|go|kotlin|swift|rust|csharp|ruby|php)"
    echo "  --with-mcp      Install MCP server configurations"
    echo "  --with-i18n     Install internationalization files"
    echo "  --force         Overwrite existing .claude directory"
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
    echo -n "Target project directory: "
    read -r TARGET_DIR
fi

TARGET_DIR="$(cd "$TARGET_DIR" 2>/dev/null && pwd || echo "$TARGET_DIR")"

if [[ ! -d "$TARGET_DIR" ]]; then
    print_err "Directory does not exist: $TARGET_DIR"
    exit 1
fi

DEST="$TARGET_DIR/.claude"

# Cleanup on failure - remove partial installation
_cleanup_on_failure() {
    if [[ -d "$DEST" ]]; then
        print_err "Installation failed. Cleaning up partial installation..."
        rm -rf "$DEST"
    fi
}
trap '_cleanup_on_failure' ERR

# Check for existing installation
if [[ -d "$DEST" ]] && [[ "$FORCE" != true ]]; then
    print_warn "Directory $DEST already exists."
    echo -n "Overwrite? (y/N): "
    read -r confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        echo "Installation cancelled."
        exit 0
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
    elif ls "$TARGET_DIR"/*.csproj 1>/dev/null 2>&1 || ls "$TARGET_DIR"/*.sln 1>/dev/null 2>&1; then
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

# Generate CLAUDE.md from template
print_step "Generating CLAUDE.md..."
if [[ -f "$TEMPLATE_DIR/CLAUDE.md" ]]; then
    sed \
        -e "s|{{PROJECT_NAME}}|${PROJECT_NAME}|g" \
        -e "s|{{LANGUAGE}}|${LANGUAGE}|g" \
        "$TEMPLATE_DIR/CLAUDE.md" > "$DEST/local/CLAUDE.project.md"
else
    sed \
        -e "s|{{PROJECT_NAME}}|$PROJECT_NAME|g" \
        -e "s|{{PROJECT_DESCRIPTION}}|A $LANGUAGE project using ClaudeKit|g" \
        -e "s|{{LANGUAGE}}|$LANGUAGE|g" \
        -e "s|{{FRAMEWORK}}|${FRAMEWORK:-N/A}|g" \
        -e "s|{{BUILD_SYSTEM}}|${BUILD_SYSTEM:-N/A}|g" \
        -e "s|{{TEST_FRAMEWORK}}|${TEST_FRAMEWORK:-N/A}|g" \
        -e "s|{{BUILD_CMD}}|$BUILD_CMD|g" \
        -e "s|{{TEST_CMD}}|$TEST_CMD|g" \
        -e "s|{{LINT_CMD}}|$LINT_CMD|g" \
        -e "s|{{COVERAGE_CMD}}|$COVERAGE_CMD|g" \
        -e "s|{{EXAMPLE_FILE_PATH}}|${EXAMPLE_FILE:-src/main.py}|g" \
        "$CLAUDE_SRC/local/CLAUDE.template.md" > "$DEST/local/CLAUDE.project.md"
fi
print_ok "CLAUDE.md generated"

# Generate CONSTITUTION.md from template
print_step "Generating CONSTITUTION.md..."
sed \
    -e "s|{{PROJECT_NAME}}|$PROJECT_NAME|g" \
    -e "s|{{DATE}}|$(date +%Y-%m-%d)|g" \
    -e "s|{{LANGUAGE}}|$LANGUAGE|g" \
    -e "s|{{LINT_CMD}}|$LINT_CMD|g" \
    -e "s|{{TEST_CMD}}|$TEST_CMD|g" \
    -e "s|{{COVERAGE_CMD}}|$COVERAGE_CMD|g" \
    -e "s|{{BUILD_TIME_TARGET}}|< 60 seconds|g" \
    "$CLAUDE_SRC/local/CONSTITUTION.template.md" > "$DEST/local/CONSTITUTION.md"
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
echo ""
echo "  Installed:"
echo "    - ${AGENT_COUNT} agents (coordinator, planner, reviewer, implementer, verifier, debugger, documenter, gitOps, explore, tester, security-scanner, devops, database-architect, silent-failure-hunter, harness-optimizer, performance-optimizer, code-simplifier, typescript-reviewer, python-reviewer, tdd-guide, refactor-cleaner, doc-updater, code-reviewer, build-error-resolver, loop-operator, opensource-sanitizer, opensource-packager, model-router)"
echo "    - 37 commands (/plan, /review, /implement, /verify, /debug, /docs, /git, /coordinator, /explore, /security, /deps, /rollback, /test, /deploy, /performance, /migrate, /batch, /santa, /hookify, /save-session, /resume-session, /model-route, /prp-plan, /prp-implement, /prp-commit, /prp-pr, /build-fix, /code-review, /gan-build, /opensource, /loop-start, /context-budget, /audit, /eval, /onboard, /blueprint)"
echo "    - 7 behavioral modes (default, brainstorm, token-efficient, deep-research, implementation, review, orchestration)"
if [[ "$MODE" == "full" ]]; then
    echo "    - ${SKILL_COUNT} skills"
    echo "    - 15 hooks (including config-protection, commit-quality, security-reminder, format-typecheck, session-start)"
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
