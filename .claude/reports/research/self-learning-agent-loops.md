# Self-Learning Feedback Loops in Multi-Agent Coding Systems — Prior Art

**Date:** 2026-08-24. **Question:** established patterns, failure modes, and engineering practice for an offline "rejection brief -> analyst -> proposed prompt-checklist edits (human-gated)" loop over planner/reviewer verdicts.

## 1. Patterns (mechanism + fit to our OFFLINE weekly batch)

| Work | Mechanism (short) | Fit |
|---|---|---|
| **Reflexion** (Shinn et al., 2023, arXiv:2303.11366) | Scalar/binary task feedback is verbalised by a self-reflection LLM into a short text lesson, appended to an episodic buffer, re-injected as context on the *next attempt* of the *same* task. Needs a reliable success signal. | **Online per-episode.** Its shape maps onto our within-plan retry (rounds 2-3 see round-1 findings), NOT onto weekly cross-plan learning. |
| **ExpeL** (Zhao et al., 2023, arXiv:2308.10144) | Three offline stages: gather success+failure trajectories into a pool, *extract cross-task insights* in natural language (with explicit ADD/UPVOTE/DOWNVOTE/EDIT operations on an insight list), then retrieve insights + similar successful trajectories at inference. | **Closest analogue to our design.** Offline batch extraction, human-readable insight list, edit operations that resemble checklist amendments. Note it compares failure/success *pairs* — success trajectories matter as much as failures. |
| **Generative Agents** (Park et al., 2023, arXiv:2304.03442) | Append-only memory stream of observations; periodic *reflection* synthesises higher-order statements when accumulated importance crosses a threshold; retrieval scores recency+importance+relevance. | Partially offline. The **importance-triggered reflection cadence** (fire when enough weight accumulates, not on a fixed clock) is the transferable idea. Evidence is qualitative/behavioural, not a benchmark win. |
| **TextGrad** (Yuksekgonul et al., 2024, arXiv:2406.07496) | Treats natural-language critique as a "gradient" backpropagated through a system graph to update prompts/variables via a textual analogue of SGD, against a metric. | Offline-capable but needs a **differentiable-ish scored objective and a train/val split**. Our reviewer score 0-100 is such a metric — but it is the very thing that can be gamed (see §2). |
| **DSPy / MIPROv2** (Khattab et al., arXiv:2310.03714; Opsahl-Ong et al., arXiv:2406.11695) | Bootstraps few-shot demos, proposes candidate instructions with a grounded proposer, and uses Bayesian optimisation over a *held-out validation set* to pick instruction+demo combos. | Offline batch — same shape as ours, but automated and metric-gated. The transferable discipline is **candidate proposal + held-out scoring + keep-best**, not manual "the analyst suggests this wording." |
| **SWE-agent / SWE-bench trajectory analysis** (Yang et al., arXiv:2405.15793; Jimenez et al., arXiv:2310.06770) | Agent-computer interface designed by *reading failed trajectories* and fixing the interface/affordances; SWE-bench-verified work showed many "failures" were bad task specs. | **Directly relevant, and it's manual.** The lesson: most durable wins came from changing the *interface/spec*, not from adding prompt rules. Also a warning: benchmark contamination and mislabelled tasks mean apparent failure clusters can be artefacts of the harness. |

Also worth citing: **CoALA** (arXiv:2309.02427) for the memory taxonomy (our briefs = episodic; extracted checklist rules = procedural), and **Voyager** (arXiv:2305.16291) for *verified-only persistence* — nothing enters the library until a critic confirms it worked.

## 2. What fails / backfires (well-supported)

