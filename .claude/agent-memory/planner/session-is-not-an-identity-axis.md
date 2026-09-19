---
name: session-is-not-an-identity-axis
description: One ClaudeKit pipeline is ONE session id, so any author-vs-reviewer gate built on sessions either over-binds or measures nothing
metadata:
  type: project
---

`review-record.py::_session_id` falls back to a process-tree match and refuses `agent-`
transcripts, so every subagent resolves to its PARENT session. Main agent stamps the
baseline, reviewer subagent scores, implementer executes — all one id. A gate comparing
author session to reviewer session can therefore never pass (shipped in `61ed9c1`, exit 6
on every run, while its CHANGELOG claimed it "does not bind").

**Why:** the plan, the reviewer and the author all accepted a docstring aside ("nothing
exports CLAUDE_SESSION_ID, so this is unknown in practice") as a behavioural claim about a
gate. Nobody executed the resolver.

**How to apply:** when planning any "who did X vs who did Y" check in this repo, the only
available axis is the role the caller ASSERTS (attestation), because the recording command
is always run by the caller, never by the subagent that produced the text. Say
"attestation, not enforcement" explicitly. And run the resolver before trusting a claim
about what an identity function returns — see [[a-green-check-can-measure-nothing]].
