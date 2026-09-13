# Incident Response -- rollback procedures

Moved verbatim from SKILL.md.

## Rollback Procedures

### Application Rollback

```bash
# 1. Identify the last known good version
git log --oneline -10

# 2. Verify the target version in staging
git checkout <good-version-tag>
# Run smoke tests

# 3. Deploy the rollback
# (Use your deployment tool -- examples:)
# Kubernetes: kubectl rollout undo deployment/<name>
# AWS ECS: aws ecs update-service --force-new-deployment
# Heroku: heroku releases:rollback v<N>

# 4. Verify rollback
# Check health endpoints, error rates, key metrics

# 5. Document
echo "Rolled back from <bad-version> to <good-version> at $(date -u)"
```

### Database Rollback

1. NEVER rollback database migrations blindly in production
2. Check if the migration is backward-compatible
3. If backward-compatible: leave the migration, rollback the application
4. If not backward-compatible: apply a compensating migration (forward-fix)
5. ALWAYS have a tested rollback script for every migration before deploying

### Configuration Rollback

1. Revert the config change in the config management system
2. Verify the previous config values are correct
3. Apply the config change (may require service restart)
4. Monitor for restoration of normal behavior

---
