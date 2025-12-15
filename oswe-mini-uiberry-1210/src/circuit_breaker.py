import time
from enum import Enum


class State(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    pass


class CircuitBreaker:
    """A simple circuit-breaker implementation for testing.

    - failure_threshold: number of consecutive failures to open the circuit
    - recovery_timeout: seconds before attempting half-open
    - half_open_success_threshold: consecutive successes to close again
    """

    def __init__(self, failure_threshold=3, recovery_timeout=0.2, half_open_success_threshold=1):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold

        self.state = State.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.opened_at = None

    def before_call(self):
        if self.state == State.OPEN:
            if (time.time() - self.opened_at) >= self.recovery_timeout:
                # try half-open
                self.state = State.HALF_OPEN
                self.success_count = 0
            else:
                raise CircuitOpenError("circuit is open")

    def on_success(self):
        if self.state in (State.HALF_OPEN, State.OPEN):
            self.success_count += 1
            if self.success_count >= self.half_open_success_threshold:
                self._close()
        else:
            self.failure_count = 0

    def on_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self._open()

    def _open(self):
        self.state = State.OPEN
        self.opened_at = time.time()
        self.failure_count = 0

    def _close(self):
        self.state = State.CLOSED
        self.failure_count = 0
        self.success_count = 0

    def force_open(self):
        self._open()

    def state_name(self):
        return self.state.value
