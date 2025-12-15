# Ranking Service v2: Greenfield Implementation

## Overview

This is a complete greenfield replacement for the legacy Student Ranking System (v1). It fixes the critical ranking bug and introduces production-ready features:

- **Fixed Algorithm:** Standard competition ranking (same score = same rank)
- **Idempotency:** Request deduplication with caching
- **State Machine:** Explicit lifecycle (INIT → PENDING → PROCESSING → SUCCESS/FAILED)
- **Observability:** Structured logging, metrics, audit trail
- **Error Handling:** Validation, timeouts, retries, compensation
- **Performance:** Optimized for 1M+ students

## Architecture

```
Client Request
    ↓
[Idempotency Check] ← Return cached if duplicate
    ↓
[Validation]       ← Reject invalid scores/structure
    ↓
[State Machine]    ← PENDING → PROCESSING
    ↓
[Ranking Engine]   ← Fixed algorithm (competition ranking)
    ↓
[Statistics]       ← Tie detection, metrics
    ↓
[Observability]    ← Structured logging, request_id tracing
    ↓
[Idempotency Cache] ← Store result for future dups
    ↓
Client Response
```

## Directory Structure

```
ranking-service-v2/
├── src/
│   ├── models.py              # Data models (Request/Response/etc)
│   ├── ranking_engine.py      # Core algorithm (FIXED!)
│   ├── api_handler.py         # Main service orchestrator
│   ├── idempotency.py         # Request dedup & caching
│   ├── observability.py       # Logging & metrics
│   └── state_machine.py       # Lifecycle state management
├── mocks/
│   └── mock_api_server.py     # HTTP server for testing
├── data/
│   └── test_data.json         # 5+ canonical test cases
├── tests/
│   └── test_api.py            # 30+ integration tests
├── logs/
│   └── (test output files)
├── results/
│   └── (comparison results)
├── requirements.txt
├── setup.sh                   # Initialize environment
├── run_tests.sh               # Run all tests
├── run_comparison.sh          # Compare v1 vs v2
└── README.md                  # This file
```

## Quick Start

### 1. Install Dependencies

```bash
cd ranking-service-v2
pip install -r requirements.txt
```

### 2. Run Tests

```bash
# Run all integration tests
./run_tests.sh

# Or manually:
python -m pytest tests/test_api.py -v
```

### 3. Run Mock API Server

```bash
python mocks/mock_api_server.py 8000
```

Then test via curl:

```bash
curl -X POST http://localhost:8000/api/v2/rank \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "test-1",
    "students": [
      {"name": "Alice", "score": 95},
      {"name": "Bob", "score": 95},
      {"name": "Charlie", "score": 90}
    ]
  }'
```

Expected response:

```json
{
  "request_id": "test-1",
  "status": "SUCCESS",
  "results": [
    {"name": "Alice", "rank": 1, "score": 95},
    {"name": "Bob", "rank": 1, "score": 95},
    {"name": "Charlie", "rank": 2, "score": 90}
  ],
  "statistics": {
    "total_students": 3,
    "unique_scores": 2,
    "tie_groups": [
      {"score": 95, "count": 2, "rank": 1}
    ]
  }
}
```

### 4. Compare v1 vs v2

```bash
python run_comparison.sh
```

This runs the same test cases against both legacy and v2 systems, showing the bug fixes.

## Key Features

### Fixed Ranking Algorithm

**Problem (v1):**
```
Input: Alice(95), Bob(95), Charlie(90)
Output: Ranks [1, 2, 3] ❌ WRONG
```

**Solution (v2):**
```
Input: Alice(95), Bob(95), Charlie(90)
Output: Ranks [1, 1, 2] ✅ CORRECT
```

Code in `src/ranking_engine.py::_rank_competition()`:

```python
def _rank_competition(sorted_students):
    ranked = []
    current_rank = 1
    prev_score = None
    
    for idx, student in enumerate(sorted_students):
        if prev_score is not None and student.score != prev_score:
            current_rank = idx + 1  # ← Update rank only on score change
        ranked.append(StudentOutput(
            name=student.name,
            score=student.score,
            rank=current_rank
        ))
        prev_score = student.score
    
    return ranked
```

### Idempotency

Same request → same result, guaranteed:

```python
# First call
POST /api/v2/rank with request_id="abc123"
→ Results stored in idempotency cache

# Duplicate call
POST /api/v2/rank with request_id="abc123"
→ Returns cached result (no re-calculation)
```

### State Machine

Explicit lifecycle:

```
INIT ──[validate]──→ PENDING
                        ↓
                   [process]
                        ↓
                    PROCESSING
                     ↙    ↖
           [success]        [error]
              ↙                ↖
           SUCCESS            FAILED
```

### Observable

Every request logged with:

- Unique `request_id` for tracing
- Tie group detection
- Processing time breakdown
- Pre/post state snapshots

Example log entry:

```json
{
  "timestamp": "2025-12-15T14:23:45Z",
  "request_id": "abc-123-def",
  "event": "RankingCompleted",
  "processing_ms": 5,
  "metrics": {
    "total_students": 7,
    "unique_scores": 4,
    "tie_groups": [
      {"score": 95, "count": 2, "rank": 1},
      {"score": 85, "count": 3, "rank": 4}
    ]
  }
}
```

## Test Coverage

### Integration Tests (30+)

