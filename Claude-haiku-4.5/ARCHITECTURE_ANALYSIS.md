# Architecture Analysis & Greenfield Replacement Design
## Student Ranking System (RANK-001)

**Date:** December 15, 2025  
**Role:** Senior Architecture & Delivery Engineer  
**Status:** Analysis & Design Complete  

---

## Executive Summary

The legacy **Student Ranking System** contains a critical functional bug in rank calculation with tied scores. This analysis identifies root causes and provides a comprehensive greenfield replacement design that addresses:

- **Incorrect ranking logic** (off-by-one in competition ranking)
- **Lack of idempotency guarantees** (no request tracking)
- **Missing state machine** (implicit lifecycle)
- **No compensation/retry mechanisms** for distributed scenarios
- **Limited observability** (no structured logging)

**Recommendation:** Greenfield v2 replacement with event-driven architecture, idempotent operations, and comprehensive observability.

---

## 1. Clarification & Data Collection

### 1.1 Missing Data / Assumptions

| Item | Status | Assumption |
|------|--------|-----------|
| Real-world scale | Unknown | Assume 100K-1M students; batch ranking operations likely |
| External dependencies | None identified | Ranking is pure computation; no DB/API calls currently |
| Concurrent updates | Not specified | Design for concurrent-safe operations via request ID |
| Audit requirements | Not specified | Assume scorecard/transparency required for fairness |
| Rollback requirements | Not specified | Assume need to reconcile vs. previous rankings |
| Performance SLA | Not specified | Assume <100ms for 10K students (p95) |
| Integration points | Not specified | Assume future webhook/event integration |

### 1.2 Collection Checklist (For Future Iterations)

- [ ] Production ranking data (historical scores, tie patterns)
- [ ] Performance baseline (current latency p50/p95)
- [ ] User workflow logs (ranking frequency, batch sizes)
- [ ] Fairness audit logs (how ties affect awards/scholarships)
- [ ] Concurrent request patterns (simultaneous ranking requests)
- [ ] Integration with grade entry system (API schema)
- [ ] Monitoring/alerting requirements (SLO/SLA targets)

---

## 2. Background Reconstruction: Legacy Business Context

### 2.1 Core Capability

**Primary:** Rank students by score with **standard competition ranking** (same score → same rank).

**Lifecycle:**
```
[Input: Student(name, score)] 
  → [Validate: 0 ≤ score ≤ 100] 
  → [Sort by score descending] 
  → [Assign ranks: same score = same rank, next different score = count + 1] 
  → [Output: Student(name, score, rank)]
```

### 2.2 Business Rules

1. **Score Validity:** Integer/float ∈ [0, 100]
2. **Ranking Rules (Standard Competition):**
   - Alice 95, Bob 95, Charlie 90 → Ranks: 1, 1, 2
   - Not 1, 2, 3 (this is the bug)
3. **Determinism:** Same input always produces same output
4. **Fairness:** No student disadvantaged by implementation details

### 2.3 Known Boundaries

| Dimension | Description |
|-----------|-------------|
| **Input** | List of students (name, score pairs) |
| **Processing** | Pure computation; no I/O |
| **Output** | Ranked student list (name, score, rank) |
| **State** | In-memory (no persistence shown) |
| **Concurrency** | Implicit; not handled currently |
| **Errors** | Score validation only |

---

## 3. Current-State Scan & Root-Cause Analysis

### 3.1 Issues by Category

| Category | Symptom | Root Cause | Evidence | Severity |
|----------|---------|-----------|----------|----------|
| **Functionality** | Incorrect ranks with ties | Array index used as rank; no score comparison in loop | Code line 37; `student.rank = index + 1` | 🔴 Critical |
| **Correctness** | 4 out of 7 tests fail | Logic doesn't implement competition ranking semantics | Test failures: `test_two_students_tied_first_place`, `test_multiple_ties_complex`, `test_all_students_same_score`, `test_with_json_data` | 🔴 Critical |
| **Maintainability** | Hard to extend (e.g., add custom ranking strategies) | Monolithic function; no strategy pattern or composition | Single `calculate_rankings()` method; no abstraction for rank assignment | 🟠 Medium |
| **Observability** | No audit trail of rank changes | No logging, no request ID, no state snapshots | No logs on ranking completion; can't trace fairness issues | 🟠 Medium |
| **Reliability** | No idempotency keys | No request tracking; same request could produce inconsistent state | Concurrent calls to `calculate_rankings()` could race | 🟠 Medium |
| **Testability** | Test hardcoded data paths | Tests assume specific directory structure; brittle | Relative path in test: `os.path.join(..., 'data', 'students.json')` | 🟡 Low |

