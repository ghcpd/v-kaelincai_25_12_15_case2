"""Greenfield Ranking Service (v2)

Features implemented for the exercise:
- Dense ranking algorithm (ties share same rank; next rank = people ahead + 1)
- Idempotent request handling via request_id
- Transactional outbox pattern (in-memory for tests)
- Publish with retry + exponential backoff
- Circuit breaker protection for external publisher
- Simple compensation (rollback) when publish permanently fails
- Reconciliation API to flush outbox later
- Structured logging hooks
"""

import time
import uuid
import json
from typing import Any, Dict, List, Optional

from .utils import get_logger, log_structured, mask_sensitive
from .circuit_breaker import CircuitBreaker, CircuitOpenError


class PublishError(Exception):
    pass


class RankingService:
    def __init__(self, publisher, log_path: str = "logs/log_post.txt"):
        self.publisher = publisher
        self.logger = get_logger(log_path)

        # in-memory stores (can be swapped for DB in real system)
        self.db: Dict[str, Dict[str, Any]] = {}         # request_id -> result record
        self.outbox: List[Dict[str, Any]] = []         # queued events
        self.processed: Dict[str, Any] = {}            # request_id -> result
        self.compensations: List[Dict[str, Any]] = []  # compensation records

        # circuit breaker around publisher
        # Configure failure_threshold >= max publish attempts used in tests to avoid
        # opening the circuit before retries are exhausted.
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=0.15)

        # metrics for tests
        self.metrics: Dict[str, Any] = {
            "publish_attempts": 0,
            "publish_retries": 0,
            "compensations": 0,
            "reconciled": 0,
        }

    # ------------------ Core API ------------------
    def process_request(self, request: Dict[str, Any], max_publish_attempts: int = 3, backoff_base: float = 0.01) -> Dict[str, Any]:
        """Process a ranking request.

        request: {
            "request_id": str (optional),
            "students": [{"name": str, "score": number}, ...]
        }
        """
        request_id = request.get("request_id") or str(uuid.uuid4())
        students = request.get("students", [])

        # Idempotency: return previous response if available
        if request_id in self.processed:
            log_structured(self.logger, 20, "idempotent_replay", request_id=request_id)
            return {
                "request_id": request_id,
                "status": "ok",
                "rankings": self.processed[request_id]["rankings"],
                "idempotent": True,
            }

        # Validation
        for s in students:
            if not isinstance(s.get("score", None), (int, float)) or s["score"] < 0 or s["score"] > 100:
                raise ValueError("Score must be between 0 and 100")

        # Compute dense rankings
        rankings = self._compute_dense_rankings(students)

        # Persist (in-memory) before publish — part of transactional outbox pattern
        record = {
            "request_id": request_id,
            "created_at": time.time(),
            "students": students,
            "rankings": rankings,
            "status": "pending",
        }
        self.db[request_id] = record

        # outbox event
        event = {"type": "ranking.computed", "request_id": request_id, "payload": rankings}
        self.outbox.append(event)

        # Attempt to publish with retry/backoff under circuit breaker
        publish_attempts = 0
        last_exc: Optional[Exception] = None
        try:
            while publish_attempts < max_publish_attempts:
                publish_attempts += 1
                try:
                    self.circuit_breaker.before_call()
                    self.publisher.publish(event)
                    self.circuit_breaker.on_success()
                    # success: remove event from outbox
                    if event in self.outbox:
                        self.outbox.remove(event)
                    record["status"] = "completed"
                    self.processed[request_id] = record
                    self.metrics["publish_attempts"] += 1
                    log_structured(self.logger, 20, "publish_success", request_id=request_id, attempts=publish_attempts)
                    break
                except CircuitOpenError as ce:
                    last_exc = ce
                    log_structured(self.logger, 40, "circuit_open", request_id=request_id, error=str(ce))
                    raise
                except Exception as exc:
                    last_exc = exc
                    self.circuit_breaker.on_failure()
                    self.metrics["publish_retries"] += 1
                    log_structured(self.logger, 30, "publish_attempt_failed", request_id=request_id, attempt=publish_attempts, error=str(exc))
                    # backoff
                    time.sleep(backoff_base * (2 ** (publish_attempts - 1)))

            else:
                # exhausted attempts without success
                raise PublishError(f"publish failed after {publish_attempts} attempts: {last_exc}")

        except Exception as final_exc:
            # permanent failure path: mark failed and perform compensation (simple saga)
            record["status"] = "failed"
            self.metrics["compensations"] += 1
            comp = self._compensate(request_id)
            self.compensations.append(comp)
            log_structured(self.logger, 40, "compensation_performed", request_id=request_id, reason=str(final_exc))
            return {"request_id": request_id, "status": "failed", "error": str(final_exc), "compensated": True}

        # success
        return {"request_id": request_id, "status": "ok", "rankings": rankings, "attempts": publish_attempts}

    # ------------------ Ranking Algorithm ------------------
    @staticmethod
    def _compute_dense_rankings(students: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # sort by score desc, then compute DENSE ranks:
        # ties share same rank; next distinct score -> rank = previous rank + 1
        sorted_students = sorted(students, key=lambda s: s["score"], reverse=True)
        rankings: List[Dict[str, Any]] = []

        prev_score = None
        current_rank = 0

        for s in sorted_students:
            if prev_score is None or s["score"] != prev_score:
                current_rank += 1
            rankings.append({"name": s["name"], "score": s["score"], "rank": current_rank})
            prev_score = s["score"]

        return rankings

    # ------------------ Reconciliation / Outbox ------------------
    def reconcile_outbox(self, max_attempts: int = 3, backoff_base: float = 0.01) -> Dict[str, Any]:
        """Try to flush the outbox again. Returns reconciliation metrics."""
        reconciled = 0
        for event in list(self.outbox):
            attempts = 0
            last_exc = None
            try:
                while attempts < max_attempts:
                    attempts += 1
                    try:
                        self.circuit_breaker.before_call()
                        self.publisher.publish(event)
                        self.circuit_breaker.on_success()
                        if event in self.outbox:
                            self.outbox.remove(event)
                        reconciled += 1
                        self.metrics["reconciled"] = self.metrics.get("reconciled", 0) + 1
                        log_structured(self.logger, 20, "reconcile_success", request_id=event.get("request_id"), attempts=attempts)
                        break
                    except CircuitOpenError as ce:
                        last_exc = ce
                        log_structured(self.logger, 40, "reconcile_circuit_open", request_id=event.get("request_id"), error=str(ce))
                        raise
                    except Exception as exc:
                        last_exc = exc
                        self.circuit_breaker.on_failure()
                        time.sleep(backoff_base * (2 ** (attempts - 1)))
                else:
                    log_structured(self.logger, 40, "reconcile_failed", request_id=event.get("request_id"), error=str(last_exc))
            except Exception:
                # leave event in outbox
                continue

        return {"reconciled": reconciled, "outbox_remaining": len(self.outbox)}

    # ------------------ Compensation (Saga) ------------------
    def _compensate(self, request_id: str) -> Dict[str, Any]:
        # Very small-scale compensation: remove persisted record (rollback) and record action
        comp = {"request_id": request_id, "action": "rollback", "ts": time.time()}
        if request_id in self.db:
            self.db.pop(request_id, None)
        # ensure outbox keeps any event (for later reconciliation)
        self.metrics["compensations"] = self.metrics.get("compensations", 0) + 1
        return comp


if __name__ == "__main__":
    # demo: run a reconciliation or a sample request
    import argparse
    from mocks.notifier import Notifier

    parser = argparse.ArgumentParser()
    parser.add_argument("--reconcile", action="store_true")
    args = parser.parse_args()

    notifier = Notifier()
    service = RankingService(notifier)

    if args.reconcile:
        print("Reconciling outbox...")
        print(service.reconcile_outbox())
    else:
        req = {"students": [{"name": "Alice", "score": 95}, {"name": "Bob", "score": 95}, {"name": "Charlie", "score": 90}], "request_id": "demo-1"}
        print(service.process_request(req))
