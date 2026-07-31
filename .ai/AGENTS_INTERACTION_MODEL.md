# Agent Interaction Model

<!-- split-from-AGENTS.md -->
> Part of the agent reference. Index: [AGENTS.md](AGENTS.md)

## Agent Interaction Model

### Handoff block format (from HANDOFF_PROTOCOL.md)

Every agent-to-agent transition MUST use this exact structure — no free-form handoffs:

```
HANDOFF TO: <target-agent>
---
Task: <concise task description>
Classification: <Feature|Bug|Quality|Git|Docs|Explore|Refactor>
Pipeline Position: Step <N> of <M>
Prior Agent Output: <summary of what was produced>
Files Modified: <list of files touched so far>
Constraints:
  - <constraint 1>
  - <constraint 2>
Expected Output: <what the target agent should produce>
Return To: <agent to return to, usually coordinator>
```

Handoff rules: include all required fields, reference files by path (never embed content), state the expected output, specify return routing, include constraints. HANDOFF_PROTOCOL.md also defines agent-specific variants: Planner→Reviewer, Reviewer→Implementer (Approved), Reviewer→Planner (Revision), Implementer→Verifier, Verifier→GitOps (Pass), Verifier→Implementer (Retry), Any→Coordinator (Escalation), Debugger→Planner, TDDGuide→Implementer (Tests Written), SilentFailureHunter+SecurityScanner→Planner (Audit Complete), and RefactorCleaner→Verifier (Batch Removed).

### Named pipelines

| Pipeline | Flow | Source |
|---|---|---|
| **Feature** | Coordinator → Planner → Reviewer → Implementer → Verifier → GitOps (revision loop Planner↔Reviewer, max 3) | coordinator.md, HANDOFF_PROTOCOL.md |
| **Bug** | Coordinator → Debugger → Planner → Reviewer → Implementer → Verifier → GitOps | coordinator.md |
| **Refactor** | Same as Feature (Planner → Reviewer → Implementer → Verifier → GitOps) | coordinator.md |
| **Quality** | Coordinator → Verifier | coordinator.md |
| **Git** | Coordinator → GitOps | coordinator.md |
| **Docs** | Coordinator → DocUpdater (coordinator.md); HANDOFF_PROTOCOL.md splits: Documenter for new docs, DocUpdater for updating existing docs | coordinator.md, HANDOFF_PROTOCOL.md |
| **Explore** | Coordinator → Explore | coordinator.md |
| **TDD** | Coordinator → TDDGuide → Verifier → GitOps | coordinator.md |
| **Dead Code** | Coordinator → RefactorCleaner → Verifier → GitOps | coordinator.md |
| **Performance** | coordinator.md: Coordinator → Explore → PerformanceOptimizer → Verifier → GitOps (parallel: profile + analyze); HANDOFF_PROTOCOL.md: Coordinator → [Explore + PerformanceOptimizer] (parallel) → Planner → Implementer → Verifier | both (they disagree — see Known Issues) |
| **Security Audit** | Coordinator → [SilentFailureHunter + SecurityScanner] (parallel, read-only) → Planner → Implementer → Verifier | coordinator.md, HANDOFF_PROTOCOL.md |
| **Code Quality Audit** | Coordinator → [TypeScriptReviewer \| PythonReviewer] → Implementer (if fixes needed) → Verifier | coordinator.md |
| **EPIC / Blueprint** | Coordinator → Blueprint skill → plan review → per-step execution pipelines | coordinator.md |
| **Open Source** (specialist routing) | OpenSource Pipeline: Sanitizer (Stage 1) → Forker (Stage 2, referenced but no agent file exists) → Packager (Stage 3) | coordinator.md, opensource-*.md |

### Scoring thresholds

| Gate | Threshold | Formula | Outcomes |
|---|---|---|---|
| **Reviewer** (plan gate) | **90/100** | Plan Quality × 0.40 + Architecture × 0.30 + Security × 0.30 | ≥90 APPROVED → Implementer; 70–89 CONDITIONAL → back to Planner; <70 REJECTED → back to Planner. Each return counts as one revision cycle; revision 3 of 3 failing → escalate to Coordinator/human. Mandatory rejections (missing ops.json, invalid JSON, missing rollback, hardcoded secrets, destructive ops without safeguards, missing test strategy, orphaned operations, phantom steps) bypass scoring entirely. |
| **Verifier** (implementation gate) | **80/100** | Static Analysis × 0.30 + Tests × 0.40 + Coverage × 0.30, then anti-pattern penalties (max −30) | ≥80 PASS → GitOps; 60–79 RETRY → back to Implementer (max 2 retries); <60 FAIL → escalate to Coordinator immediately (do not return to Implementer). |

### Escalation rules (coordinator.md)

Escalate to the human user when: (1) revision limit exceeded (3 cycles without approval), (2) an agent reports an unrecoverable error, (3) classification is ambiguous, (4) any agent flags a security concern, (5) destructive operation (data deletion, force-push, production config changes), (6) conflicting requirements. Escalation format includes Reason, Current State, Context, Options, Recommendation.

Coordinator error recovery: log the error in workflow state, re-run the failed agent once with the same inputs, escalate to human if it fails again; never silently skip a pipeline agent, never proceed past a failed agent.

### Failed handoff recovery (HANDOFF_PROTOCOL.md)

If a handoff fails (target agent unavailable, invalid format): (1) log the failure with full context, (2) retry once with the same handoff, (3) if retry fails, escalate to Coordinator, (4) Coordinator decides: retry with different approach, skip the agent (if non-critical), or escalate to human.

### Parallel execution rules (coordinator.md)

Safe combinations: Explore + Debugger; Silent Failure Hunter + Security Scanner; TypeScript Reviewer + Python Reviewer; DocUpdater + GitOps; multiple Verifier instances on independent modules; Explore + Deep Research skill. Hard rules: NEVER run Implementer in parallel with anything; NEVER run GitOps in parallel with Implementer; Reviewer MUST complete before Implementer; Verifier MUST complete before GitOps; TDD Guide MUST produce tests before Implementer writes code.

---