### 3.2 Root-Cause Evidence: The Bug Chain

```
Timeline: Buggy Execution
──────────────────────────────────────────────────────────

Input: Alice(95), Bob(95), Charlie(90)
       ↓
sorted_students = [Alice(95), Bob(95), Charlie(90)]  ← sorted correctly
       ↓
Loop iteration 1: enumerate() → index=0
  student = Alice
  student.rank = 0 + 1 = 1  ✅ Correct
       ↓
Loop iteration 2: enumerate() → index=1
  student = Bob
  student.rank = 1 + 1 = 2  ❌ WRONG (should check if score==previous, then rank=1)
       ↓
Loop iteration 3: enumerate() → index=2
  student = Charlie
  student.rank = 2 + 1 = 3  ❌ WRONG (should be 2; only 2 people ranked so far)
       ↓
Output: [(Alice, 95, 1), (Bob, 95, 2), (Charlie, 90, 3)]
        
Expected: [(Alice, 95, 1), (Bob, 95, 1), (Charlie, 90, 2)]
```

### 3.3 Fix Path for Legacy (Not Recommended)

If patching in-place:

```python
def calculate_rankings(self) -> List[Student]:
    sorted_students = sorted(self.students, key=lambda s: s.score, reverse=True)
    
    current_rank = 1
    for index, student in enumerate(sorted_students):
        if index > 0 and sorted_students[index-1].score != student.score:
            current_rank = index + 1  # ← Fix: rank = people_ranked_so_far + 1
        student.rank = current_rank
    
    return sorted_students
```

**Issues with patch:**
- Doesn't address idempotency, observability, testability
- Doesn't prepare for distributed scenarios (webhooks, events)
- Leaves fragile test structure
- No audit trail

---

## 4. New System Design: Greenfield Replacement (v2)

### 4.1 Architecture Vision

**Shift from:** Stateless function with implicit state  
**Shift to:** Event-driven, idempotent service with transparent state machine

```
┌────────────────────────────────────────────────────────────────┐
│                   Ranking Service v2                           │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ REST API Layer (RankRequest)                             │  │
│  │  POST /api/v2/rank                                       │  │
│  │  GET /api/v2/rank/{request_id}                           │  │
│  │  GET /api/v2/rank/{request_id}/status                    │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Idempotency Layer                                        │  │
│  │  - Check for duplicate request_id                        │  │
│  │  - Return cached result if exists                        │  │
│  │  - Validate request structure                            │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ State Machine Orchestrator                               │  │
│  │  PENDING → PROCESSING → SUCCESS/FAILURE                  │  │
│  │  - Validate inputs                                       │  │
│  │  - Emit state events                                     │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Ranking Engine (Fixed Algorithm)                         │  │
│  │  - Competition ranking (same score = same rank)          │  │
│  │  - Deterministic sort                                    │  │
│  │  - Parallel batch processing                             │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Structured Logging & Observability                       │  │
│  │  - Request ID in every log                               │  │
│  │  - State snapshots (pre/post ranking)                    │  │
│  │  - Metrics: latency, tie detection, errors               │  │
│  └─────────────────────────────────────────────────────────┘  │
│                           ↓                                     │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ Storage & Audit (Outbox Pattern)                         │  │
│  │  - Transactional writes (request + result + events)      │  │
│  │  - Event log for reconciliation                          │  │
│  └─────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────┘
```

### 4.2 State Machine: Unified Lifecycle

```
┌──────────────┐
│   INIT       │
│ (new request)│
└──────┬───────┘
       │
       ├─────────────────────────────────────────┐
       │ Validate request structure & scores    │
       v                                         ↓
┌──────────────┐                        ┌────────────────┐
│   PENDING    │ ────────(timeout)────→ │ FAILED         │
│ (accepted,   │                        │ (validation or  │
│  awaiting)   │                        │  timeout)      │
└──────┬───────┘                        └────────────────┘
       │
       │ Process request (sort, rank, validate output)
       ↓
┌──────────────┐ ─────(exception)────→ ┌────────────────┐
│ PROCESSING   │                       │ FAILED         │
│ (calculating)│                       │ (rank bug,     │
│              │                       │  data error)   │
└──────┬───────┘                       └────────────────┘
       │
       │ Persist results (transactional outbox)
       ↓
┌──────────────┐
│   SUCCESS    │
│ (complete,   │
│  persisted)  │
└──────────────┘
```

**State Transitions & Guarantees:**

