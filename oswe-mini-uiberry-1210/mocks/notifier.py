"""Controllable notifier mock to simulate external system behavior

Behavior is configured via set_behavior(). Supported modes:
- always_succeed: publish always returns True
- fail_n_then_succeed: fails (Exception) for first N calls, then succeeds
- timeout_n_then_succeed: raises TimeoutError for first N calls, then succeeds
- always_fail: always raises Exception
- succeed_with_delay: sleeps for delay then returns True
"""

import time
from typing import Dict, Any


class Notifier:
    def __init__(self):
        # default: always succeed
        self.reset()

    def reset(self):
        self.behavior = {"mode": "always_succeed"}
        self.call_count = 0

    def set_behavior(self, behavior: Dict[str, Any]):
        """Set behavior e.g. {'mode': 'fail_n_then_succeed', 'n': 2} """
        self.behavior = behavior.copy()
        self.call_count = 0

    def publish(self, event: Dict[str, Any]):
        self.call_count += 1
        mode = self.behavior.get("mode", "always_succeed")

        if mode == "always_succeed":
            return True

        if mode == "fail_n_then_succeed":
            n = int(self.behavior.get("n", 1))
            if self.call_count <= n:
                raise Exception("transient error")
            return True

        if mode == "timeout_n_then_succeed":
            n = int(self.behavior.get("n", 1))
            if self.call_count <= n:
                raise TimeoutError("simulated timeout")
            return True

        if mode == "always_fail":
            raise Exception("permanent failure")

        if mode == "succeed_with_delay":
            d = float(self.behavior.get("delay", 0.05))
            time.sleep(d)
            return True

        # unknown mode: succeed
        return True
