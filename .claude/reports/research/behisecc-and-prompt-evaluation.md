# Research: awesome-claude-skills + prompt-evaluation-claude-code

**Date:** 2026-08-25  
**Sources:** GitHub BehiSecc/awesome-claude-skills, 46ki75/skills/prompt-evaluation-claude-code

---

## A) awesome-claude-skills Catalog

### Categories (10 major)
1. **📄 Document Skills** — Word/PDF/PowerPoint/Excel/Presentation manipulation
2. **🛠 Development & Code Tools** — Testing, git workflows, AWS/Azure, UI/UX, debugging, plugins, email templates, crypto
3. **📊 Data & Analysis** — CSV, databases, Kaggle, DEX data, scraping, BI
4. **🔬 Scientific & Research** — Bioinformatics, materials simulation, academic search
5. **✍️ Writing & Research** — Content research, comms, brainstorming, genealogy, AI detection, translation
6. **📘 Learning & Knowledge** — Personal wikis, knowledge graphs, indexed markdown
7. **🎬 Media & Content** — Video transcripts, image enhancement, TTS, EPUB, music/podcast
8. **🏥 Health & Life Sciences** — Medical reports, DNA analysis, wellness
9. **🤝 Collaboration & Project Mgmt** — Linear/Jira, kanban, meetings, product/sales
10. **🛡 Security & Web Testing** — OWASP, fuzzing, auditing, PII redaction, web app testing
11. **🔧 Utility & Automation** — File org, email, LinkedIn, CRM

### Notable Skills
- **web-artifacts-builder** — React/Tailwind/shadcn/ui frontend components for HTML artifacts
- **claude-scientific-skills** — 125+ curated scientific skills for bioinformatics/cheminformatics/clinical research
- **goprogramming-skills** — 28 Go development skills (concurrency, architecture)
- **pm-skills** — 24 product management domain skills across Triple Diamond lifecycle
- **devmarketing-skills** — Developer GTM (HN strategy, technical tutorials)

### Relevance for ClaudeKit (QA/Test-Automation Fleet: Java/Maven, Kotlin/Gradle, Python; Appium; API Testing)

**High-value skills for your fleet (5–8 to monitor/adopt):**
1. **Development & Code Tools** → test automation, git workflows — covers Java/Maven/Kotlin/Gradle ecosystem
2. **Security & Web Testing** → OWASP, fuzzing, web app testing → API testing; covers compliance-driven QA
3. **claude-scientific-skills subset** → reproducibility patterns transferable to test-driven-development
4. **pm-skills** → test planning/product quality layer
5. Security & Code Auditing → pre-deployment verification (aligns with ClaudeKit's verification-before-completion)

**Gap:** No explicit Appium/mobile automation skills surfaced; catalog is language/framework-agnostic at category level (Java/Maven/Kotlin/Gradle would be inside "Development & Code Tools" but not separately indexed).

**For your 73-skill corpus:** awesome-claude-skills is a **curated consumer-facing catalog**, not an operational reference. Your existing skills (verification-before-completion, verification-gap-lens, test-driven-development, autonomous-loop, gan-harness, santa-method, hookify, eval-harness) are **more specialized** (tighter to agent orchestration + enforcement). Monitor awesome-claude-skills for external patterns (e.g., web-artifacts-builder for dynamic artifact generation) but do not adopt wholesale — your corpus is deeper and more tightly integrated.

---

## B) prompt-evaluation-claude-code Skill

### Purpose
Rapid, exploratory **prompt refinement directly in Claude Code** using isolated subagent contexts and parallel execution—avoiding external Python, SDKs, or API key dependencies.

### Method & Rubric

**Grading approaches:**
- **Reference matching** — Deterministic criteria (set equality, regex)
- **Binary judges** — Correct/incorrect verdicts with reasoning-before-decision for open-ended outputs
- **Pairwise comparisons** — Position-swapped runs to mitigate first-position bias

**Calibration mirror:** Echoes the SDK-based `prompt-evaluation` skill's rigor:
- Hand-curated eval sets (10–30 entries, sourced from real failures when possible)
- Cohen's κ ≥ 0.6 agreement threshold against human labels
- Per-failure-mode clustering rather than headline pass-rate reporting

**Key design principle:** *"One isolated judge per criterion when you have ≥2 criteria. Compound rubrics produce halo effects."*

### Structure

**Artifacts (versioned orthogonally):**
- Eval sets: `eval-set-vY.jsonl` (evaluation data)
- Candidate prompts: `candidate-vX.md` (prompt iterations)
- Per-iteration directories: candidate outputs + judge verdicts (JSON) + synthesis documents

**Five-step workflow:**
1. Capture the prompt and target job
2. Build/curate eval set (10–30 cases)
3. Select grading method (reference/judge/pairwise)
4. Spawn parallel subagents for isolated judgment
5. Aggregate failure modes, propose single-edit revision targeting root cause

**Directory structure:**
- `SKILL.md` — 15 KB (full documentation)
- `assets/` — Holds supporting materials
- `evals/` — Eval set storage
- `references/` — Reference outputs/benchmarks

### Suitability for ClaudeKit's Existing Corpus

**Suitable Use Cases:**
- Quick A/B testing of two prompt candidates within Claude Code
- Single-prompt exploration with isolated judges (fits the "one judge per criterion" rule)
- Exploratory iteration loop when waiting for code review/approval

**NOT Suitable:**
- **Production regression testing** — No versioned baseline tracking or CI integration
- **Cross-skill corpus evaluation at scale** — The skill is designed for 1–2 prompt variants, not 73 skills
- **Scenarios requiring exact API semantics** — System/user role distinction, specific model routing logic, not supported
- **Compliance/audit trails** — No structured verdict provenance

**Recommendation:**
This skill is fundamentally a **rapid exploratory tool**. Its comparative advantage is *speed and Claude Code native execution*. After iteration, port validated improvements to the SDK-based `prompt-evaluation` skill for **production regression testing and cross-corpus measurement**. ClaudeKit's existing `eval-harness` skill likely already covers the rigorous side; this would sit **upstream of eval-harness** in the development loop, not replace it.

### Adoption Path for ClaudeKit
If your workflow includes frequent prompt experimentation (new agents, command refinements):
1. Use prompt-evaluation-claude-code for rapid A/B vetting in Claude Code (hours)
2. On convergence, hand off to eval-harness or SDK-based prompt-evaluation for baseline lock-in (CI-gated)
3. Mark successful prompts in CHANGELOG_AI with the eval-harness verdict

**License:** Not stated in SKILL.md; assume repo-level license (check https://github.com/46ki75/skills/LICENSE).

---

## License Notes

- **awesome-claude-skills:** License not stated in README; check repo root or assume curator's terms.
- **prompt-evaluation-claude-code:** License not stated in SKILL.md; infer from parent 46ki75/skills repo.

---

## Conclusion

**awesome-claude-skills** is a valuable external **reference catalog** for emerging patterns (web-artifacts, scientific-skills taxonomy, pm-skills rigor), especially for Java/Maven/Kotlin/Gradle/Python/API-testing communities. Your 73-skill corpus is **more specialized** and should not be directly supplanted; instead, monitor for cross-cutting patterns (e.g., security, verification layers).

**prompt-evaluation-claude-code** is **worth adopting for rapid prompt iteration** (replaces ad-hoc manual testing), but **not as a replacement for eval-harness or production regression**: it is explicitly an exploratory tool, lightweight and fast, designed to hand off validated improvements downstream to rigorous CI-gated evaluation. Its "one isolated judge per criterion" principle is sound and aligns with ClaudeKit's verification-gap-lens philosophy.