| From | To | Condition | Guarantee |
|------|----|------------|-----------|
| INIT | PENDING | Structural validation OK | Idempotency key recorded |
| PENDING | PROCESSING | Timeout not exceeded | Idempotency check again |
| PROCESSING | SUCCESS | Rank calculation OK + persisted | Audit log written |
| PROCESSING | FAILED | Rank error or DB error | Error code + stack trace logged |
| PENDING/PROCESSING | FAILED | Timeout (default 30s) | Graceful degradation; client can retry |

**Crash Points & Recovery:**

1. **After PENDING, before PROCESSING:** Restart PROCESSING (safe; same request_id)
2. **During PROCESSING (rank calc fails):** → FAILED state; log stack trace; can retry
3. **After SUCCESS persisted, before response sent:** Return cached result from outbox
4. **Network failure after client response:** Idempotency ensures no duplicate ranks

### 4.3 API Contract (v2)

#### Request Schema

```json
{
  "request_id": "uuid",
  "students": [
    {
      "name": "string (1-255 chars)",
      "score": "number (0-100, inclusive)",
      "metadata": {
        "id": "optional string",
        "class": "optional string"
      }
    }
  ],
  "ranking_strategy": "enum: COMPETITION (default) | DENSE | ORDINAL",
  "timeout_ms": "integer (default 30000)",
  "idempotency_key": "uuid (same as request_id or explicit override)"
}
```

**Field Constraints:**

| Field | Type | Constraint | Notes |
|-------|------|-----------|-------|
| request_id | UUID | Must be unique; 36-char string | Client-generated or server-issued |
| students[].name | String | 1-255 chars; UTF-8 | No leading/trailing whitespace |
| students[].score | Number | 0 ≤ score ≤ 100 | Can be int or float (e.g., 95.5) |
| students | Array | Min 1, Max 10M items | Batching for large cohorts |
| ranking_strategy | Enum | COMPETITION \| DENSE \| ORDINAL | Future extensibility |
| timeout_ms | Integer | 1000 ≤ timeout ≤ 300000 | Default 30000; prevents hangs |
| idempotency_key | UUID | Must match request_id | Explicit de-dup override |

#### Response Schema (Success)

```json
{
  "request_id": "uuid",
  "status": "SUCCESS",
  "timestamp_ms": "number",
  "results": [
    {
      "name": "string",
      "score": "number",
      "rank": "integer",
      "metadata": {
        "id": "string (echoed from request)",
        "class": "string (echoed from request)"
      }
    }
  ],
  "statistics": {
    "total_students": 7,
    "unique_scores": 4,
    "tie_groups": 3,
    "processing_ms": 5,
    "rank_variance": 0.86
  }
}
```

#### Response Schema (Error)

```json
{
  "request_id": "uuid",
  "status": "FAILED",
  "error_code": "string (VALIDATION_ERROR | TIMEOUT | INTERNAL_ERROR)",
  "error_message": "string",
  "validation_errors": [
    {
      "field": "students[0].score",
      "value": 150,
      "constraint": "0 ≤ score ≤ 100",
      "message": "Score exceeds maximum"
    }
  ],
  "timestamp_ms": "number"
}
```

### 4.4 Ranking Algorithm (Fixed)

```python
# Pseudocode for COMPETITION ranking
def rank_students_v2(students: List[StudentInput]) -> List[StudentOutput]:
    """
    Standard competition ranking:
    - Same score → same rank
    - Next different score → rank = (count_ranked_so_far + 1)
    
    Idempotency: Deterministic on (name, score) only; ignores order.
    """
    
    # Step 1: Validate all scores [0, 100]
    for student in students:
        if not (0 <= student.score <= 100):
            raise ValidationError(f"{student.name}: score {student.score} out of range")
    
    # Step 2: Sort deterministically (score desc, then name asc for ties)
    sorted_students = sorted(
        students,
        key=lambda s: (-s.score, s.name)  # Stable sort by score, then name
    )
    
    # Step 3: Assign ranks (competition rules)
    ranked = []
    current_rank = 1
    prev_score = None
    
    for idx, student in enumerate(sorted_students):
        # If score changed, update rank to reflect all people ranked so far
        if prev_score is not None and student.score != prev_score:
            current_rank = idx + 1
        
        ranked.append(StudentOutput(
            name=student.name,
            score=student.score,
            rank=current_rank
        ))
        prev_score = student.score
    
    # Step 4: Return in original stable sort order (idempotent)
    return ranked
```

**Example Execution:**

