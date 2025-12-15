# Rollout Strategy & Deployment Procedures
## Ranking Service v2 Greenfield Replacement

**Version:** 1.0  
**Date:** December 15, 2025  
**Status:** Ready for Rollout Planning

---

## Executive Summary

The Student Ranking System v2 is a production-ready replacement for v1 with:

1. **Fixed ranking bug** (tied scores now handled correctly)
2. **New capabilities** (idempotency, observability, state machine)
3. **Zero data loss** (backfill strategy available)
4. **Graceful rollback** (30-day standby window)

Recommended rollout: **4-week phased approach** (shadow → validation → canary → full)

---

## Phase 1: Preparation & Testing (Week -2)

### Objectives
- Finalize v2 code & tests
- Set up monitoring/alerting
- Train operations team
- Prepare rollback procedures

### Checklist

- [ ] Code review (all v2 modules)
- [ ] Performance testing (100K+ students)
- [ ] Security review (input validation, logging, PII masking)
- [ ] Documentation complete (README, architecture, API spec)
- [ ] Monitoring dashboards created
  - [ ] Request rate (req/s)
  - [ ] Latency (p50, p95, p99)
  - [ ] Error rate (%)
  - [ ] Idempotency cache hit rate
  - [ ] Tie detection rate
- [ ] Alerts configured
  - [ ] Error rate > 0.5%
  - [ ] Latency p95 > 2x baseline
  - [ ] Timeout rate > 0.1%
- [ ] Runbook prepared (troubleshooting, rollback)
- [ ] Operations team trained

### Success Criteria
- All tests passing (100%)
- Performance baseline established
- Monitoring in place
- Team trained and ready

---

## Phase 2: Shadow Mode (Week 1-2)

### Objectives
- Run v2 in parallel with v1
- Compare results (correctness, performance)
- Build confidence before cutover
- Zero user impact

### Architecture

```
┌──────────────────────────────────┐
│      Client Request              │
│   (ranking students)              │
└──────────────┬───────────────────┘
               │
        ┌──────┴──────┐
        ↓             ↓
    ┌─────────┐  ┌─────────┐
    │ v1 Live │  │ v2 Shadow
    │ (return)│  │ (log only)
    └────┬────┘  └────┬────┘
         │             │
         └──────┬──────┘
                │
        ┌───────┴────────┐
        ↓                ↓
    [Return to]    [Log Diff]
    [Client]       [Compare]
         │                │
         │          ┌──────────────────┐
         │          │ Analysis:        │
         │          │ - Correctness    │
         │          │ - Performance    │
         │          │ - Edge cases     │
         │          └──────────────────┘
```

### Procedure

1. **Deploy v2** (code only, not live traffic)
   ```
   # On ranking service servers
   git clone https://repo.git ranking-service-v2
   cd ranking-service-v2
   pip install -r requirements.txt
   ```

2. **Configure dual processing** (in API handler)
   ```python
   # Pseudocode in api_handler.py
   def process_request(request):
       v1_response = legacy_system.process(request)
       v2_response = v2_service.process(request)
       
       # Log diff for analysis
       if v1_response != v2_response:
           logger.warning("v1 vs v2 diff detected", {
               "request_id": request.request_id,
               "v1": v1_response,
               "v2": v2_response
           })
       
       # Return v1 (safe; user doesn't see v2 yet)
       return v1_response
   ```

3. **Monitor & Analyze**
   - Collect v1 vs v2 output diffs
   - Check for any regressions
   - Verify performance (latency, memory)
   - Build confidence in correctness

4. **Analyze Results** (after 1 week)
   ```bash
   python ranking-service-v2/run_comparison.sh
   # Generates: results/comparison_results.json
   ```

   Expected output:
   ```
   Total Tests:       N
   Tests with Diffs:  M (% should be tied-score scenarios only)
   Total Differences: P (all showing v1→v2 fixes)
   ```

5. **QA Sign-Off**
   - Review diffs (should only be tie-handling fixes)
   - Verify no regressions
   - Performance acceptable
   - Document any concerns

### Success Criteria
- ✅ No unexpected differences between v1 and v2
- ✅ All diffs are in tie-handling scenarios (expected)
- ✅ v2 latency ≤ v1 latency + 10%
- ✅ v2 memory usage acceptable (<200MB for 10K students)
- ✅ QA sign-off received

