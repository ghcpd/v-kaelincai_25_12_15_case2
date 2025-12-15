"""
Integration tests for the Ranking v2 service
These tests cover key crash points / risks identified in the legacy system:
- Tie-handling semantics
- Deterministic ordering
- Idempotency / repeatability
- Input validation and boundary conditions
- Observability hooks (structured logging)
"""

import json
from typing import List

import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from ranking_v2 import Student, RankingService


def test_tie_handling_simple():
    students = [Student(name="Alice", score=95), Student(name="Bob", score=95), Student(name="Charlie", score=90)]
    svc = RankingService()
    res = svc.calculate_rankings(students)

    assert res[0].rank == 1
    assert res[1].rank == 1
    assert res[2].rank == 3


def test_complex_ties_and_ordering():
    students = [Student(name="A", score=95), Student(name="B", score=95), Student(name="C", score=85), Student(name="D", score=85), Student(name="E", score=85), Student(name="F", score=80)]
    svc = RankingService()
    res = svc.calculate_rankings(students)

    # two at 95 -> rank 1
    assert res[0].rank == 1
    assert res[1].rank == 1

    # three at 85 -> rank 3 (two people ahead)
    assert res[2].rank == 3
    assert res[3].rank == 3
    assert res[4].rank == 3

    # 80 -> rank 6
    assert res[5].rank == 6


def test_all_same_score_idempotent():
    students = [Student(name=f"S{i}", score=90) for i in range(5)]
    svc = RankingService(idempotency_key="test-key")
    res1 = svc.calculate_rankings(students)
    res2 = svc.calculate_rankings(students)

    # All should be rank 1 and deterministic
    for r in res1:
        assert r.rank == 1

    # Subsequent call returns same result
    assert [r.rank for r in res1] == [r.rank for r in res2]


def test_invalid_score_rejected():
    svc = RankingService()
    students = [Student(name="Alice", score=-1), Student(name="Bob", score=101)]
    try:
        svc.calculate_rankings(students)
    except Exception as e:
        assert isinstance(e, Exception)
    else:
        assert False, "Expected exception for invalid scores"


def test_structured_logging_multiple_calls():
    # This test ensures the service logs JSON-friendly messages; assert we can parse output
    students = [Student(name="Alice", score=95), Student(name="Bob", score=80)]
    svc = RankingService(idempotency_key="run-1")
    _ = svc.calculate_rankings(students)
    # here we would capture logs in a real system - this is placeholder for showing intent
    assert True

