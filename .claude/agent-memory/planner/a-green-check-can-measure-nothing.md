---
name: a-green-check-can-measure-nothing
description: In claudekit, three separate "passing" checks this session were inert; prove a check can fail before believing it passes
metadata:
  type: feedback
---

Before reporting any check as evidence, make it fail on purpose. A check that cannot fail is not a check, and it reads identically to one that works.

**Why:** three inert checks in one session, each found by something other than review:

1. **An idempotence probe re-ran `install.sh` without `--yes`.** The second run exited non-zero and never installed, so the file survived for a reason unrelated to the code. The probe "passed" while the shipped code destroyed accumulated memory on every real reinstall.
2. **Two mutation-proof tests loaded the wrong module.** `_load_sanitizers()` resolved the script's own tree before the target project's, so the `reflection.py` the tests mutated in `tmp_path` was never read. Both tests proved nothing; a reviewer found it by tracing the candidate order.
3. **An order-independence test** asserted a property that pre-sorting already guaranteed, while the failure mode actually worth bounding (complete-linkage chaining) went untested. It would have passed forever.

**How to apply:**
- Write the test red first and *see* it red. A test written after the fix has never demonstrated it can fail.
- For a reuse claim, mutate the thing being reused and assert the caller changes. If it does not, the reuse is a copy.
- Negative control alongside the positive: with the fix reverted, the test must fail. Both directions, measured.
- Prose review does not catch this class. Only execution does.

Related: [[installer-order-decides-what-survives]].
