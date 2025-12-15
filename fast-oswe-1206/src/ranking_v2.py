"""
Ranking v2 - clean implementation

This module contains the greenfield replacement for the legacy ranking system.
It demonstrates:
- Correct ranking semantics with ties
- Deterministic, idempotent behavior
- Simple, typed API (input + output schemas)
- Structured logging (JSON friendly)

The small scope here is the ranking service only, but the design document
(and the surrounding project scaffold) illustrate how you could extract
and replace the legacy system as a service in a larger architecture.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Dict, Any
import json
import logging

# Configure structured logging to stdout or file depending on env
logger = logging.getLogger("ranking_v2")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
if not logger.handlers:
    logger.addHandler(handler)


@dataclass
class Student:
    name: str
    score: float
    rank: int | None = None

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "Student":
        return Student(name=d["name"], score=d["score"])

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RankingError(Exception):
    pass


class RankingService:
    """Pure function-style service to calculate rankings.

    Expected semantics:
    - Tied scores get the same rank
    - The next rank is #people_ahead + 1
    - Deterministic ordering by score desc then name asc for ties
    + input validation + structured logging
    """

    def __init__(self, *, idempotency_key: str | None = None):
        self.idempotency_key = idempotency_key

    def calculate_rankings(self, students: List[Student]) -> List[Student]:
        logger.info("RankingService.calculate_rankings start", extra={
            "idempotency_key": self.idempotency_key,
            "student_count": len(students)
        })

        # Validate inputs
        for s in students:
            if not isinstance(s.score, (int, float)):
                raise RankingError("Score must be numeric")
            if s.score < 0 or s.score > 100:
                raise RankingError("Score must be between 0 and 100")

        # Sort by score desc, then name asc for deterministic tie ordering
        sorted_students = sorted(students, key=lambda s: (-s.score, s.name))

        current_rank = 0
        num_ahead = 0
        last_score: float | None = None
        for s in sorted_students:
            if last_score is None or s.score != last_score:
                # new different score -> rank is people ahead + 1
                current_rank = num_ahead + 1
            # else keep same current_rank for ties
            s.rank = current_rank
            num_ahead += 1
            last_score = s.score

        logger.info("RankingService.calculate_rankings complete", extra={
            "idempotency_key": self.idempotency_key,
            "result": [s.to_dict() for s in sorted_students]
        })
        return sorted_students

    def get_rankings_json(self, students: List[Student]) -> str:
        ranked = self.calculate_rankings(students)
        return json.dumps([s.to_dict() for s in ranked])


def main() -> None:  # pragma: no cover - example
    # example usage for quick manual run
    raw = [
        {"name": "Alice", "score": 95},
        {"name": "Bob", "score": 95},
        {"name": "Charlie", "score": 90},
    ]
    students = [Student.from_dict(d) for d in raw]
    service = RankingService()
    ranked = service.calculate_rankings(students)
    print("Rankings:")
    for r in ranked:
        print(f"Rank {r.rank}: {r.name} - {r.score} pts")


if __name__ == "__main__":  # pragma: no cover
    main()
