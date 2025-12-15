"""
Main API handler for ranking service v2
- Coordinates request processing
- Manages idempotency, validation, ranking, observability
"""

from typing import Dict, Tuple
from datetime import datetime

from models import (
    RankRequest,
    RankResponse,
    ErrorResponse,
    RequestState,
    ErrorCode,
    StudentInput,
    ValidationError
)
from ranking_engine import rank_students, RankingStrategy
from idempotency import get_idempotency_store
from observability import (
    get_request_logger,
    get_metrics,
    RequestLogger,
    MetricsCollector
)
from state_machine import (
    RequestStateMachine,
    validate_request_structure
)


class RankingServiceV2:
    """Main ranking service handler."""
    
    def __init__(self):
        """Initialize service."""
        self.idempotency_store = get_idempotency_store()
        self.request_logger: RequestLogger = get_request_logger()
        self.metrics: MetricsCollector = get_metrics()
        self._state_machines: Dict[str, RequestStateMachine] = {}
    
    def process_request(self, request_dict: Dict) -> Tuple[Dict, int]:
        """
        Process a ranking request.
        
        Args:
            request_dict: Request payload (dict)
        
        Returns:
            Tuple of (response_dict, http_status_code)
        """
        request_id = request_dict.get("request_id", "unknown")
        start_time = datetime.utcnow()
        
        # Step 1: Validate request structure
        is_valid, validation_errors = validate_request_structure(request_dict)
        if not is_valid:
            processing_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            # Log validation failure without creating RankRequest with empty students
            self.request_logger.logger.info(
                f"Validation failed for request {request_id}: {validation_errors}"
            )
            self.metrics.record_request_failed()
            
            error_objs = [
                ValidationError(
                    field=e["field"],
                    value=e.get("value", ""),
                    constraint=e["constraint"],
                    message=e["message"]
                )
                for e in validation_errors
            ]
            
            error_response = ErrorResponse(
                request_id=request_id,
                status=RequestState.FAILED,
                error_code=ErrorCode.VALIDATION_ERROR,
                error_message="Request validation failed",
                validation_errors=error_objs
            )
            return error_response.to_dict(), 400
        
        # Step 2: Parse request
        try:
            students = [
                StudentInput(
                    name=s["name"],
                    score=s["score"],
                    metadata=s.get("metadata", {})
                )
                for s in request_dict["students"]
            ]
        except (ValueError, KeyError, TypeError) as e:
            processing_ms_err = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.metrics.record_request_failed()
            
            error_response = ErrorResponse(
                request_id=request_id,
                status=RequestState.FAILED,
                error_code=ErrorCode.VALIDATION_ERROR,
                error_message=f"Invalid request data: {str(e)}",
                validation_errors=[]
            )
            return error_response.to_dict(), 400
        
        request = RankRequest(
            request_id=request_id,
            students=students,
            ranking_strategy=RankingStrategy(
                request_dict.get("ranking_strategy", "DENSE")
            ),
            timeout_ms=request_dict.get("timeout_ms", 30000),
            client_id=request_dict.get("client_id")
        )
        
        idempotency_key = request.idempotency_key
        
        # Step 3: Check idempotency
        cached_result = self.idempotency_store.get_cached_result(idempotency_key)
        if cached_result:
            self.request_logger.log_idempotency_hit(request_id)
            self.metrics.record_request_cached()
            
            response_dict = cached_result.to_dict()
            response_dict["cached"] = True
            return response_dict, 200
        
        cached_error = self.idempotency_store.get_cached_error(idempotency_key)
        if cached_error:
            self.request_logger.log_idempotency_hit(request_id)
            self.metrics.record_request_failed()
            return cached_error.to_dict(), 400
        
        # Step 4: Log request received
        self.request_logger.log_request_received(request)
        self.request_logger.log_validation_passed(request)
        
        # Step 5: State machine setup
        sm = RequestStateMachine()
        self._state_machines[request_id] = sm
        
        # Step 6: Transition to PROCESSING
        self.request_logger.log_ranking_started(request)
        
        # Step 7: Calculate rankings
        try:
            ranked, statistics = rank_students(
                request.students,
                request.ranking_strategy
            )
            
            # Check timeout before creating response
            processing_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            if processing_ms > request.timeout_ms:
                self.request_logger.log_timeout(
                    request_id,
                    request.timeout_ms,
                    processing_ms
                )
                self.metrics.record_request_failed()
                
                error_response = ErrorResponse(
                    request_id=request_id,
                    status=RequestState.FAILED,
                    error_code=ErrorCode.TIMEOUT,
                    error_message=(
                        f"Request exceeded timeout of {request.timeout_ms}ms "
                        f"(took {processing_ms:.0f}ms)"
                    )
                )
                self.idempotency_store.cache_error(
                    idempotency_key,
                    request,
                    error_response
                )
                return error_response.to_dict(), 408  # 408 Request Timeout
            
            # Create response
            response = RankResponse(
                request_id=request_id,
                status=RequestState.SUCCESS,
                results=ranked,
                statistics=statistics,
                cached=False
            )
            
            # Update metrics
            has_ties = len(statistics.tie_groups) > 0
            self.metrics.record_request_success(statistics.processing_ms, has_ties)
            
            # Log completion
            self.request_logger.log_ranking_completed(
                request,
                response,
                statistics.processing_ms
            )
            
            # Cache result
            self.idempotency_store.cache_success(
                idempotency_key,
                request,
                response
            )
            
            # Log response sent
            self.request_logger.log_response_sent(request_id, "SUCCESS")
            
            return response.to_dict(), 200
        
        except Exception as e:
            processing_ms_err = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            self.request_logger.log_ranking_error(request, e, processing_ms_err)
            self.metrics.record_request_failed()
            
            error_response = ErrorResponse(
                request_id=request_id,
                status=RequestState.FAILED,
                error_code=ErrorCode.INTERNAL_ERROR,
                error_message=f"Internal error: {str(e)}"
            )
            
            self.idempotency_store.cache_error(
                idempotency_key,
                request,
                error_response
            )
            
            self.request_logger.log_response_sent(request_id, "FAILED")
            
            return error_response.to_dict(), 500
    
    def get_metrics(self) -> Dict:
        """Get current metrics."""
        return self.metrics.get_summary()


# Global singleton
_service = None


def get_ranking_service() -> RankingServiceV2:
    """Get global ranking service instance."""
    global _service
    if _service is None:
        _service = RankingServiceV2()
    return _service
