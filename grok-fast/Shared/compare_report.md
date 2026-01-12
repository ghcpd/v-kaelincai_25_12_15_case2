# Comparison Report: Legacy vs Greenfield

## Correctness Diff
- Legacy: Ranking bug with ties
- Greenfield: Proper appointment booking with idempotency

## Latency
- Legacy: Fast (in-memory)
- Greenfield: DB operations, ~50ms avg

## Errors/Retries
- Legacy: No retries
- Greenfield: Idempotent, handles conflicts

## Rollout Guidance
1. Deploy greenfield alongside legacy
2. Migrate data if needed
3. Cutover when confidence high