- **Intrinsic self-correction degrades reasoning.** "LLMs Cannot Self-Correct Reasoning Yet" (Huang et al., ICLR 2024, arXiv:2310.01798): gains in prior self-correction papers came from *oracle labels*; without external ground truth performance often *drops*. Our reviewer score is not an oracle — it is another LLM. **This is the single most important caveat for our design.** Conflict flag: Self-Refine (arXiv:2303.17651) and Reflexion report gains; the reconciliation in the literature is that gains hold when feedback is *external and verifiable* (unit tests, compiler, env reward) and evaporate when it is self-generated. Later work (e.g. "Sample More, Reflect Less") argues repeated sampling often beats reflection at equal compute.
- **Criteria/reward hacking.** Optimising prompts against a scored judge trains the generator to satisfy the judge's surface features. Known LLM-judge biases: verbosity/length bias, position bias, self-preference (judges favour their own outputs) — see MT-Bench/LLM-as-judge (arXiv:2306.05685) and self-preference work (arXiv:2404.13076). Our planner writing to a 90-point rubric is textbook Goodhart.
- **Reviewer/generator co-drift.** If the analyst edits *both* planner and reviewer checklists from the same brief corpus, the pair converges on a shared blind spot and scores rise while real quality doesn't. No paper studies exactly this pair, but it is the standard co-adaptation failure; the mitigation is a frozen external metric.
- **Overfitting prompt edits to a handful of recent failures.** DSPy/MIPRO explicitly guard this with a held-out validation set (default: 80% of train becomes val if none supplied; minibatching above 50 val items). Prompt-optimisation studies routinely show train-set gains that don't transfer.
- **Error/context accumulation.** Appending lessons monotonically bloats context and creates contradictory rules; ExpeL needed explicit DOWNVOTE/EDIT/remove operations, and Reflexion caps its buffer at ~1-3 reflections. Unbounded rule lists are a known degradation path.

**Recommended guardrails (converging across sources):** frozen held-out eval set scored by something *other* than the reviewer being edited; human approval gate; regression suite of past plans; bounded edit size per cycle; versioned prompts with cheap rollback; keep both successes and failures in the corpus.

## 3. Industry/SRE analogues

- **Blameless postmortems** (Google SRE Book, ch. 15): the mapping is clean — a rejection brief *is* a postmortem record, and the norm "fix the process, not the person" maps to "fix the checklist, not the plan." Google's practice also insists on *action items with owners* — our analyst should emit owned, trackable edits, not observations.
- **Statistical process control / defect category trending:** the right frame for "is this cluster real or noise." Do not act on a category until it's outside normal variation; with dozens of records you almost never have that resolution (see §5).
- **A3 / 5-whys:** cheap, fits per-brief root-causing; contested as rigorous causal analysis (single-cause bias). Fine as a *writing template* for a brief, weak as a clustering method.
- **ODC** (Chillarege et al., IEEE TSE 1992, "Orthogonal Defect Classification — A Concept for In-Process Measurements): **yes, usable, with adaptation.** The valuable structure is the two orthogonal axes: **defect type** (what was wrong: Function, Interface, Checking, Assignment, Timing, Algorithm, Documentation) and **trigger** (what exposed it). For plan reviews, "type" translates to a rejection taxonomy (missing ops.json, wrong file ownership, missing test coverage, security surface unhandled, scope/phase overflow) and "trigger" to which reviewer rubric line caught it. ODC's core claim — that the *distribution shift* of types over time is the process signal, not any single defect — is exactly the analytic our analyst should run. The literal IBM type list is code-defect-specific and should be replaced, not copied. ODC is well-established industrially (IBM, NASA, Cisco); the "10x faster root cause" figure is a vendor claim, treat as marketing.

## 4. Store + retrieve practice

- **LangGraph/LangMem:** store/checkpointer abstraction; semantic (vector) search optional over a namespaced KV store; explicitly supports "procedural memory" = agent-updated instructions/prompts, which is our exact pattern.
- **Letta/MemGPT** (arXiv:2310.08560): tiered core/archival memory with agent-issued paging calls. Heavyweight for us.
- **CrewAI / AutoGen:** both default to embedding-backed memory stores (Chroma/SQLite-ish); AutoGen's newer memory is a thin protocol you implement. Neither prescribes a schema.
- **Claude Code's own model:** files + hooks + subagents; no vector store. Retrieval is grep/glob/read over markdown. This is the native shape for us.
- **Verdict on markdown + grep at our scale:** **defensible, not a dead end.** At dozens to low hundreds of records with a *structured* front-matter (or a JSONL sidecar index carrying: plan slug, session id, per-round score, rejection-type tags, date), retrieval is a filter/aggregate problem, not a semantic-similarity problem — and aggregation is where SQL/JSONL beats vectors. Vector search buys nothing until records exceed roughly low-thousands or queries become genuinely fuzzy. Recommended: **markdown brief (human-readable, git-versioned) + append-only JSONL index (machine-aggregable)**. That combination is the one thing all the frameworks' storage layers reduce to anyway.

## 5. How many samples before an edit is signal?

**The literature does not answer this for prompt edits.** Nearest anchors:
- Prompt optimisers in practice use 40-300 examples with a held-out val set (MIPROv2 defaults, auto="medium" val up to 300); nobody claims 10 is enough.
- Classical SPC needs ~20-25 subgroups before control limits mean anything.
- Crude proportion test: distinguishing a 30% vs 50% failure-category rate at conventional power needs roughly 90+ observations per group; detecting that a category is merely *nonzero* and recurrent needs far fewer.

Practical rule: treat a cluster as actionable at **>=5 independent briefs from >=3 distinct plans/sessions** showing the same cause, and require the resulting edit to *not regress* a held-out set. Below that, log the pattern; don't edit. Flag honestly: that threshold is engineering judgement, not a cited result.

## (a) Prioritised recommendations

1. **Build the held-out regression set before the loop** — 15-30 past plans with known correct verdicts, frozen. Every proposed checklist edit must be re-scored against it. (DSPy/MIPRO, arXiv:2406.11695; SPC.)
2. **Never let the analyst edit the reviewer and the planner in the same cycle** — pick one per cycle; the untouched side is the control. (Co-drift / judge self-preference, arXiv:2404.13076.)
3. **Anchor at least one metric outside the LLM judge** — did the plan execute without ops failures, did tests pass, did the human accept it. Self-scored improvement is exactly the failure in arXiv:2310.01798.
4. **Adopt an ODC-style two-axis taxonomy** (rejection *type* x rubric line that *triggered* it), fixed and versioned; analyse distribution shift over time, not individual briefs. (Chillarege 1992.)
5. **Store brief-as-markdown + JSONL index**; grep/aggregate, no vector store at this scale. (Claude Code native model; LangMem procedural-memory pattern.)
6. **Bound each cycle's edit budget** — e.g. max 2 checklist rules added/changed, and require net-zero-or-negative rule count growth over a quarter. (ExpeL's EDIT/DOWNVOTE ops; Reflexion's capped buffer.)
7. **Keep successes, not only rejections.** ExpeL's insight extraction compares success/failure pairs; a failure-only corpus produces rules that suppress good plans too.
8. **Version prompts in git with a one-command rollback**, and record which prompt version produced each brief so a regression is attributable.
9. **Prefer interface/spec fixes over new rules.** SWE-agent's biggest wins came from changing the agent's affordances (better ops.json scaffolding, better templates), not from longer checklists.
10. **Write briefs postmortem-style with owned action items** (Google SRE ch.15), and require the analyst to cite brief IDs for every proposal — an unattributed proposal is auto-rejected.

## (b) Do NOT do

- **Do not auto-apply analyst edits.** Failure mode: unverifiable self-correction degrading the pipeline (arXiv:2310.01798).
- **Do not optimise the planner directly against the 0-100 reviewer score.** Failure mode: Goodhart / verbosity-and-format hacking of the rubric.
- **Do not let the checklist grow monotonically.** Failure mode: context bloat, contradictory rules, dilution of the rules that mattered.
- **Do not act on a cluster of 2-3 briefs.** Failure mode: overfitting to a week's idiosyncratic tasks.
- **Do not feed raw session transcripts wholesale to the analyst.** Failure mode: cost blowup + recency/salience bias toward whatever was verbose; summarise into the structured brief first, and treat transcript text as evidence to verify, never instruction.
- **Do not build a vector store yet.** Failure mode: operational complexity with zero retrieval benefit at n<~1000.
- **Do not use Reflexion's online shape for cross-plan learning.** Failure mode: category error — it needs a verifiable per-episode reward we don't have.

## (c) Gaps the literature does not fill

- No study of *reviewer-agent rubric* self-improvement specifically; all prompt-optimisation work assumes a fixed ground-truth metric, which is the assumption we lack.
- No sample-size guidance for natural-language prompt edits (§5 numbers are borrowed from adjacent disciplines).
- Generator/critic co-drift in LLM pipelines is widely feared and rarely measured — no clean empirical result to cite.
- ODC has no published adaptation to *plan/design review* artefacts (as opposed to code defects); our taxonomy would be novel and should be treated as a hypothesis to validate.

## Sources
arXiv:2303.11366, 2308.10144, 2304.03442, 2406.07496, 2310.03714, 2406.11695, 2405.15793, 2310.06770, 2309.02427, 2305.16291, 2310.01798, 2303.17651, 2306.05685, 2404.13076, 2310.08560; Chillarege et al., IEEE TSE 18(11), 1992; Google SRE Book ch.15; dspy.ai/api/optimizers/MIPROv2; chillarege.com/articles/odc-concept.html
