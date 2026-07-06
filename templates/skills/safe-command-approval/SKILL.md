---
name: safe-command-approval
description: "Use when configuring auto-approval rules for bash commands -- defines allowlists of safe commands, blocklists of dangerous commands, and AST-based analysis for complex pipelines."
---

# Safe Command Approval

## Purpose

Define and enforce a policy for automatically approving safe bash commands and blocking dangerous ones. Reduces friction for routine operations while maintaining security for destructive or sensitive commands.

---

## Command Classification

### Allowlist (Auto-Approve)

These commands are safe to execute without user confirmation:

#### File Reading

```
cat <file>
head <file>
head -n <N> <file>
tail <file>
tail -n <N> <file>
less <file>
wc -l <file>
wc -w <file>
file <path>
stat <path>
```

#### Directory Listing

```
ls
ls -la
ls -lah
ls <directory>
tree
tree <directory>
tree -L <N>
du -sh <path>
du -sh *
```

#### Search

```
grep <pattern> <file>
grep -r <pattern> <directory>
grep -rn <pattern> <directory>
rg <pattern>
find <dir> -name <pattern>
find <dir> -type f -name <pattern>
which <command>
whereis <command>
```

#### Git (Read-Only)

```
git status
git log
git log --oneline
git log --oneline -<N>
git diff
git diff <file>
git diff --cached
git diff <branch1>..<branch2>
git branch
git branch -a
git remote -v
git show <ref>
git blame <file>
git stash list
git tag
git rev-parse HEAD
```

#### Git (Write -- Safe)

```
git add <file>
git add -A
git commit -m "<message>"
git stash
git stash pop
git checkout -b <branch>
git switch <branch>
git switch -c <branch>
git fetch
git pull
```

#### Package Managers (Read-Only)

```
npm list
npm outdated
npm audit
pip list
pip show <package>
pip check
cargo tree
go list ./...
bundle list
composer show
```

#### Build and Test

```
npm test
npm run test
npm run build
npm run lint
npx jest
npx jest <file>
python -m pytest
python -m pytest <file>
python -m pytest -v
pytest
pytest <file>
go test ./...
cargo test
cargo build
cargo clippy
make test
make build
make lint
bundle exec rspec
mvn test
gradle test
```

#### Environment

```
node --version
python --version
python3 --version
go version
rustc --version
java --version
ruby --version
php --version
env | grep <pattern>
echo $<VAR>
pwd
whoami
date
uname -a
```

### Blocklist (Always Block)

These commands MUST NEVER be auto-approved:

#### Destructive File Operations

```
rm -rf /
rm -rf *
rm -rf ~
rm -rf .
rm -rf <path>/*  (when path is / or ~)
shred
mkfs
dd if=<device>
```

#### Permission Escalation

```
sudo <anything>
su
su -
chmod 777
chmod -R 777
chown -R
```

#### Network Dangers

```
curl <url> | bash
curl <url> | sh
wget <url> -O - | bash
wget <url> | sh
curl <url> | sudo bash
```

#### System Modification

```
systemctl stop
systemctl disable
service stop
kill -9
killall
pkill
shutdown
reboot
halt
init 0
init 6
```

#### Data Exfiltration Risk

```
curl -X POST -d @<file> <url>
scp <local-file> <remote>
rsync <local> <remote>
nc -l <port>
```

#### Git Destructive

```
git push --force
git push -f
git reset --hard
git clean -fd
git clean -f
git checkout .
git restore .
```

---

## Analysis Levels

### Level 1: Exact Match

Compare the full command string against the allowlist and blocklist. Fastest check.

### Level 2: Prefix Match

Match the command prefix (first 1-2 words) and validate arguments:
- `rm` is suspicious -> check arguments for `-rf`, recursive flags, and dangerous paths
- `git` is safe for read operations -> check subcommand
- `chmod` is suspicious -> check for `777` or recursive flags

### Level 3: AST-Based Analysis

For complex commands (pipes, subshells, command substitution), parse the command structure:

```bash
# Parse pipe chains -- each segment must be individually safe
cat file.txt | grep "pattern" | wc -l
# -> cat (safe) | grep (safe) | wc (safe) = APPROVE

# Detect command substitution
rm -rf $(cat targets.txt)
# -> rm -rf (dangerous) + command substitution (unpredictable) = BLOCK

# Detect redirects to sensitive locations
echo "data" > /etc/passwd
# -> redirect to /etc/* = BLOCK

# Detect background execution
rm -rf /tmp/data &
# -> destructive + background = BLOCK
```

### Level 4: Context-Aware Analysis

Consider the project context:
- Is the command operating within the project directory? (safer)
- Is the command modifying files outside the project? (dangerous)
- Does the command reference environment variables that could expand to dangerous paths?
- Is the command part of a known build/test/deploy script? (safer)

---

## Decision Flow

```
Command received
    │
    ├── Exact blocklist match? ──YES──► BLOCK (log reason)
    │
    ├── Exact allowlist match? ──YES──► APPROVE
    │
    ├── Prefix match blocklist? ──YES──► BLOCK (log reason)
    │
    ├── Prefix match allowlist?
    │       │
    │      YES──► Validate arguments
    │               │
    │               ├── Args safe? ──YES──► APPROVE
    │               └── Args unsafe? ──► BLOCK
    │
    ├── Complex command (pipes, substitution)?
    │       │
    │      YES──► AST analysis
    │               │
    │               ├── All segments safe? ──YES──► APPROVE
    │               └── Any segment unsafe? ──► BLOCK
    │
    └── Unknown command ──► PROMPT USER
```

---

## Configuration

Store approval rules in `.claude/settings.json`:

```json
{
  "commandApproval": {
    "mode": "allowlist",
    "customAllowlist": [
      "docker compose up",
      "docker compose down",
      "make deploy-staging"
    ],
    "customBlocklist": [
      "npm publish",
      "git push origin main"
    ],
    "allowProjectScripts": true,
    "promptForUnknown": true
  }
}
```

---

## Logging

Every command decision is logged to `.claude/command-audit.log`:

```
[2024-01-15T10:23:45Z] APPROVE  "git status"                    (allowlist-exact)
[2024-01-15T10:23:52Z] APPROVE  "npm test"                      (allowlist-exact)
[2024-01-15T10:24:01Z] BLOCK    "rm -rf node_modules/"          (blocklist-prefix:rm -rf)
[2024-01-15T10:24:15Z] PROMPT   "docker build -t myapp ."       (unknown)
[2024-01-15T10:24:20Z] APPROVE  "docker build -t myapp ."       (user-approved)
```

---

## Integration

- **coordinator** invokes this skill before executing any bash command
- **implementer** uses it during plan execution
- **autonomous-loop** relies on it for unattended command execution
- Works alongside the **operations system** safety guards