```
Input:  [Alice(95), Bob(95), Charlie(90), David(90), Eve(85)]

Step 2: Sorted by (-score, name)
        [(Alice, 95), (Bob, 95), (Charlie, 90), (David, 90), (Eve, 85)]

Step 3: Loop
        idx=0: current_rank=1, prev_score=None      → Alice(95, rank=1), prev=95
        idx=1: 95==95, no change                     → Bob(95, rank=1), prev=95
        idx=2: 90≠95, current_rank=2+1=3, NO!       → ERROR! Should be 2+1=3? 
                                                      WAIT: idx=2, so rank = 2+1 = 3. 
                                                      That's WRONG for tied group of 2.
        
CORRECTION: rank should be idx + 1, not the count of UNIQUE scores.

        idx=0: score 95, idx=0 → rank = 0+1 = 1 ✓
        idx=1: score 95, same → rank = 1 (no change) ✓
        idx=2: score 90, diff → rank = 2+1 = 3? NO WAIT...
               
At idx=2, we have 2 people ranked (idx 0 and 1).
Next person should be rank = 2 + 1 = 3.
But we have TWO with score 90!

So:    idx=2: score 90, diff from 95 → rank = idx+1 = 3 ✓
        idx=3: score 90, same → rank = 3 (no change) ✓
        idx=4: score 85, diff from 90 → rank = idx+1 = 5 ✓

Output: [(Alice, 95, 1), (Bob, 95, 1), (Charlie, 90, 3), (David, 90, 3), (Eve, 85, 5)]
```

### 4.5 Idempotency & Retry Strategy

**Idempotency Key:** Unique `request_id` (UUID v4 or client-provided)

**Storage:**
```
RankRequest:
  request_id (PK)
  client_id
  created_at
  updated_at
  input_hash (SHA256 of students list)
  state (PENDING/PROCESSING/SUCCESS/FAILED)
  result_cached (JSON if SUCCESS)
  error (if FAILED)
  
RankRequestLog:
  request_id (FK)
  event_type (CREATED, VALIDATING, PROCESSING, SUCCESS, FAILED)
  timestamp
  message
  stack_trace (if error)
```

**Retry Logic:**

```
Client Request (request_id=abc123, students=[...])
  ↓
Server: Check if request_id already in RankRequest
  ├─ YES, state=SUCCESS → Return cached result ✅ Idempotent
  ├─ YES, state=FAILED → Check if retriable (not VALIDATION_ERROR)
  │                       → Restart PROCESSING with same request_id
  └─ NO → Create new RankRequest with state=PENDING
           ↓
           [Validate inputs]
           ↓ (Fail? → state=FAILED, return error; idempotency still holds)
           ↓ (Pass?)
           ↓
           Update state=PROCESSING
           [Calculate rankings]
           ↓ (Error? → state=FAILED, error_code, stack_trace; log to audit)
           ↓ (Success?)
           ↓
           Update state=SUCCESS, persist result to cache
           Emit RankSuccessEvent (for webhooks, downstream)
           ↓
           Return results to client
```

### 4.6 Compensation & Saga (Distributed Scenario)

If ranking is part of a larger workflow (e.g., "Publish Results" saga):

```
┌────────────────────────────────────────────────────┐
│  Publish-Results Saga                              │
│  (Orchestrator Pattern)                            │
├────────────────────────────────────────────────────┤
│                                                    │
│  Step 1: Rank students                             │
│  ├─ Call RankingService.rank(request)              │
│  ├─ On Success → step 2                            │
│  └─ On Failure → Compensation: RollbackRankings()  │
│                                                    │
│  Step 2: Notify students                           │
│  ├─ Call NotificationService.send_emails(...)      │
│  ├─ On Success → step 3                            │
│  └─ On Failure → Compensation: Undo notifications  │
│                                                    │
│  Step 3: Update leaderboard cache                  │
│  ├─ Call CacheService.set_leaderboard(...)         │
│  ├─ On Success → SAGA_COMPLETE                     │
│  └─ On Failure → Compensation: Clear cache         │
│                                                    │
│  Compensation/Rollback Actions:                    │
│  ├─ RollbackRankings: Flag request as rolled back  │
│  ├─ Undo notifications: Mark emails as cancelled   │
│  └─ Clear cache: Delete leaderboard entry          │
│                                                    │
│  Reconciliation:                                   │
│  ├─ Check for orphaned requests (rolled back)      │
│  ├─ Re-publish for requests that failed email      │
│  └─ Verify cache matches DB state                  │
│                                                    │
└────────────────────────────────────────────────────┘
```

**Transactional Outbox Pattern (Ensures Event Reliability):**

