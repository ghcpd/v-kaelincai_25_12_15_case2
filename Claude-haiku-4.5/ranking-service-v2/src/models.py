"""
Data models for Ranking Service v2
- Defines request/response schemas with validation
- Provides type safety and serialization
"""

from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Literal
from datetime import datetime
from enum import Enum
import json
import hashlib


class RankingStrategy(str, Enum):
    """Ranking strategies (extensibility)."""
    COMPETITION = "COMPETITION"  # Same score = same rank; next different = rank+count
    DENSE = "DENSE"              # Same score = same rank; next different = rank+1
    ORDINAL = "ORDINAL"          # Each gets unique rank (1,2,3...) even with ties


class RequestState(str, Enum):
    """Lifecycle states for ranking requests."""
    INIT = "INIT"
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class ErrorCode(str, Enum):
    """Error classification."""
    VALIDATION_ERROR = "VALIDATION_ERROR"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


@dataclass
class StudentInput:
    """Input student record."""
    name: str
    score: float
    metadata: Optional[Dict] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate student data."""
        if not self.name or len(self.name.strip()) == 0:
            raise ValueError("Student name cannot be empty")
        if len(self.name) > 255:
            raise ValueError("Student name exceeds 255 characters")
        if not isinstance(self.score, (int, float)):
            raise ValueError(f"Score must be numeric, got {type(self.score)}")
        if self.score < 0 or self.score > 100:
            raise ValueError(f"Score {self.score} out of range [0, 100]")
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "name": self.name,
            "score": self.score,
            "metadata": self.metadata
        }


@dataclass
class StudentOutput:
    """Output student record with rank."""
    name: str
    score: float
    rank: int
    metadata: Optional[Dict] = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "name": self.name,
            "score": self.score,
            "rank": self.rank,
            "metadata": self.metadata
        }


@dataclass
class TieGroup:
    """Statistics about a group of tied scores."""
    score: float
    count: int
    rank: int
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "score": self.score,
            "count": self.count,
            "rank": self.rank
        }


@dataclass
class RankingStatistics:
    """Aggregated metrics from ranking operation."""
    total_students: int
    unique_scores: int
    tie_groups: List[TieGroup] = field(default_factory=list)
    processing_ms: float = 0.0
    rank_variance: float = 0.0  # Measure of rank spread
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "total_students": self.total_students,
            "unique_scores": self.unique_scores,
            "tie_groups": [tg.to_dict() for tg in self.tie_groups],
            "processing_ms": self.processing_ms,
            "rank_variance": self.rank_variance
        }


@dataclass
class RankRequest:
    """Request to rank a cohort of students."""
    request_id: str
    students: List[StudentInput]
    ranking_strategy: RankingStrategy = RankingStrategy.DENSE
    timeout_ms: int = 30000
    idempotency_key: Optional[str] = None
    client_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Validate request structure."""
        if not self.request_id or len(self.request_id.strip()) == 0:
            raise ValueError("request_id required")
        if len(self.students) == 0:
            raise ValueError("At least one student required")
        if len(self.students) > 10_000_000:
            raise ValueError("Student count exceeds limit (10M)")
        if self.timeout_ms < 1000 or self.timeout_ms > 300000:
            raise ValueError("timeout_ms must be in [1000, 300000]")
        if self.idempotency_key is None:
            self.idempotency_key = self.request_id
        
        # Validate each student
        for student in self.students:
            if isinstance(student, dict):
                try:
                    self.students[self.students.index(student)] = StudentInput(**student)
                except (KeyError, TypeError, ValueError) as e:
                    raise ValueError(f"Invalid student: {e}")
            elif not isinstance(student, StudentInput):
                raise ValueError(f"Expected StudentInput, got {type(student)}")
    
    def input_hash(self) -> str:
        """Generate hash of input for dedup."""
        # Hash the sorted student list (deterministic)
        sorted_input = json.dumps(
            sorted([s.to_dict() for s in self.students], 
                   key=lambda x: (x['score'], x['name'])),
            sort_keys=True
        )
        return hashlib.sha256(sorted_input.encode()).hexdigest()
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "request_id": self.request_id,
            "students": [s.to_dict() for s in self.students],
            "ranking_strategy": self.ranking_strategy.value,
            "timeout_ms": self.timeout_ms,
            "idempotency_key": self.idempotency_key,
            "client_id": self.client_id,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class RankResponse:
    """Successful response with ranked results."""
    request_id: str
    status: RequestState
    results: List[StudentOutput]
    statistics: RankingStatistics
    timestamp_ms: datetime = field(default_factory=datetime.utcnow)
    cached: bool = False
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "request_id": self.request_id,
            "status": self.status.value,
            "results": [r.to_dict() for r in self.results],
            "statistics": self.statistics.to_dict(),
            "timestamp_ms": self.timestamp_ms.isoformat(),
            "cached": self.cached
        }


@dataclass
class ValidationError:
    """A single validation failure."""
    field: str
    value: str
    constraint: str
    message: str
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "field": self.field,
            "value": self.value,
            "constraint": self.constraint,
            "message": self.message
        }


@dataclass
class ErrorResponse:
    """Error response with diagnostic info."""
    request_id: str
    status: RequestState
    error_code: ErrorCode
    error_message: str
    validation_errors: List[ValidationError] = field(default_factory=list)
    timestamp_ms: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict:
        """Serialize to dict."""
        return {
            "request_id": self.request_id,
            "status": self.status.value,
            "error_code": self.error_code.value,
            "error_message": self.error_message,
            "validation_errors": [e.to_dict() for e in self.validation_errors],
            "timestamp_ms": self.timestamp_ms.isoformat()
        }
