"""
Idempotency layer for request deduplication
- Tracks requests by idempotency key
- Returns cached results for duplicate requests
- Prevents double-processing
"""

from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

from models import (
    RankRequest,
    RankResponse,
    ErrorResponse,
    RequestState
)


class IdempotencyStore:
    """In-memory store for idempotency tracking."""
    
    def __init__(self, ttl_hours: int = 24):
        """
        Initialize idempotency store.
        
        Args:
            ttl_hours: Time-to-live for cached results (default 24 hours)
        """
        self.ttl = timedelta(hours=ttl_hours)
        self._requests: Dict[str, Tuple[datetime, RankRequest]] = {}
        self._results: Dict[str, Tuple[datetime, RankResponse]] = {}
        self._errors: Dict[str, Tuple[datetime, ErrorResponse]] = {}
    
    def get_cached_result(self, idempotency_key: str) -> Optional[RankResponse]:
        """
        Retrieve cached success result if exists.
        
        Args:
            idempotency_key: Unique request identifier
        
        Returns:
            RankResponse if cached and not expired, else None
        """
        if idempotency_key not in self._results:
            return None
        
        timestamp, result = self._results[idempotency_key]
        if self._is_expired(timestamp):
            del self._results[idempotency_key]
            return None
        
        return result
    
    def get_cached_error(self, idempotency_key: str) -> Optional[ErrorResponse]:
        """
        Retrieve cached error result if exists.
        
        Args:
            idempotency_key: Unique request identifier
        
        Returns:
            ErrorResponse if cached and not expired, else None
        """
        if idempotency_key not in self._errors:
            return None
        
        timestamp, error = self._errors[idempotency_key]
        if self._is_expired(timestamp):
            del self._errors[idempotency_key]
            return None
        
        return error
    
    def cache_success(
        self,
        idempotency_key: str,
        request: RankRequest,
        result: RankResponse
    ):
        """
        Cache successful ranking result.
        
        Args:
            idempotency_key: Unique request identifier
            request: The ranking request
            result: The ranking result
        """
        now = datetime.utcnow()
        self._requests[idempotency_key] = (now, request)
        self._results[idempotency_key] = (now, result)
        # Clean up error entry if exists
        if idempotency_key in self._errors:
            del self._errors[idempotency_key]
    
    def cache_error(
        self,
        idempotency_key: str,
        request: RankRequest,
        error: ErrorResponse
    ):
        """
        Cache error result.
        
        Args:
            idempotency_key: Unique request identifier
            request: The ranking request
            error: The error response
        """
        now = datetime.utcnow()
        self._requests[idempotency_key] = (now, request)
        self._errors[idempotency_key] = (now, error)
        # Clean up result entry if exists
        if idempotency_key in self._results:
            del self._results[idempotency_key]
    
    def exists(self, idempotency_key: str) -> bool:
        """Check if request has been processed before."""
        return idempotency_key in self._requests
    
    def is_processing(self, idempotency_key: str) -> bool:
        """
        Check if request is currently being processed.
        
        In a real system, this would check persistent state.
        For now, we assume if not cached, then not processing.
        """
        return (
            self.exists(idempotency_key) and
            idempotency_key not in self._results and
            idempotency_key not in self._errors
        )
    
    def clear_expired(self):
        """Remove expired entries (cleanup)."""
        now = datetime.utcnow()
        
        # Clean requests
        expired = [
            key for key, (ts, _) in self._requests.items()
            if now - ts > self.ttl
        ]
        for key in expired:
            if key in self._requests:
                del self._requests[key]
            if key in self._results:
                del self._results[key]
            if key in self._errors:
                del self._errors[key]
    
    def _is_expired(self, timestamp: datetime) -> bool:
        """Check if timestamp is expired."""
        return datetime.utcnow() - timestamp > self.ttl


# Global instance
_store = None


def get_idempotency_store() -> IdempotencyStore:
    """Get global idempotency store."""
    global _store
    if _store is None:
        _store = IdempotencyStore()
    return _store