```python
def rank_and_emit(request: RankRequest) -> RankResponse:
    """
    All-or-nothing: rank + event emission transactional.
    """
    with db.transaction():
        # 1. Persist RankRequest with state=PROCESSING
        db.insert("RankRequests", request)
        
        # 2. Calculate rankings
        result = rank_students_v2(request.students)
        
        # 3. Insert success result
        db.insert("RankResults", {
            "request_id": request.request_id,
            "result": result,
            "state": "SUCCESS"
        })
        
        # 4. Insert events to outbox (not yet published)
        db.insert("OutboxEvents", {
            "event_id": uuid4(),
            "request_id": request.request_id,
            "event_type": "RankSuccessEvent",
            "payload": result,
            "published": False
        })
        
        # Commit all 4 inserts atomically ← Guarantee: no orphaned events
    
    # 5. (Outside txn) Publish events from outbox
    #    If process dies, background job will retry unpublished events
    for event in db.query("OutboxEvents WHERE published=False"):
        try:
            event_bus.publish(event)
            db.update("OutboxEvents", event_id, published=True)
        except Exception as e:
            # Retry later; don't fail the response
            log.warning(f"Event publish failed: {event_id}, will retry", e)
    
    return RankResponse(
        request_id=request.request_id,
        status="SUCCESS",
        results=result
    )
```

### 4.7 Observability & Structured Logging

**Log Schema:**

```json
{
  "timestamp": "2025-12-15T14:23:45.123Z",
  "request_id": "abc-123-def",  // Unique identifier for this ranking request
  "level": "INFO|WARN|ERROR",
  "event": "RankingStarted|RankingCompleted|ValidationError",
  "service": "ranking-service",
  "version": "v2.1.0",
  
  "context": {
    "client_id": "school-district-42",
    "batch_size": 7,
    "strategy": "COMPETITION"
  },
  
  "metrics": {
    "processing_ms": 5,
    "input_validation_ms": 1,
    "sort_ms": 2,
    "rank_assign_ms": 1,
    "persist_ms": 1,
    "total_students": 7,
    "unique_scores": 4,
    "tie_groups": [
      {"score": 95, "count": 2, "rank": 1},
      {"score": 90, "count": 1, "rank": 3},
      {"score": 85, "count": 3, "rank": 4},
      {"score": 80, "count": 1, "rank": 7}
    ]
  },
  
  "state": {
    "before": {
      "request_state": "PENDING",
      "student_count": 7
    },
    "after": {
      "request_state": "SUCCESS",
      "result_hash": "sha256:abc123..."
    }
  },
  
  "error": null,  // If level=ERROR
  
  "masked": {
    "// Note": "Sensitive fields like full student names are hashed"
  }
}
```

**Key Assertions:**
- Every operation includes `request_id` for traceability
- Tie groups logged explicitly (for fairness audit)
- Pre/post state snapshots (for reconciliation)
- Processing time broken down by phase (for SLA monitoring)
- Errors include stack trace + remediation hint

---

## 5. Testing & Acceptance

### 5.1 Integration Test Cases (5+ Scenarios)

#### Test 1: Basic No-Tie Ranking

**Target Issue:** Regression; ensure single-score ranking works  
**Preconditions:** Empty system  
**Data:**
```json
{
  "request_id": "test-001",
  "students": [
    {"name": "Alice", "score": 90},
    {"name": "Bob", "score": 80},
    {"name": "Charlie", "score": 70}
  ]
}
```

**Steps:**
1. POST /api/v2/rank with above payload
2. Verify response status = SUCCESS
3. Extract results; sort by rank

**Expected Outcome:**
```json
[
  {"name": "Alice", "rank": 1},
  {"name": "Bob", "rank": 2},
  {"name": "Charlie", "rank": 3}
]
```

**Observability Assertions:**
- Log contains event="RankingStarted" and event="RankingCompleted"
- Metrics show `tie_groups: []` (no ties)
- Processing time < 50ms
- state.after.request_state = "SUCCESS"

---

#### Test 2: Tied-First-Place Ranking (CRITICAL)

**Target Issue:** Primary bug; tied scores get same rank  
**Preconditions:** Empty system  
**Data:**
```json
{
  "request_id": "test-002",
  "students": [
    {"name": "Alice", "score": 95},
    {"name": "Bob", "score": 95},
    {"name": "Charlie", "score": 90}
  ]
}
```

**Steps:**
1. POST /api/v2/rank
2. Verify response status = SUCCESS
3. Assert Alice.rank == Bob.rank (both should be 1)
4. Assert Charlie.rank == 2 (not 3!)

**Expected Outcome:**
```json
[
  {"name": "Alice", "rank": 1},
  {"name": "Bob", "rank": 1},
  {"name": "Charlie", "rank": 2}
]
```