### Rollback (if issues found)
- Disable v2 shadow processing
- Investigate root cause
- Fix and re-test
- Extend shadow mode 1 week if critical issues

---

## Phase 3: Canary Rollout (Week 3)

### Objectives
- Return v2 results to subset of users
- Real-world validation with low blast radius
- Gradual increase in traffic %
- Production data integrity check

### Traffic Distribution

```
Timeline:  Day 1-2      Day 3-4      Day 5-6      Day 7
Traffic:   95% v1 ↑     80% v1 ↑     50% v1 ↑     0% v1
           5%  v2 ↓     20% v2 ↓     50% v2 ↓     100% v2

           [Canary 5%] [Canary 20%] [Canary 50%] [Full]
```

### Monitoring During Canary

**Metrics to Watch (every 2 minutes):**

| Metric | Threshold | Action |
|--------|-----------|--------|
| v2 error rate | > 1% | PAUSE canary; investigate |
| v2 latency p95 | > baseline + 20% | PAUSE canary; optimize |
| v2 timeout rate | > 0.5% | PAUSE canary; increase timeout |
| Correctness diff | > 0.1% unexpected | ROLLBACK; investigate |
| Cache hit rate | < 50% expected | Expected; monitor |

### Procedure for Each Stage

#### Stage 1: 5% Traffic (Day 1-2)

```
# Router/LB configuration
if hash(user_id) % 100 < 5:
    use_v2 = True
else:
    use_v2 = False
```

1. Deploy to 5% canary fleet
2. Monitor metrics (alert on threshold)
3. Review logs (should be clean; no errors)
4. QA reviews real results (check correctness)

**Go/No-Go Decision (Day 2 EOD):**
- ✅ **GO:** Metrics healthy, no unexpected diffs → Proceed to 20%
- ❌ **NO-GO:** Rollback to Shadow mode; investigate; re-test

#### Stage 2: 20% Traffic (Day 3-4)

```
if hash(user_id) % 100 < 20:
    use_v2 = True
```

Same process as Stage 1. Monitor additional 2 days.

**Go/No-Go Decision (Day 4 EOD):**
- ✅ **GO:** Metrics healthy; no issues → Proceed to 50%
- ❌ **NO-GO:** Hold at 20% for 1 more day; or rollback

#### Stage 3: 50% Traffic (Day 5-6)

```
if hash(user_id) % 100 < 50:
    use_v2 = True
```

Monitor 2 days with 50% traffic.

**Go/No-Go Decision (Day 6 EOD):**
- ✅ **GO:** Metrics healthy; high confidence → Proceed to 100%
- ❌ **NO-GO:** Revert to 20% for 1 more day; investigate; re-test

#### Stage 4: 100% Traffic (Day 7)

```
use_v2 = True (all users)
# v1 kept in standby for 30 days
```

### Rollback Procedure (Canary Phase)

If issues detected during any stage:

1. **Immediate:** Revert traffic to previous stable percentage
   ```bash
   # Example: If at 20% and issues found, revert to 5%
   ./deploy_canary.sh --percentage 5
   ```

2. **Diagnosis:** Check logs, metrics, recent code changes
   ```bash
   # Review v2 logs from past 1 hour
   tail -1000 logs/test_output_v2.log | grep ERROR
   
   # Check metrics
   curl http://localhost:8000/api/v2/metrics | jq
   ```

3. **Fix:** Hotfix code or configuration
   ```bash
   # Example fixes:
   - Increase timeout_ms (if timeout issues)
   - Optimize ranking algorithm (if latency issues)
   - Adjust cache TTL (if cache issues)
   - Revert specific commit (if regression)
   ```

4. **Retest:** Shadow mode for fixed code
   ```bash
   python ranking-service-v2/run_comparison.sh
   ```

5. **Resume:** Restart canary at previous percentage
   ```bash
   ./deploy_canary.sh --percentage 5  # Start fresh at 5%
   ```

### Success Criteria
- ✅ All 4 canary stages completed successfully
- ✅ Error rate remains < 0.5% throughout
- ✅ Latency acceptable (p95 within baseline + 20%)
- ✅ No unexpected correctness issues
- ✅ Cache hit rate as expected (60-80%)
- ✅ QA and ops team sign-off