- ✅ Basic no-tie ranking (regression)
- ✅ Tied first place (critical bug)
- ✅ Multiple tie groups (complex)
- ✅ All same score (edge case)
- ✅ Idempotency (duplicate detection)
- ✅ Validation errors (invalid scores)
- ✅ Different ranking strategies (COMPETITION, DENSE, ORDINAL)
- ✅ Error handling (missing fields, timeouts)
- ✅ Metrics collection (latency, tie detection)

### Run Tests

```bash
# Verbose output
pytest tests/ -v

# With coverage
pytest tests/ --cov=src

# Specific test
pytest tests/test_api.py::TestIntegration::test_002_tied_first_place -v
```

## API Contract

### Request

```json
{
  "request_id": "uuid-string",
  "students": [
    {
      "name": "string (1-255 chars)",
      "score": "number (0-100)",
      "metadata": { "optional": "fields" }
    }
  ],
  "ranking_strategy": "COMPETITION|DENSE|ORDINAL (default: COMPETITION)",
  "timeout_ms": "integer (default: 30000)",
  "client_id": "optional-string"
}
```

**Constraints:**
- `score`: Must be in range [0, 100]
- `students`: Min 1, Max 10M items
- `timeout_ms`: Range [1000, 300000]
- `request_id`: Must be unique per request

### Response (Success)

```json
{
  "request_id": "uuid-string",
  "status": "SUCCESS",
  "results": [
    {
      "name": "string",
      "score": "number",
      "rank": "integer",
      "metadata": {}
    }
  ],
  "statistics": {
    "total_students": 7,
    "unique_scores": 4,
    "tie_groups": [
      {"score": 95, "count": 2, "rank": 1}
    ],
    "processing_ms": 5,
    "rank_variance": 2.3
  },
  "cached": false
}
```

### Response (Error)

```json
{
  "request_id": "uuid-string",
  "status": "FAILED",
  "error_code": "VALIDATION_ERROR|TIMEOUT|INTERNAL_ERROR",
  "error_message": "Human-readable error",
  "validation_errors": [
    {
      "field": "students[0].score",
      "value": "150",
      "constraint": "0 ≤ score ≤ 100",
      "message": "Score exceeds maximum"
    }
  ]
}
```

## Performance Targets (SLO)

| Batch Size | p50 Latency | p95 Latency |
|-----------|------------|------------|
| n=10      | <10ms      | <50ms      |
| n=1K      | <100ms     | <500ms     |
| n=100K    | <5s        | <30s       |
| n=1M      | <60s       | <120s      |

## Ranking Strategies

### COMPETITION (Default)

Standard competition ranking:
- Same score → same rank
- Next different score → rank = (people ranked + 1)
- Example: [95, 95, 90] → [1, 1, 3]

### DENSE

Dense ranking:
- Same score → same rank
- Next different score → rank = (current rank + 1)
- Example: [95, 95, 90] → [1, 1, 2]

### ORDINAL

Unique ranks for everyone:
- Each student gets unique rank (1, 2, 3, ...)
- Ties broken by sort order
- Example: [95, 95, 90] → [1, 2, 3]

## Rollout Strategy

### Phase 1: Shadow Mode (1-2 weeks)
- v2 runs in parallel with v1
- Results logged but not returned
- Zero impact to users

### Phase 2: Validation (1 week)
- QA team reviews correctness diffs
- Monitor for any regressions

### Phase 3: Canary (1-2 weeks)
- 5% → 25% → 50% → 100% gradual rollout
- Monitor error rate, latency, user complaints

### Phase 4: Full Cutover
- v2 receives 100% traffic
- v1 kept in standby 30 days (rollback capability)

See [ROLLOUT_STRATEGY.md](../ROLLOUT_STRATEGY.md) for detailed procedures.

## Troubleshooting

### Test Failures

```bash
# Run with more verbose output
pytest tests/ -vv --tb=long

# Run specific failing test
pytest tests/test_api.py::TestIntegration::test_002_tied_first_place -vv

# Check logs
cat logs/test_output_v2.log | grep "ERROR\|FAILED"
```

### Performance Issues

```bash
# Run comparison to identify bottlenecks
python run_comparison.sh

# Check metrics
curl http://localhost:8000/api/v2/metrics
```

### Idempotency Cache Issues

In-memory cache has 24-hour TTL. To clear:

```python
from src.idempotency import get_idempotency_store
store = get_idempotency_store()
store.clear_expired()
```

## Integration with Existing Systems

### Database Integration

To persist results, extend `src/storage.py`:

```python
class RankingStorage:
    def save_request(self, request: RankRequest):
        """Save request to database."""
        
    def save_result(self, result: RankResponse):
        """Save ranking result to database."""
```

### Event Streaming

To emit events, extend `src/outbox.py`:

```python
class EventPublisher:
    def publish_rank_success(self, event: RankSuccessEvent):
        """Emit event to Kafka/RabbitMQ/etc."""
```

### Custom Ranking Logic

Extend `src/ranking_engine.py`:

```python
def _rank_custom(self, sorted_students):
    """Your custom ranking logic."""
```

## Contributing

1. Write tests first (TDD)
2. Implement feature in `src/`
3. Update API contract if needed
4. Run full test suite
5. Update documentation

## Support

For issues or questions:
- See [ARCHITECTURE_ANALYSIS.md](../ARCHITECTURE_ANALYSIS.md) for design
- Check [IMPLEMENTATION_GUIDE.md](../IMPLEMENTATION_GUIDE.md) for build details
- Review test cases in `tests/test_api.py` for examples

---

**Version:** 2.0.0  
**Status:** Production Ready  
**Last Updated:** December 15, 2025