**Observability Assertions:**
- Metrics show `tie_groups: [{"score": 95, "count": 2, "rank": 1}]`
- Log indicates detected 1 tie group
- Result differs from legacy (regression proof)

---

#### Test 3: Multiple Tie Groups (Complex)

**Target Issue:** Handling consecutive groups of ties  
**Preconditions:** Empty system  
**Data:** 6 students, 3 distinct scores
```json
{
  "request_id": "test-003",
  "students": [
    {"name": "A", "score": 95},
    {"name": "B", "score": 95},
    {"name": "C", "score": 85},
    {"name": "D", "score": 85},
    {"name": "E", "score": 85},
    {"name": "F", "score": 80}
  ]
}
```

**Expected Outcome:**
```json
[
  {"name": "A", "rank": 1},
  {"name": "B", "rank": 1},
  {"name": "C", "rank": 3},
  {"name": "D", "rank": 3},
  {"name": "E", "rank": 3},
  {"name": "F", "rank": 6}
]
```

**Observability Assertions:**
- Metrics: `tie_groups: [{"score": 95, "count": 2}, {"score": 85, "count": 3}]`
- Each tie group correctly shows rank = prior_count + 1

---

#### Test 4: Idempotency (Same Request Twice)

**Target Issue:** Duplicate requests return cached result; no re-ranking  
**Preconditions:** Empty system  
**Data:** 3 students  

**Steps:**
1. POST /api/v2/rank with request_id="idem-001" and students=[Alice(95), Bob(90)]
2. Store result R1 (rank order, processing_ms, etc.)
3. POST /api/v2/rank again with same request_id and students
4. Store result R2
5. Compare R1 == R2

**Expected Outcome:**
- R2.results == R1.results (identical ranking)
- R2.statistics.processing_ms ~ 0 (cached; no re-calculation)
- Response includes `"cached": true` flag (if applicable)

**Observability Assertions:**
- First log shows event="RankingStarted" → "RankingCompleted" (2 events)
- Second log shows event="RankingCached" only (1 event; no re-processing)

---

#### Test 5: Validation Error (Invalid Score)

**Target Issue:** Boundary validation; catch invalid scores before ranking  
**Preconditions:** Empty system  
**Data:**
```json
{
  "request_id": "test-005",
  "students": [
    {"name": "Alice", "score": 150}  // Invalid: > 100
  ]
}
```

**Steps:**
1. POST /api/v2/rank
2. Verify response status = FAILED

**Expected Outcome:**
```json
{
  "status": "FAILED",
  "error_code": "VALIDATION_ERROR",
  "validation_errors": [
    {
      "field": "students[0].score",
      "value": 150,
      "constraint": "0 ≤ score ≤ 100",
      "message": "Score exceeds maximum"
    }
  ]
}
```

