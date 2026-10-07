# Incident Response -- phase detail

Moved verbatim from SKILL.md.

## Incident Phases

```
┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────┐    ┌──────────┐    ┌────────────┐
│  DETECT  │ -> │  TRIAGE  │ -> │ INVESTIGATE  │ -> │ MITIGATE │ -> │ RESOLVE  │ -> │ POSTMORTEM │
└──────────┘    └──────────┘    └──────────────┘    └──────────┘    └──────────┘    └────────────┘
```

### Phase 1: Detect

**Goal**: Confirm the incident is real and capture initial data.

Steps:
1. Verify the report: Is this a real incident or a false alarm?
2. Identify symptoms: What is the user-visible impact?
3. Check monitoring dashboards: Error rates, latency, availability
4. Check recent deployments: Was anything deployed in the last 24 hours?
5. Capture initial evidence: screenshots, error messages, log excerpts

**Output**: Incident declaration with initial symptom description.

### Phase 2: Triage

**Goal**: Classify severity and assemble the response team.

Steps:
1. Classify severity (see Severity Classification below)
2. Identify affected systems and services
3. Estimate user impact (percentage of users affected, revenue impact)
4. Assign incident commander (IC)
5. Open incident communication channel
6. Notify stakeholders based on severity level

**Output**: Severity classification, assigned IC, stakeholder notification sent.

### Phase 3: Investigate

**Goal**: Find the root cause.

Steps:
1. Form a hypothesis based on symptoms
2. Gather evidence:
   - Application logs (filter by timeframe around incident start)
   - Infrastructure metrics (CPU, memory, disk, network)
   - Database metrics (connections, query latency, deadlocks)
   - Deployment history (what changed recently?)
   - Dependency status (third-party service outages?)
3. Narrow the search:
   - Use binary search on timeline to find the inflection point
   - Compare healthy and unhealthy instances
   - Check for recent config changes
4. Confirm root cause with evidence
5. Document the investigation trail

**Output**: Confirmed root cause with supporting evidence.

### Phase 4: Mitigate

**Goal**: Stop the bleeding -- reduce user impact as quickly as possible.

Options (in order of preference):
1. **Feature flag**: Disable the broken feature
2. **Rollback**: Revert to the last known good deployment
3. **Hotfix**: Apply a minimal fix to production
4. **Scale**: Add capacity if the issue is load-related
5. **Redirect**: Route traffic away from the affected service
6. **Failover**: Switch to backup system or region

Mitigation rules:
- ALWAYS prefer rollback over hotfix when possible
- NEVER apply an untested hotfix to production
- ALWAYS monitor the mitigation to confirm it reduces impact
- Document the mitigation action and timestamp

**Output**: Impact reduced, mitigation confirmed effective.

### Phase 5: Resolve

**Goal**: Fully fix the underlying issue and confirm normal operation.

Steps:
1. Implement the permanent fix (may be the same as mitigation or a more thorough fix)
2. Test the fix in staging/pre-production
3. Deploy the fix to production with careful monitoring
4. Verify all symptoms have resolved
5. Monitor for recurrence (minimum 30 minutes for SEV-1/2)
6. Confirm with stakeholders that service is restored
7. Close the incident channel

**Output**: Incident resolved, normal operation confirmed.

### Phase 6: Postmortem

**Goal**: Learn from the incident and prevent recurrence.

Timeline:
- SEV-1: Postmortem within 24 hours
- SEV-2: Postmortem within 3 business days
- SEV-3: Postmortem within 1 week
- SEV-4: Optional, at team discretion

See Postmortem Template below.

