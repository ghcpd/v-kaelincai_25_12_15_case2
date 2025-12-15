"""
Core ranking engine for v2
- Implements fixed competition ranking algorithm
- Idempotent; deterministic sort order
- Produces detailed statistics for audit trail
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass
import time
from enum import Enum

from models import (
    StudentInput,
    StudentOutput,
    RankingStrategy,
    RankingStatistics,
    TieGroup
)


class RankingEngine:
    """Fixed ranking engine with competition semantics."""
    
    def rank_students(
        self,
        students: List[StudentInput],
        strategy: RankingStrategy = RankingStrategy.COMPETITION
    ) -> Tuple[List[StudentOutput], RankingStatistics]:
        """
        Rank students using specified strategy.
        
        Args:
            students: List of StudentInput objects
            strategy: COMPETITION (default), DENSE, or ORDINAL
        
        Returns:
            Tuple of (ranked_students, statistics)
        
        Raises:
            ValueError: If validation fails
        """
        start_time = time.time()
        
        # Step 1: Validate inputs
        if not students:
            raise ValueError("At least one student required")
        
        for i, student in enumerate(students):
            if not isinstance(student, StudentInput):
                raise ValueError(f"students[{i}] not a StudentInput")
            if student.score < 0 or student.score > 100:
                raise ValueError(
                    f"students[{i}] ({student.name}): "
                    f"score {student.score} out of range [0, 100]"
                )
        
        # Step 2: Sort deterministically (score desc, then name asc for stability)
        sorted_students = sorted(
            students,
            key=lambda s: (-s.score, s.name)
        )
        
        # Step 3: Assign ranks based on strategy
        if strategy == RankingStrategy.COMPETITION:
            ranked = self._rank_competition(sorted_students)
        elif strategy == RankingStrategy.DENSE:
            ranked = self._rank_dense(sorted_students)
        elif strategy == RankingStrategy.ORDINAL:
            ranked = self._rank_ordinal(sorted_students)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
        
        # Step 4: Compute statistics
        elapsed_ms = (time.time() - start_time) * 1000
        stats = self._compute_statistics(ranked, elapsed_ms)
        
        return ranked, stats
    
    def _rank_competition(self, sorted_students: List[StudentInput]) -> List[StudentOutput]:
        """
        Competition ranking:
        - Same score → same rank
        - Next different score → rank = (count_ranked_so_far + 1)
        
        Example:
            Alice 95, Bob 95, Charlie 90, David 90, Eve 85
            → Ranks: 1, 1, 3, 3, 5
        """
        ranked = []
        current_rank = 1
        prev_score = None
        
        for idx, student in enumerate(sorted_students):
            # Update rank when score changes
            if prev_score is not None and student.score != prev_score:
                current_rank = idx + 1  # Rank = (count ranked so far + 1)
            
            ranked.append(StudentOutput(
                name=student.name,
                score=student.score,
                rank=current_rank,
                metadata=student.metadata
            ))
            prev_score = student.score
        
        return ranked
    
    def _rank_dense(self, sorted_students: List[StudentInput]) -> List[StudentOutput]:
        """
        Dense ranking:
        - Same score → same rank
        - Next different score → rank = (current_rank + 1)
        
        Example:
            Alice 95, Bob 95, Charlie 90, David 90, Eve 85
            → Ranks: 1, 1, 2, 2, 3
        """
        ranked = []
        current_rank = 1
        prev_score = None
        
        for student in sorted_students:
            if prev_score is not None and student.score != prev_score:
                current_rank += 1
            
            ranked.append(StudentOutput(
                name=student.name,
                score=student.score,
                rank=current_rank,
                metadata=student.metadata
            ))
            prev_score = student.score
        
        return ranked
    
    def _rank_ordinal(self, sorted_students: List[StudentInput]) -> List[StudentOutput]:
        """
        Ordinal ranking:
        - Every student gets unique rank (1, 2, 3, ...)
        - Ties broken by sort order (name)
        
        Example:
            Alice 95, Bob 95, Charlie 90, David 90, Eve 85
            → Ranks: 1, 2, 3, 4, 5
        """
        ranked = []
        for idx, student in enumerate(sorted_students):
            ranked.append(StudentOutput(
                name=student.name,
                score=student.score,
                rank=idx + 1,
                metadata=student.metadata
            ))
        
        return ranked
    
    def _compute_statistics(
        self,
        ranked: List[StudentOutput],
        elapsed_ms: float
    ) -> RankingStatistics:
        """Compute aggregated statistics about the ranking."""
        
        # Collect unique scores and build tie groups
        score_to_count: Dict[float, int] = {}
        score_to_rank: Dict[float, int] = {}
        
        for student in ranked:
            score = student.score
            score_to_count[score] = score_to_count.get(score, 0) + 1
            if score not in score_to_rank:
                score_to_rank[score] = student.rank
        
        # Build tie group list (sorted by rank)
        tie_groups = []
        for score in sorted(score_to_rank.keys(), reverse=True):
            if score_to_count[score] > 1:  # Only groups with ties
                tie_groups.append(TieGroup(
                    score=score,
                    count=score_to_count[score],
                    rank=score_to_rank[score]
                ))
        
        # Compute rank variance (spread of ranks)
        ranks = [s.rank for s in ranked]
        mean_rank = sum(ranks) / len(ranks)
        variance = sum((r - mean_rank) ** 2 for r in ranks) / len(ranks)
        rank_variance = variance ** 0.5  # Standard deviation
        
        return RankingStatistics(
            total_students=len(ranked),
            unique_scores=len(score_to_count),
            tie_groups=tie_groups,
            processing_ms=elapsed_ms,
            rank_variance=rank_variance
        )


# Singleton instance
_engine = RankingEngine()


def rank_students(
    students: List[StudentInput],
    strategy: RankingStrategy = RankingStrategy.COMPETITION
) -> Tuple[List[StudentOutput], RankingStatistics]:
    """Convenience function to use singleton engine."""
    return _engine.rank_students(students, strategy)