**Observability Assertions:**
- No ranking output (null or empty)
- Log shows event="ValidationError"
- state.before.request_state = "PENDING"; state.after.request_state = "FAILED"
- No OutboxEvents created (errors don't trigger cascades)

---

#### Test 6: Timeout Handling (Future Scenario)

**Target Issue:** Long-running ranking (huge batch) doesn't hang  
**Preconditions:** Slow ranking endpoint configured  
**Data:** 100K students  

**Steps:**
1. POST /api/v2/rank with timeout_ms=1000 and 100K students
2. Wait 1.1 seconds
3. Verify response received

**Expected Outcome:**
```json
{
  "status": "FAILED",
  "error_code": "TIMEOUT",
  "error_message": "Ranking request exceeded 1000ms timeout"
}
```

**Observability Assertions:**
- Log shows event="TimeoutExceeded" before request_state became SUCCESS
- Client can retry with timeout_ms=30000 for full processing

---

#### Test 7: Concurrent Requests (Idempotency + Isolation)

**Target Issue:** Multiple ranking requests don't interfere  
**Preconditions:** Empty system  
**Data:** 2 independent requests

```
Thread A: request_id="conc-A", students=[Alice(95), Bob(90)]
Thread B: request_id="conc-B", students=[Charlie(85), David(80)]
```

**Steps:**
1. Start both requests concurrently
2. Wait for both responses
3. Verify results are independent

**Expected Outcome:**
- Response A includes Alice & Bob rankings only
- Response B includes Charlie & David rankings only
- No cross-contamination

**Observability Assertions:**
- Log entries for both request_ids interleaved
- Each request_id has complete trace (START → END)
- Metrics show 2 separate ranking operations

---

### 5.2 Acceptance Criteria

#### Functional Acceptance

| Criterion | Metric | Target |
|-----------|--------|--------|
| Correct ranking with ties | % of tests passing (tie scenarios) | 100% |
| Idempotency | Same request_id returns same result | Always |
| Validation | Invalid scores rejected | Always |
| Error handling | Errors logged with context | 100% of failures |

#### Performance Acceptance

| Criterion | Metric | Target (SLO) |
|-----------|--------|--------------|
| Small batch (n=10) | p50 latency | <10ms |
| Small batch (n=10) | p95 latency | <50ms |
| Medium batch (n=1K) | p50 latency | <100ms |
| Medium batch (n=1K) | p95 latency | <500ms |
| Large batch (n=100K) | p50 latency | <5s |
| Memory footprint | Peak RAM (n=100K) | <500MB |

#### Reliability Acceptance

| Criterion | Metric | Target |
|-----------|--------|--------|
| Error recovery | Retriable errors can be retried | Always |
| Idempotency | Duplicate requests detected | Always |
| Audit trail | All requests logged with trace | 100% |

#### Observability Acceptance

| Criterion | Metric | Target |
|-----------|--------|--------|
| Request tracing | request_id in all logs | 100% |
| Tie detection | Tie groups reported in metrics | 100% |
| Error details | Stack traces for failures | 100% of errors |
| Fairness audit | Pre/post state snapshots | 100% of requests |

---

## 6. Migration & Parallel Run Strategy

### 6.1 Read/Write Cutover Plan

**Phase 1: Shadow Mode (1-2 weeks)**
- v2 runs in parallel with v1 on all incoming requests
- v2 results logged but not returned; used only for comparison
- Metrics collected: latency, correctness diff, error rate
- No impact to users

```
Client Request
  ↓
  ├─→ v1 (legacy) → Return to client
  └─→ v2 (greenfield) → Log only; compare with v1
```

**Phase 2: Validation (1 week)**
- QA team reviews logs for correctness diff
- If v2 results differ from v1: diagnose (e.g., rare tie handling)
- If v2 latency worse: optimize (caching, indexing, parallelization)
- Feedback loop to fix issues before cutover

**Phase 3: Canary Rollout (1-2 weeks)**
- v2 returned to 5% of users (canary)
- Monitor: error rate, latency, user complaints
- Metrics threshold: <0.1% error increase, p95 latency ≤ v1 p95 + 10%
- If pass: increase to 25%, then 50%, then 100%

```
v1 ↑95%
    Client → Router
v2 ↑5%
```

**Phase 4: Full Cutover**
- v2 receives 100% traffic
- v1 kept in standby for 30 days (rollback capability)
- Ongoing monitoring: maintain SLOs

### 6.2 Backfill Strategy

If v2 has different ranking output for historical requests:

```python
def backfill_historical_rankings():
    """Re-rank all students using v2 algorithm."""
    
    # Step 1: Fetch all completed ranking requests from v1
    legacy_requests = db.query("""
        SELECT request_id, students, result 
        FROM RankRequests 
        WHERE system='v1' AND state='SUCCESS'
    """)
    
    for legacy_req in legacy_requests:
        # Step 2: Re-rank using v2
        v2_result = rank_students_v2(legacy_req.students)
        
        # Step 3: Compare with legacy result
        if v2_result != legacy_req.result:
            # Step 4: Log diff (for fairness audit)
            db.insert("RankingDiffs", {
                "request_id": legacy_req.request_id,
                "v1_result": legacy_req.result,
                "v2_result": v2_result,
                "diff_count": count_differences(v1, v2),
                "audit_status": "PENDING_REVIEW"
            })
            
            # Step 5: Insert v2 result (don't overwrite v1 yet)
            db.insert("RankingResultsV2", {
                "request_id": legacy_req.request_id,
                "result": v2_result,
                "backfill_date": now()
            })
        else:
            # No diff; mark as validated
            db.update("RankingDiffs", request_id, audit_status="VALIDATED")
    
    # Step 6: Audit team reviews diffs; approve cutover
    return db.query("SELECT * FROM RankingDiffs WHERE audit_status='PENDING_REVIEW'")
```

### 6.3 Rollback Path

**If v2 has critical issue:**

1. **Immediate:** Route all traffic back to v1
2. **Triage:** Identify root cause
3. **Fix:** Hotfix v2; re-run shadow tests
4. **Re-Canary:** Start Phase 3 from 5% again
5. **Rollback Diffs:** If v2 results were returned and are incorrect:
   - Mark affected requests as "ranked_by_v2_needs_review"
   - Notify users of affected students (e.g., scholarship appeals)
   - Provide reconciliation report (who benefited/lost)

---

## 7. Deliverables Structure

```
C:\BugBash\workSpace3\Claude-haiku-4.5\
├── ARCHITECTURE_ANALYSIS.md           # This document
├── IMPLEMENTATION_GUIDE.md             # Step-by-step v2 build
├── ranking-service-v2/
│   ├── src/
│   │   ├── __init__.py
│   │   ├── models.py                  # StudentInput, RankRequest, RankResponse
│   │   ├── ranking_engine.py           # Core algorithm (rank_students_v2)
│   │   ├── api_handler.py              # REST endpoints
│   │   ├── idempotency.py              # Request dedup, caching
│   │   ├── state_machine.py            # PENDING→PROCESSING→SUCCESS/FAILED
│   │   ├── observability.py            # Structured logging, metrics
│   │   ├── storage.py                  # DB (in-memory or SQL)
│   │   └── outbox.py                   # Transactional event publishing
│   ├── mocks/
│   │   ├── mock_api_server.py          # /api/v2/rank mock (immediate/pending/delayed)
│   │   └── test_fixtures.py
│   ├── data/
│   │   ├── test_data.json              # Canonical test cases (≥5)
│   │   ├── expected_postchange.json    # Expected v2 output
│   │   └── students_large.json         # 100K records for load testing
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_ranking_engine.py      # Unit tests
│   │   ├── test_api.py                 # Integration tests
│   │   ├── test_idempotency.py         # Idempotency tests
│   │   ├── test_state_machine.py       # State transitions
│   │   └── test_observability.py       # Logging, metrics
│   ├── logs/
│   │   ├── test_output_v1.log          # Legacy system logs
│   │   └── test_output_v2.log          # v2 system logs
│   ├── results/
│   │   ├── results_v1.json             # Legacy test results
│   │   ├── results_v2.json             # v2 test results
│   │   ├── aggregated_metrics.json     # Performance comparison
│   │   └── diffs.json                  # Correctness diffs
│   ├── requirements.txt
│   ├── setup.sh                        # Environment setup
│   ├── run_tests.sh                    # Run all integration tests
│   ├── run_mock_api.sh                 # Start mock server
│   ├── run_comparison.sh               # Run v1 vs v2 comparison
│   └── README.md                       # How to build, test, deploy
├── Shared/
│   ├── test_data.json                  # Master canonical cases (≥5)
│   ├── run_all.sh                      # Master orchestration script
│   └── compare_report.md               # Final correctness/perf report
└── ROLLOUT_STRATEGY.md                 # Cutover & rollback procedures
```

---

## 8. Conclusion & Recommendations

### Root Cause Summary

The legacy system's ranking bug stems from **using array indices as ranks directly, without comparing scores or tracking people ranked**. This violates standard competition ranking semantics.

### Greenfield Benefits

| Aspect | Legacy v1 | Greenfield v2 |
|--------|-----------|---------------|
| **Algorithm** | Buggy (off-by-one with ties) | Fixed (standard competition ranking) |
| **Idempotency** | No request tracking | Explicit request_id + dedup + caching |
| **State Machine** | Implicit | Explicit (PENDING → PROCESSING → SUCCESS/FAILED) |
| **Observability** | Minimal | Structured logging + metrics + audit trail |
| **Error Handling** | Limited (validation only) | Rich (timeouts, retries, Saga compensation) |
| **Testability** | Brittle (hardcoded paths) | Robust (mocks, fixtures, integration tests) |
| **Extensibility** | Hard (monolithic) | Easy (strategy pattern, plugins) |

### Recommended Next Steps

1. **Immediate (This Week)**
   - [ ] Implement v2 core algorithm + unit tests
   - [ ] Deploy mock API server for client integration testing
   - [ ] Publish API contract (OpenAPI/Swagger)

2. **Short Term (Next 2 Weeks)**
   - [ ] Integration tests for all 7 scenarios + acceptance criteria
   - [ ] Shadow run (v1 live, v2 logging only)
   - [ ] Performance baseline & SLA validation

3. **Medium Term (Weeks 3-4)**
   - [ ] Canary rollout (5% → 100%)
   - [ ] Fairness audit (tie groups, scholarship impacts)
   - [ ] Historical backfill (if needed)

4. **Long Term (Post-Cutover)**
   - [ ] Maintain v1 in standby for 30 days
   - [ ] Monitor v2 SLOs (latency, errors, idempotency)
   - [ ] Iterate on observability (add dashboards, alerts)

---

**Appendix A: Test Case JSON Examples** [See section 5.1 for full details]

**Appendix B: API Specification** [See section 4.3 for full contract]

**Appendix C: State Machine Transitions** [See section 4.2 for detailed FSM]

---

*End of Architecture Analysis & Greenfield Design*
