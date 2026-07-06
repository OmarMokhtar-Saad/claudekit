# Task 014 — Supply Chain Hardening

## Problem
A security-branded toolkit ships with an unhardened supply chain (security review §2.1, §6):
1. **GitHub Actions on mutable tags:** `actions/checkout@v4`, `actions/setup-python@v5`, `softprops/action-gh-release@v2`, `actions/upload-artifact@v4` across `.github/workflows/*` — `@v4` is a moving ref; a compromised action release runs in CI with the repo token. No `dependabot.yml` (ironic: the kit ships a `dependency-audit` skill and `/deps` command).
2. **MCP template is RCE-by-design:** `templates/mcp/mcp-settings.json` runs `npx -y @pkg@latest` for all 5 servers — fetches and executes the latest published package with no version pin and no integrity check — and grants `server-filesystem --allow-write .`. Every `--with-mcp` install trusts 5 npm publish streams forever.
3. **No install integrity:** README instructs `git clone && ./install.sh` with no checksum/signature verification, no pinned release tag, no published hashes. A tampered mirror or MITM'd clone yields silent code execution (installer itself is network-free and sudo-free — genuinely good — but the acquisition step is unverified).
4. **No dependency pinning:** `tests/requirements.txt` pulls `jsonschema` unpinned; no lockfile/hashes anywhere.
5. **No release signing:** no Sigstore/GPG, no SLSA provenance, no PyPI attestations (moot until task 001 publishes, then load-bearing).
6. **Repo-slug ambiguity as squat risk:** `omarmokhtar/claudekit` vs `OmarMokhtar-Saad/claudekit` — a user cloning the wrong (possibly unclaimed) slug could fetch attacker-controlled code (security §5.3; canonicalization in task 006 — the *claim/redirect* of the alternate is this task's concern).

## Root Cause
Standard young-project posture: conveniences (`@latest`, tag refs, unpinned deps) adopted before any adversarial review; the release pipeline never ran (zero tags), so signing/attestation questions never came up.

## Files
- `.github/workflows/ci.yml`, `release.yml`, `security.yml` (SHA-pin every `uses:`)
- New: `.github/dependabot.yml` (github-actions + pip ecosystems)
- `templates/mcp/mcp-settings.json` (pin exact versions; drop `-y ...@latest`; scope/document `--allow-write`)
- `templates/mcp/README.md` (risk disclosure)
- `tests/requirements.txt` → pinned with hashes (`pip-compile --generate-hashes`)
- `.github/workflows/release.yml` (SHA256SUMS artifact; Sigstore signing; PyPI Trusted Publishing with attestations — extends task 001)
- `README.md` install section (pin to tag; verification instructions), `SECURITY.md` (disclosures — with task 006)

## Priority
**P1–P2** (security review items 6, 8, 11 — Med severity individually, but cheap and table stakes for a security-branded project; oss-excellence #13).

## Estimated Time
1–2 days.

## Risk
Low. SHA pins add Dependabot-PR noise (that's the point). Pinning MCP servers trades freshness for integrity — correct trade for a security product; Dependabot/renovate-style bumps keep them current deliberately. Version-pinned `npx` still executes remote code at first fetch — document that `--with-mcp` is a trust decision, not make it invisible.

## Step-by-step Implementation
1. **Pin actions by SHA:** replace every `uses: owner/action@vN` with `@<full-sha> # vN.x.y` across the three workflows. Add `dependabot.yml` with `package-ecosystem: github-actions` (weekly) and `pip` for tests/requirements.
2. **Least-privilege workflows:** add explicit `permissions:` blocks (default `contents: read`; `release.yml` gets only what gh-release needs; `id-token: write` only in the publish job for Trusted Publishing).
3. **MCP pinning:** resolve current stable versions of the 5 servers (context7, sequential-thinking, playwright, memory, filesystem); write exact versions (`@x.y.z`), remove `@latest` and `-y` auto-confirm where viable; change filesystem default from `--allow-write .` to read-only with a commented opt-in line; add a "what this grants" paragraph to templates/mcp/README.md and the SECURITY.md disclosure.
4. **Pin test deps with hashes:** `pip-compile --generate-hashes tests/requirements.in` → requirements.txt; CI installs with `--require-hashes`.
5. **Release integrity** (on top of task 001's working release): release.yml emits `SHA256SUMS` for sdist/wheel/tarball; sign with Sigstore (`sigstore-python` or gh attestation); enable PyPI Trusted Publishing + `--attestations`; add SLSA provenance generation (the official generator workflow) when convenient.
6. **Installer verification docs:** README install section pins to the latest tag (`git clone --branch vX.Y.Z`), documents `git verify-tag` (once tags are signed) and the SHA256SUMS check for tarball users.
7. **Slug claim:** register/squat the alternate GitHub name if available and make it redirect (task 006 canonicalizes references; this closes the acquisition-side hole).
8. **CI guard:** a workflow-lint step (e.g., zizmor or a grep) failing on any unpinned `uses:` ref and on `@latest` inside `templates/mcp/`.

## Acceptance Criteria
- `grep -rn "uses:.*@v[0-9]" .github/workflows/` returns nothing (all SHAs).
- `grep -rn "@latest" templates/` returns nothing; MCP config carries exact versions; filesystem server read-only by default.
- Dependabot opens PRs for an intentionally stale action pin (verify once).
- CI installs test deps with `--require-hashes` successfully.
- Next release publishes SHA256SUMS + signatures; PyPI upload carries attestations; README documents verification.
- Both slug variants resolve to the canonical repo (or the alternate is confirmed unregistrable).

## Testing Strategy
- CI workflow-lint gate (step 8) — red on an unpinned ref canary branch.
- `tests/test_mcp.py` extended: parse mcp-settings.json, assert every `args` package spec matches `@\d+\.\d+\.\d+` and filesystem lacks `--allow-write` by default.
- Manual verification walkthrough of a release artifact using only README instructions (the docs must be sufficient for a stranger).

## Rollback Plan
Pins are declarative — reverting any commit restores prior behavior. If a pinned MCP version breaks, bump the pin (never restore `@latest`). If SHA-pinned actions block an urgent fix, updating the SHA is the same one-line change as a tag bump. Signing steps are additive to release.yml; a failing signing step can be temporarily `continue-on-error` with a tracking issue without blocking the release artifacts themselves.
