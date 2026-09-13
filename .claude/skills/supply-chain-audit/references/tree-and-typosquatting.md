# Supply Chain Audit -- tree analysis, typosquatting, abandoned packages

Moved verbatim from SKILL.md.

## Dependency Tree Analysis

### Step 1: Map the Full Tree

Generate the complete dependency tree including transitive dependencies:

| Ecosystem | Command | Output |
|---|---|---|
| Node.js | `npm ls --all --json` | Full tree with versions |
| Python | `pip-compile --generate-hashes` or `pipdeptree --json` | Pinned tree with hashes |
| Rust | `cargo tree` | Hierarchical dependency tree |
| Go | `go mod graph` | Module dependency graph |
| Java | `mvn dependency:tree` or `gradle dependencies` | Resolved dependency tree |

### Step 2: Identify Risk Concentration

Flag dependencies that appear as transitive dependencies of many packages. A compromised package deep in the tree can affect the entire application.

**Red flags in the tree:**
- A single maintainer package depended on by 10+ other packages
- Packages with post-install scripts (`scripts.postinstall` in package.json)
- Native binary dependencies pulled from non-registry sources
- Git URLs or tarball URLs instead of registry references

---

## Typosquatting Detection

### Common Typosquatting Patterns

| Pattern | Legitimate | Typosquat Example |
|---|---|---|
| Character swap | `lodash` | `lodahs`, `lodashs` |
| Hyphen manipulation | `cross-env` | `crossenv`, `cross--env` |
| Scope confusion | `@babel/core` | `babel-core` (outdated), `@bable/core` |
| Prefix/suffix | `express` | `express-js`, `node-express` |
| Homoglyph | `request` | `requets` (with zero-width chars) |

### Detection Checklist

- [ ] Compare each dependency name against known legitimate packages
- [ ] Check for packages published within the last 30 days with names similar to popular packages
- [ ] Verify npm scope owners match expected organizations
- [ ] Flag any dependency with fewer than 100 weekly downloads that shares a name pattern with a popular package
- [ ] Check for packages with identical descriptions but different names

---

## Abandoned Package Indicators

| Signal | Threshold | Risk |
|---|---|---|
| Last publish date | > 24 months ago | High - no security patches |
| Open issues without response | > 50 unanswered | Medium - unmaintained |
| Last commit to repository | > 18 months ago | High - likely abandoned |
| Repository archived | Archived flag set | Critical - confirmed abandoned |
| Maintainer account activity | No activity in 12 months | High - account may be hijacked |
| Transfer of ownership | Recent transfer to unknown entity | Critical - investigate immediately |

### What To Do With Abandoned Dependencies

1. Check if a maintained fork exists
2. Evaluate whether the functionality can be replaced with a standard library call
3. If the package is small, consider inlining the code (with license compliance)
4. If no alternative exists, document the risk and monitor for CVEs

---

