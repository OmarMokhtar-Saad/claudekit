# Awesome Security Skills – Research Report
**Date:** 2026-08-25  
**Source:** https://github.com/securityfortech/awesome-security-skills  
**Overall License:** CC0 1.0 Universal Public Domain Dedication (curated list); individual repos vary

---

## Categories & Complete Skills List

### Offensive Security
- **nemesis-auditor** – Iterative deep-logic security audit agent for Claude Code
- **awesome-claude-skills-security** – Security testing toolkit with SecLists wordlists, injection payloads, LLM security testing (MIT)
- **Ghost Security skills** – AppSec skills collection for AI coding agents (Apache 2.0)
- **Anthropic-Cybersecurity-Skills** – 818 structured skills with MITRE ATT&CK/NIST/ATLAS/D3FEND mapping (Apache 2.0)
- **hacking-skills** – Skills for finding bugs and vulnerabilities across multiple contexts
- **claude-bug-bounty** – Claude Code skills for bug bounty hunting
- **Trail of Bits skills** – Security research, vulnerability detection, audit workflow tools (CC BY-SA 4.0)
- **communitytools** – AI-powered agents with 35+ OWASP Top 10 tools, 100% OWASP Top 10 (2021) coverage (MIT)

### Secure Code Reviews
- **claude-code-security-review** – AI-powered security review GitHub Action using Claude (Anthropic official)
- **VibeSec-Skill** – Secure code writing skill for preventing common vulnerabilities

### Threat Detection & SOC
- **SecurityClaw** – Modular skill-based autonomous SOC agent with threat detection, anomaly triage

---

## Top Value Entries for Gaps Analysis

### For QA/Test-Automation Fleet (Java/Maven, Kotlin/Gradle, Python, Appium, API Testing)

#### 1. **awesome-claude-skills-security** (MIT)
- **Covers:** Fuzzing, passwords, pattern detection, injection payloads (SQL, NoSQL, LDAP), web shells, LLM testing
- **Relevance:** Extensive payload library; AI bias/privacy/memory recall testing; supports Cursor, Claude Code, 60+ agents
- **Gap filled:** Injection payload library not mentioned in your existing corpus

#### 2. **communitytools** (MIT)
- **Covers:** 100% OWASP Top 10 (2021) including `/api-security` skills (REST, GraphQL, WebSocket), `/injection`, `/authentication`, `/server-side` (SSRF, path traversal, file upload)
- **Skills count:** 10 vulnerability categories + OWASP LLM Top 10, SANS Top 25 CWE coverage
- **Gap filled:** Comprehensive API testing (REST/GraphQL/WebSocket vulnerability patterns)

#### 3. **Anthropic-Cybersecurity-Skills** (Apache 2.0)
- **API security:** 28 dedicated skills covering GraphQL, REST, OWASP API Top 10, WAF bypass
- **Mobile security:** 13 skills for Android/iOS analysis, mobile pentesting, MDM forensics
- **Framework maps:** MITRE ATT&CK (805 skills × 290 techniques), NIST CSF 2.0, ATLAS, D3FEND, NIST AI RMF
- **Gap filled:** Mobile app security testing; API security depth; comprehensive framework alignment

### For Skill-Corpus Gaps (vs. existing: security-checklist, differential-security-review, insecure-defaults, supply-chain-audit, prompt-injection-defense, safe-command-approval, opensource-pipeline)

#### 4. **claude-code-security-review** (Anthropic official)
- **Capability:** GitHub Action CI/CD security gating with diff-aware analysis
- **Checks:** Injection attacks, auth flaws, data exposure, crypto weaknesses, input validation, business logic flaws, XSS
- **Output:** PR comments on specific lines, findings count for enforcement policies, false-positive filtering
- **Gap filled:** **CI/CD security gating** (live automated PR analysis); complements your safe-command-approval with contextual diff analysis

#### 5. **Trail of Bits skills** (CC BY-SA 4.0)
- **Supply chain audit:** npm, PyPI, Go packages for version-matched advisories, abandoned upstreams, publisher concentration, install script analysis
- **Code audit:** Specialized skills for C/C++, Rust differential review (memory safety, concurrency, unsafe boundaries)
- **Testing:** Mutation testing, property-based testing (Hypothesis, fast-check, proptest), coverage verification
- **Gap filled:** Supply chain auditing at scale (beyond simple version checks); differential security review for compiled languages; testing infrastructure

#### 6. **Ghost Security skills** (Apache 2.0)
- **Capabilities:** `ghost-repo-context`, `ghost-scan-deps` (dependency vulns), `ghost-scan-secrets`, `ghost-scan-code`, `ghost-report` (consolidated findings), `ghost-validate` (live app testing), `ghost-proxy`
- **Gap filled:** Modular scanning pipeline; consolidated findings aggregation; live application testing (beyond static analysis)

---

## Mobile App Security Testing

**Primary source:** Anthropic-Cybersecurity-Skills (13 dedicated skills)
- Android/iOS analysis and penetration testing
- MDM (Mobile Device Management) forensics
- No Appium-specific skills found in the awesome list (gap for your specific test-automation fleet)

---

## API Security Testing

**Comprehensive coverage across three sources:**

1. **awesome-claude-skills-security** – Injection payloads, API key detection
2. **communitytools** – `/api-security` skill covering REST, GraphQL, WebSocket, Web LLM vulnerabilities
3. **Anthropic-Cybersecurity-Skills** – 28 dedicated API skills including OWASP API Top 10, WAF bypass, OAuth/JWT attacks

**Specific gaps:** No REST client/Postman/Insomnia integration mentioned; no OpenAPI spec validation tools

---

## CI Security Gating

**Best match:** `claude-code-security-review` (Anthropic official GitHub Action)
- Diff-aware analysis on pull requests
- Contextual vulnerability detection (not pattern-matching)
- Severity ratings with line-specific PR comments
- False-positive filtering for practical enforcement
- Integrates directly into GitHub workflows (no manual runner needed)

---

## Recommendations for ClaudeKit Skill-Corpus

### Highest priority gaps:
1. **CI/CD security gating skill** – adopt/wrap `claude-code-security-review` if not already integrated
2. **Mobile app security testing** – Anthropic-Cybersecurity-Skills mobile domain (13 skills) or dedicated mobile-specific repo
3. **API testing library** – communitytools `/api-security` or extraction from Anthropic's 28 API skills
4. **Supply chain auditing depth** – Trail of Bits supply chain domain (npm/PyPI/Go, abandoned upstreams, publisher concentration)

### Lower priority (already covered or niche):
- Payload/injection libraries (awesome-claude-skills-security is comprehensive but may be overkill)
- Threat detection/SOC skills (SecurityClaw) – only relevant if you're building incident response automation
