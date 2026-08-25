# Third-party licenses

ClaudeKit is MIT-licensed (see `LICENSE`). `MANIFEST.in` ships `.claude/` into the sdist, so
a small number of prompt-corpus files carry their own upstream terms and travel with the
package. They are listed here so the distribution's licensing is legible from one place.

**Nothing here changes the license of ClaudeKit's own code**, which remains MIT.

## CC BY-SA 4.0 (share-alike)

| File | Upstream | Terms |
|---|---|---|
| `.claude/skills/differential-security-review/SKILL.md` | [`trailofbits/skills`](https://github.com/trailofbits/skills) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/) |

The risk-first prioritisation, size-adaptive depth and attack-scenario evidence rule in that
file are adapted from Trail of Bits' skills corpus, which makes the file a derivative work.
Share-alike applies **to that file**: redistribute it, or a modified version of it, under
CC BY-SA 4.0 and keep its attribution block intact. The rest of the skill's content predates
the adaptation and the attribution block marks what is derivative.

## MIT

| File | Upstream chain |
|---|---|
| `.claude/skills/verification-gap-lens/SKILL.md` | SHAFT_ENGINE `chaos-engine` (MIT), itself adapted from bmad-method (MIT) |
| `.claude/skills/token-optimization/SKILL.md` | SHAFT_ENGINE `chaos-engine` reference notes (`context-economy.md`, `script-first.md`), MIT, Copyright (c) 2026 ChaosEngine contributors |

MIT-to-MIT, so no additional obligation beyond the attribution already in each file.

## Reimplementations (no upstream license inherited)

| File | Relationship |
|---|---|
| `.claude/skills/prompt-evaluation/SKILL.md` | Method reimplemented from `46ki75/prompt-evaluation-claude-code`. **The upstream SKILL.md states no license, and the parent repository's terms were not verified** (as of 2026-08-25) — which is precisely why the method was reimplemented rather than adapted. No upstream text was copied; the file is original work and MIT like the rest of the corpus. If the parent repo is later found to carry terms that reach the method itself, revisit this row. |

## Adding to this file

Any new file adapted from an upstream source gets a row here **and** an attribution block at
the top of the file itself. If the upstream terms are copyleft, say so in both places — a
share-alike file inside an MIT distribution is legible only if it is written down.
