"""
State machine for ranking request lifecycle
- INIT → PENDING → PROCESSING → SUCCESS/FAILED
- Handles timeouts, retries, state transitions
"""

from enum import Enum
from typing import Callable, Optional, Tuple
from datetime import datetime, timedelta

from models import (
    RankRequest,
    RankResponse,
    ErrorResponse,
    RequestState,
    ErrorCode,
    ValidationError
)


class RequestStateMachine:
    """Manages request lifecycle state transitions."""
    
    # State transition rules (from -> to)
    _ALLOWED_TRANSITIONS = {
        RequestState.INIT: [RequestState.PENDING, RequestState.FAILED],
        RequestState.PENDING: [RequestState.PROCESSING, RequestState.FAILED],
        RequestState.PROCESSING: [RequestState.SUCCESS, RequestState.FAILED],
        RequestState.SUCCESS: [],  # Terminal state
        RequestState.FAILED: [RequestState.PENDING]  # Allow retry
    }
    
    def __init__(self):
        """Initialize state machine."""
        self._current_state = RequestState.INIT
        self._state_entered_at = datetime.utcnow()
    
    def can_transition_to(self, target_state: RequestState) -> bool:
        """Check if transition is allowed."""
        return target_state in self._ALLOWED_TRANSITIONS.get(
            self._current_state, []
        )
    
    def transition_to(
        self,
        target_state: RequestState,
        request: Optional[RankRequest] = None,
        timeout_ms: Optional[int] = None
    ) -> bool:
        """
        Attempt state transition.
        
        Args:
            target_state: Target state
            request: The ranking request (for timeout check)
            timeout_ms: Timeout in milliseconds (for timeout check)
        
        Returns:
            True if transition successful, False otherwise
        
        Raises:
            ValueError: If transition is not allowed
        """
        if not self.can_transition_to(target_state):
            raise ValueError(
                f"Cannot transition from {self._current_state} to {target_state}"
            )
        
        # Check timeout if transitioning to PROCESSING or SUCCESS
        if request and timeout_ms:
            elapsed = self._get_elapsed_ms()
            if elapsed > timeout_ms:
                # Transition to FAILED instead
                self._current_state = RequestState.FAILED
                return False
        
        self._current_state = target_state
        self._state_entered_at = datetime.utcnow()
        return True
    
    def get_current_state(self) -> RequestState:
        """Get current state."""
        return self._current_state
    
    def get_elapsed_ms(self) -> float:
        """Get elapsed time since state machine created."""
        return (datetime.utcnow() - self._state_entered_at).total_seconds() * 1000
    
    def _get_elapsed_ms(self) -> float:
        """Internal elapsed time getter."""
        return self.get_elapsed_ms()
    
    def is_terminal(self) -> bool:
        """Check if in terminal state (SUCCESS or FAILED)."""
        return self._current_state in [RequestState.SUCCESS, RequestState.FAILED]


class RequestOrchestrator:
    """
    Orchestrates the ranking request lifecycle.
    
    Handles:
    - State transitions
    - Validation
    - Processing
    - Error handling
    - Timeout management
    """
    
    def __init__(self):
        """Initialize orchestrator."""
        self._state_machines: dict = {}  # request_id -> state machine
    
    def create_request(self, request_id: str) -> RequestStateMachine:
        """Create new request state machine."""
        sm = RequestStateMachine()
        self._state_machines[request_id] = sm
        return sm
    
    def get_state_machine(self, request_id: str) -> Optional[RequestStateMachine]:
        """Get existing state machine for request."""
        return self._state_machines.get(request_id)
    
    def validate_transition(
        self,
        request_id: str,
        target_state: RequestState,
        request: Optional[RankRequest] = None,
        timeout_ms: Optional[int] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate if transition is allowed.
        
        Returns:
            Tuple of (allowed, reason_if_not)
        """
        sm = self.get_state_machine(request_id)
        if not sm:
            return False, f"No state machine for {request_id}"
        
        if not sm.can_transition_to(target_state):
            return False, (
                f"Cannot transition from {sm.get_current_state()} "
                f"to {target_state}"
            )
        
        if request and timeout_ms:
            if sm.get_elapsed_ms() > timeout_ms:
                return False, "Request exceeded timeout"
        
        return True, None


# Utility for validation
def validate_request_structure(request_dict: dict) -> Tuple[bool, list]:
    """
    Validate request dictionary structure.
    
    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []
    
    # Check required fields
    if "request_id" not in request_dict or not request_dict["request_id"]:
        errors.append({
            "field": "request_id",
            "constraint": "required",
            "message": "request_id is required"
        })
    
    if "students" not in request_dict:
        errors.append({
            "field": "students",
            "constraint": "required",
            "message": "students list is required"
        })
    elif not isinstance(request_dict["students"], list):
        errors.append({
            "field": "students",
            "constraint": "type",
            "message": "students must be a list"
        })
    elif len(request_dict["students"]) == 0:
        errors.append({
            "field": "students",
            "constraint": "min_length",
            "message": "students list must have at least 1 item"
        })
    else:
        # Validate each student
        for i, student in enumerate(request_dict["students"]):
            if not isinstance(student, dict):
                errors.append({
                    "field": f"students[{i}]",
                    "constraint": "type",
                    "message": "Each student must be an object"
                })
                continue
            
            if "name" not in student or not student["name"]:
                errors.append({
                    "field": f"students[{i}].name",
                    "constraint": "required",
                    "message": "name is required"
                })
            
            if "score" not in student:
                errors.append({
                    "field": f"students[{i}].score",
                    "constraint": "required",
                    "message": "score is required"
                })
            elif not isinstance(student["score"], (int, float)):
                errors.append({
                    "field": f"students[{i}].score",
                    "value": str(student["score"]),
                    "constraint": "type",
                    "message": "score must be numeric"
                })
            elif student["score"] < 0 or student["score"] > 100:
                errors.append({
                    "field": f"students[{i}].score",
                    "value": str(student["score"]),
                    "constraint": "0 ≤ score ≤ 100",
                    "message": f"Score {student['score']} out of range"
                })
    
    # Check optional fields
    if "timeout_ms" in request_dict:
        if not isinstance(request_dict["timeout_ms"], int):
            errors.append({
                "field": "timeout_ms",
                "constraint": "type",
                "message": "timeout_ms must be integer"
            })
        elif (request_dict["timeout_ms"] < 1000 or
              request_dict["timeout_ms"] > 300000):
            errors.append({
                "field": "timeout_ms",
                "value": str(request_dict["timeout_ms"]),
                "constraint": "1000 ≤ timeout_ms ≤ 300000",
                "message": "timeout_ms out of range"
            })
    
    return len(errors) == 0, errors
