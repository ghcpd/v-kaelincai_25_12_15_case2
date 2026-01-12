# Shared Resources

## How to Run/Interpret

1. Run `run_all.sh` to execute tests for both systems
2. Check `compare_report.md` for differences
3. Review `results/` for detailed metrics

## Limits

- Greenfield assumes single instance, no distributed concurrency
- Legacy has ranking bug

## Rollout Strategy

Blue-green deployment: Run both, cutover after validation.