---

## Phase 4: Full Production (Week 4)

### Objectives
- v2 receives 100% production traffic
- Migrate all users from v1 to v2
- Maintain v1 in standby (30-day window)
- Monitor for any production issues

### Procedure

1. **Final Deployment**
   ```bash
   # Remove traffic split; route all to v2
   ./deploy_full.sh --version v2 --keep-v1-standby 30
   ```

2. **Monitoring (increased frequency)**
   - Check metrics every 5 minutes (vs 2 min in canary)
   - Set up incident response team
   - Daily standups for first week

3. **Backfill Historical Data** (if needed)
   ```bash
   # Re-rank historical requests using v2 algorithm
   python ranking-service-v2/scripts/backfill_rankings.py \
     --from-date 2025-01-01 \
     --to-date 2025-12-14 \
     --dry-run  # Verify first
   
   # After verification:
   python ranking-service-v2/scripts/backfill_rankings.py \
     --from-date 2025-01-01 \
     --to-date 2025-12-14
   ```

4. **Announce to Users** (if applicable)
   - Blog post: "Student Ranking System Improved"
   - Highlight fairness improvements (tie handling)
   - Document any changes in behavior

### 30-Day Standby Window

Keep v1 running in standby mode:

```
v2: Active (100% traffic)
v1: Standby (not serving traffic)
```

If critical issue in v2 discovered:

```bash
# Emergency rollback to v1
./rollback_to_v1.sh --immediate

# This will:
# 1. Route all traffic back to v1
# 2. Keep v2 logs/data for analysis
# 3. Page on-call engineer
# 4. Trigger incident response
```

After 30 days (Day 38 from start):

```bash
# Decommission v1 (after verified stability)
./decommission_v1.sh --confirm
```

### Success Criteria
- ✅ 100% traffic on v2 for 7+ days
- ✅ Error rate < 0.5% sustained
- ✅ No production incidents
- ✅ User feedback positive (if applicable)
- ✅ v1 standby operational (ready for 30-day window)

---

## Full Rollback (Emergency)

If critical issue in any phase:

### Immediate (< 5 minutes)

1. **Revert traffic to stable version**
   ```bash
   # Example: Critical issue in v2, revert to v1
   ./switch_traffic.sh --target v1 --immediate
   ```

2. **Page on-call team**
   - Alert incident commander
   - Begin war room
   - Preserve logs/traces

3. **Confirm traffic switched**
   - Verify all requests going to v1
   - Check error rate drops
   - Monitor user impact

### Investigation (< 30 minutes)

1. **Collect evidence**
   - v2 logs (past 1 hour)
   - Request traces (sampling)
   - Metrics (latency, errors, diffs)
   - Stack traces (if exceptions)

2. **Root cause analysis**
   ```bash
   # Example: Analyze error spike
   grep "ERROR" logs/test_output_v2.log | head -100
   
   # Check metrics snapshot
   curl http://localhost:8000/api/v2/metrics > metrics_snapshot.json
   
   # Review code changes
   git log --oneline ranking-service-v2/ | head -10
   ```

3. **Determine fix**
   - Code bug fix (revert/hotfix)
   - Configuration change (timeout, batch size)
   - Data cleanup (corrupted cache)

### Fix & Retest (< 2 hours)

1. **Implement fix**
   ```bash
   # Example: Hotfix code
   cd ranking-service-v2
   git checkout -b hotfix/critical-issue
   # Make code changes
   git commit -m "Fix: ..."
   ```

2. **Test locally**
   ```bash
   pytest tests/test_api.py::TestIntegration::test_002_tied_first_place -v
   python run_comparison.sh
   ```

3. **Deploy fixed v2 to shadow** (not live yet)
   ```bash
   ./deploy_v2_shadow.sh --version fixed
   ```

4. **Run shadow comparison** (1-2 hours)
   - Verify fix resolves issue
   - Check for new regressions

### Resume Rollout

If fix validated:

```bash
# Option A: Resume canary from current stage
./resume_canary.sh --percentage <prev_percentage>

# Option B: If confident, skip ahead
./deploy_canary.sh --percentage 50
```

If fix not validated:

1. Hold in shadow mode for extended testing
2. Re-assess rollout timeline
3. May need to defer to next cycle

