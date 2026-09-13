---
name: installer-order-decides-what-survives
description: In claudekit, install.sh replaces .claude/ wholesale and preserve_assets.py only restores what the new tree LACKS
metadata:
  type: feedback
---

Anything the installer writes at a path a project also owns must be written **after** `preserve_assets.py`, never during the asset phase.

**Why:** `install.sh` backs up and replaces `.claude/` wholesale, then `preserve_assets.py` carries back a backup file **only if the new tree lacks it**. The agent-memory scaffold wrote a stub during the asset phase, so preservation saw the path occupied and skipped the project's real `MEMORY.md` — months of accumulated knowledge replaced by an empty stub on every reinstall.

Moving the write after preservation is **necessary but not sufficient**. Ownership is also decided from the *old* manifest, and a manifest written by the buggy build already listed the stub as a kit asset — so preservation still declined to restore the real file. Measured, both controls on a tree carrying such a manifest:

| Configuration | Result |
|---|---|
| reorder alone | LOST |
| reorder + path-keyed always-custom rule | PRESERVED |

**How to apply:**
- Project data is decided by **path**, never by a manifest a previous build may have got wrong.
- Anything created after manifest generation is deliberately unmanaged: `ck uninstall` will not delete it and `ck diff` will not call it drift. Decide that on purpose and write down which half you chose.
- Test the *transition* (old build → new build), not just new → new. New-to-new passes while the upgrade path destroys data.

Related: [[a-green-check-can-measure-nothing]].
