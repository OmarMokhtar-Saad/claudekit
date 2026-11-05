# Third-party notice: Elephant-Goldfish Model

`plan-design-critic.md` and `plan-readiness-critic.md` contain persona and standard text adapted from
the Elephant-Goldfish Model, https://github.com/google/elephant-goldfish-model (commit 0dfb5bf),
Copyright Google LLC, licensed under the Apache License, Version 2.0 (full text: `EGM-LICENSE.txt`).

Adapted files: `agents/design_critic.md`, `agents/implementation_readiness.md`,
`resources/document_standards/feature-spec-standard.md`,
`resources/document_standards/implementation-readiness-standard.md`.

Changes made: BRAINSTORM mode removed (REVIEW only); the Target Standard is inlined into each agent;
a claudekit run contract was added (plan path only, untrusted-content rule, vacuous-test check,
finding cap, `PANEL:` summary line); EGM frontmatter replaced with claudekit frontmatter.