---

## Monitoring & SLOs

### Key Metrics

| Metric | v1 Baseline | v2 Target | Alert Threshold |
|--------|------------|-----------|-----------------|
| Request latency (p95) | 50ms | ≤ 50ms | > 100ms |
| Error rate | < 0.1% | < 0.5% | > 1% |
| Idempotency cache hit | N/A | 60-80% | < 40% |
| Tie detection rate | N/A | 2-10% | N/A (monitor) |
| Timeout rate | 0% | < 0.1% | > 0.5% |
| Database latency | N/A | < 10ms | > 50ms |

### Dashboard Requirements

Create dashboards for:

1. **Health Overview**
   - Request rate (requests/sec)
   - Error rate (%)
   - Latency (p50, p95, p99)
   - Uptime (%)

2. **v1 vs v2 Comparison** (during canary)
   - Side-by-side error rates
   - Side-by-side latency
   - Correctness diffs (rolling log)

3. **Detailed Diagnostics**
   - Request latency by student count
   - Tie detection frequency
   - Cache hit rate over time
   - Error breakdown (validation vs processing)

### Alerting Rules

```yaml
# Example Prometheus alerts
alert: RankingServiceV2HighErrorRate
expr: rate(requests_failed[5m]) > 0.005
for: 5m
action: page_oncall

alert: RankingServiceV2HighLatency
expr: histogram_quantile(0.95, request_latency_ms) > 100
for: 5m
action: page_oncall

alert: RankingServiceV2TimeoutRate
expr: rate(requests_timeout[5m]) > 0.001
for: 5m
action: escalate_to_lead
```

---

## Post-Rollout (Week 5+)

### Objectives
- Stabilize production
- Optimize performance
- Plan future improvements
- Gather user feedback

### Daily (Week 1)

- Check metrics (hourly reviews)
- Monitor error logs
- Respond to any user reports
- Update status page

### Weekly (Week 2-4)

- Analyze performance trends
- Review user feedback
- Identify optimization opportunities
- Plan next phase (e.g., caching layer)

### Monthly (Month 2+)

- Full retrospective
- Document lessons learned
- Plan optimizations
- Update documentation

### Post-30-Day (Week 5+)

- Decommission v1 (if everything stable)
- Celebrate successful rollout!
- Plan next improvements

---

## Risks & Mitigation

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|-----------|
| Correctness regression | Critical | Low | Shadow mode (1-2 week); extensive testing |
| Performance degradation | High | Low | Canary rollout with monitoring |
| Data loss | Critical | Very Low | Backfill strategy; read-only v1 standby |
| Cache poisoning | Medium | Low | TTL-based expiry; manual invalidation |
| Timeout cascades | High | Medium | Timeout SLA; circuit breaker; retries |
| User complaints | Medium | Medium | Rollback plan; support team prepared |

---

## Contacts & Escalation

### On-Call Rotation

- **Primary:** [Name] - [Phone/Slack]
- **Secondary:** [Name] - [Phone/Slack]
- **Manager:** [Name] - [Phone/Slack]

### Escalation

```
0-30 min:   On-call page
30 min:     Escalate to engineering lead
1 hour:     Escalate to manager
2+ hours:   Full incident response
```

### War Room

- **Slack:** #ranking-service-incident
- **Zoom:** [Link]
- **Runbook:** [Drive Link]

---

## Appendix: Rollback Commands

### Full Rollback to v1

```bash
# Emergency: Route all traffic to v1
./switch_traffic.sh --target v1 --immediate

# Verify
curl http://api.example.com/health
# Should show: {"version": "v1", "status": "healthy"}

# Hold v2 for analysis (don't delete)
# Incident response team reviews logs
```

### Partial Rollback (Canary)

```bash
# Revert from 20% to 5%
./deploy_canary.sh --percentage 5

# Or to previous known-good stage
./resume_from_checkpoint.sh --checkpoint canary-5-percent
```

### Restore v1 Standby

```bash
# After 30 days, if keeping v1:
./promote_standby.sh --version v1

# Or full decommission
./decommission_v1.sh --confirm --archive /backups/v1
```

---

**End of Rollout Strategy**

For questions, contact: [Team Lead Name]  
Last updated: December 15, 2025
