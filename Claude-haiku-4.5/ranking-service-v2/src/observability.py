"""
Structured logging and observability
- Logs with request_id tracing
- Metrics collection (tie detection, latency)
- Pre/post state snapshots for audit
"""

import json
import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import asdict

from models import RankRequest, RankResponse, ErrorResponse, RankingStatistics


# Configure logging format
class JsonFormatter(logging.Formatter):
    """Custom JSON formatter for structured logs."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name
        }
        
        # Add request_id if available in extra
        if hasattr(record, "request_id") and record.request_id:
            log_data["request_id"] = record.request_id
        
        # Add custom fields from extra
        if hasattr(record, "extra_data") and record.extra_data:
            log_data.update(record.extra_data)
        
        return json.dumps(log_data, default=str)


def configure_logging(log_file: Optional[str] = None) -> logging.Logger:
    """Configure structured logging."""
    logger = logging.getLogger("ranking-service-v2")
    logger.setLevel(logging.DEBUG)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JsonFormatter())
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(JsonFormatter())
        logger.addHandler(file_handler)
    
    return logger


class RequestLogger:
    """Logger for ranking request lifecycle."""
    
    def __init__(self, logger: logging.Logger):
        """Initialize with logger instance."""
        self.logger = logger
    
    def log_request_received(self, request: RankRequest):
        """Log when request is received."""
        extra = {
            "event": "RequestReceived",
            "request_id": request.request_id,
            "student_count": len(request.students),
            "strategy": request.ranking_strategy.value,
            "client_id": request.client_id
        }
        self._log_with_extra("INFO", "Ranking request received", extra)
    
    def log_validation_started(self, request: RankRequest):
        """Log validation phase start."""
        extra = {
            "event": "ValidationStarted",
            "request_id": request.request_id,
            "student_count": len(request.students)
        }
        self._log_with_extra("INFO", "Validating request", extra)
    
    def log_validation_passed(self, request: RankRequest):
        """Log validation success."""
        extra = {
            "event": "ValidationPassed",
            "request_id": request.request_id,
            "input_hash": request.input_hash()
        }
        self._log_with_extra("INFO", "Validation passed", extra)
    
    def log_validation_failed(self, request: RankRequest, errors: List[Dict[str, Any]]):
        """Log validation failures."""
        extra = {
            "event": "ValidationFailed",
            "request_id": request.request_id,
            "error_count": len(errors),
            "errors": errors
        }
        self._log_with_extra("WARN", "Validation failed", extra)
    
    def log_ranking_started(self, request: RankRequest):
        """Log ranking calculation start."""
        extra = {
            "event": "RankingStarted",
            "request_id": request.request_id,
            "strategy": request.ranking_strategy.value
        }
        self._log_with_extra("INFO", "Starting ranking calculation", extra)
    
    def log_ranking_completed(
        self,
        request: RankRequest,
        response: RankResponse,
        processing_ms: float
    ):
        """Log ranking completion with metrics."""
        stats = response.statistics
        extra = {
            "event": "RankingCompleted",
            "request_id": request.request_id,
            "status": response.status.value,
            "processing_ms": processing_ms,
            "metrics": {
                "total_students": stats.total_students,
                "unique_scores": stats.unique_scores,
                "tie_groups_count": len(stats.tie_groups),
                "tie_groups": [
                    {
                        "score": tg.score,
                        "count": tg.count,
                        "rank": tg.rank
                    }
                    for tg in stats.tie_groups
                ],
                "rank_variance": stats.rank_variance
            }
        }
        self._log_with_extra("INFO", "Ranking calculation completed", extra)
    
    def log_ranking_error(
        self,
        request: RankRequest,
        error: Exception,
        processing_ms: float
    ):
        """Log ranking error with context."""
        extra = {
            "event": "RankingError",
            "request_id": request.request_id,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "processing_ms": processing_ms
        }
        self._log_with_extra("ERROR", f"Ranking failed: {error}", extra)
    
    def log_response_sent(self, request_id: str, status: str, cached: bool = False):
        """Log response sent to client."""
        extra = {
            "event": "ResponseSent",
            "request_id": request_id,
            "status": status,
            "cached": cached
        }
        self._log_with_extra("INFO", "Response sent", extra)
    
    def log_idempotency_hit(self, request_id: str):
        """Log when request is served from cache."""
        extra = {
            "event": "IdempotencyHit",
            "request_id": request_id,
            "cached": True
        }
        self._log_with_extra("INFO", "Serving from cache (idempotent)", extra)
    
    def log_timeout(self, request_id: str, timeout_ms: int, elapsed_ms: float):
        """Log timeout occurrence."""
        extra = {
            "event": "Timeout",
            "request_id": request_id,
            "timeout_ms": timeout_ms,
            "elapsed_ms": elapsed_ms
        }
        self._log_with_extra("WARN", "Request timeout exceeded", extra)
    
    def _log_with_extra(self, level: str, message: str, extra_data: Dict[str, Any]):
        """Helper to log with extra JSON data."""
        log_method = getattr(self.logger, level.lower())
        record = self.logger.makeRecord(
            name=self.logger.name,
            level=getattr(logging, level),
            fn="",
            lno=0,
            msg=message,
            args=(),
            exc_info=None
        )
        record.extra_data = extra_data
        if "request_id" in extra_data:
            record.request_id = extra_data["request_id"]
        log_method(record)


class MetricsCollector:
    """Collect and aggregate metrics for monitoring."""
    
    def __init__(self):
        """Initialize metrics."""
        self.requests_total = 0
        self.requests_success = 0
        self.requests_failed = 0
        self.requests_cached = 0
        self.processing_times: List[float] = []
        self.tie_detections = 0
    
    def record_request_success(self, processing_ms: float, has_ties: bool):
        """Record successful ranking."""
        self.requests_total += 1
        self.requests_success += 1
        self.processing_times.append(processing_ms)
        if has_ties:
            self.tie_detections += 1
    
    def record_request_failed(self):
        """Record failed ranking."""
        self.requests_total += 1
        self.requests_failed += 1
    
    def record_request_cached(self):
        """Record cached (idempotent) hit."""
        self.requests_cached += 1
    
    def get_summary(self) -> Dict[str, Any]:
        """Get metrics summary."""
        if not self.processing_times:
            p50, p95, p99 = 0, 0, 0
        else:
            sorted_times = sorted(self.processing_times)
            p50 = sorted_times[int(len(sorted_times) * 0.50)]
            p95 = sorted_times[int(len(sorted_times) * 0.95)]
            p99 = sorted_times[int(len(sorted_times) * 0.99)]
        
        return {
            "requests_total": self.requests_total,
            "requests_success": self.requests_success,
            "requests_failed": self.requests_failed,
            "requests_cached": self.requests_cached,
            "success_rate": (
                self.requests_success / self.requests_total
                if self.requests_total > 0 else 0
            ),
            "cache_hit_rate": (
                self.requests_cached / self.requests_total
                if self.requests_total > 0 else 0
            ),
            "processing_latency_ms": {
                "p50": p50,
                "p95": p95,
                "p99": p99,
                "count": len(self.processing_times)
            },
            "tie_detections": self.tie_detections
        }


# Global instances
_logger = None
_request_logger = None
_metrics = None


def get_logger() -> logging.Logger:
    """Get global logger instance."""
    global _logger
    if _logger is None:
        _logger = configure_logging()
    return _logger


def get_request_logger() -> RequestLogger:
    """Get global request logger instance."""
    global _request_logger
    if _request_logger is None:
        _request_logger = RequestLogger(get_logger())
    return _request_logger


def get_metrics() -> MetricsCollector:
    """Get global metrics collector."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics
