import json
import os
import time
import pytest

from mocks.notifier import Notifier
from src.ranking_v2 import RankingService


ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_PATH = os.path.join(ROOT, "data")
RESULTS_PATH = os.path.join(ROOT, "results")
LOGS_PATH = os.path.join(ROOT, "logs")

os.makedirs(RESULTS_PATH, exist_ok=True)
os.makedirs(LOGS_PATH, exist_ok=True)


with open(os.path.join(DATA_PATH, "test_data.json"), "r", encoding="utf-8") as f:
    TEST_DATA = json.load(f)["cases"]

with open(os.path.join(DATA_PATH, "expected_postchange.json"), "r", encoding="utf-8") as f:
    EXPECTED = json.load(f)["cases"]


METRICS = {
    "tests_run": [],
    "success_rate": 0.0,
    "retry_counts": [],
}


def write_results_artifacts(summary: dict):
    with open(os.path.join(RESULTS_PATH, "results_post.json"), "w", encoding="utf-8") as fh:
        json.dump(summary.get("results", {}), fh, indent=2)
    with open(os.path.join(RESULTS_PATH, "aggregated_metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(summary.get("metrics", {}), fh, indent=2)


def test_01_healthy_path():
    notifier = Notifier()
    notifier.set_behavior({"mode": "always_succeed"})

    svc = RankingService(notifier, log_path=os.path.join(LOGS_PATH, "log_post.txt"))

    req = TEST_DATA["simple_no_ties"]
    resp = svc.process_request(req)

    assert resp["status"] == "ok"
    assert resp["rankings"] == EXPECTED["simple_no_ties"]

    METRICS["tests_run"].append({"test": "healthy_path", "status": "passed"})


def test_02_idempotency_replay():
    notifier = Notifier()
    notifier.set_behavior({"mode": "always_succeed"})

    svc = RankingService(notifier, log_path=os.path.join(LOGS_PATH, "log_post.txt"))

    req = TEST_DATA["two_tied_first"]
    # first run
    r1 = svc.process_request(req)
    # replay same request_id
    r2 = svc.process_request(req)

    assert r1["status"] == "ok"
    assert r2.get("idempotent", False) is True
    # ensure rankings are identical
    assert r1.get("rankings") == r2.get("rankings")

    METRICS["tests_run"].append({"test": "idempotency_replay", "status": "passed"})


def test_03_retry_with_backoff():
    notifier = Notifier()
    # fail twice then succeed to force retries
    notifier.set_behavior({"mode": "fail_n_then_succeed", "n": 2})

    svc = RankingService(notifier, log_path=os.path.join(LOGS_PATH, "log_post.txt"))

    req = TEST_DATA["multiple_ties_complex"]
    resp = svc.process_request(req)

    assert resp["status"] == "ok"
    # svc.metrics records retry events
    assert svc.metrics["publish_retries"] >= 2
    METRICS["retry_counts"].append(svc.metrics["publish_retries"])
    METRICS["tests_run"].append({"test": "retry_with_backoff", "status": "passed", "retries": svc.metrics["publish_retries"]})


def test_04_timeout_and_circuit_breaker(shared_env=None):
    # We'll demonstrate circuit-breaker opening and fast-fail behavior using a shared service
    notifier = Notifier()
    notifier.set_behavior({"mode": "always_fail"})

    svc = RankingService(notifier, log_path=os.path.join(LOGS_PATH, "log_post.txt"))

    # First request: will try and fail; circuit should open during attempts
    resp1 = svc.process_request(TEST_DATA["simple_no_ties"])  # will be compensated
    assert resp1["status"] == "failed"

    # Circuit should now be open (failure_threshold=2 in service)
    state = svc.circuit_breaker.state_name()
    assert state in ("open", "half_open") or state == "open"

    # Immediate second request should fail fast (compensated) because circuit is open
    resp2 = svc.process_request(TEST_DATA["two_tied_first"])
    assert resp2["status"] == "failed"

    METRICS["tests_run"].append({"test": "timeout_and_circuit_breaker", "status": "passed", "circuit_state": state})


def test_05_compensation_and_outbox():
    notifier = Notifier()
    notifier.set_behavior({"mode": "always_fail"})

    svc = RankingService(notifier, log_path=os.path.join(LOGS_PATH, "log_post.txt"))

    req = TEST_DATA["simple_no_ties"]
    resp = svc.process_request(req)

    # publish failed permanently, service should have compensated (rolled back) and left the outbox with the event
    assert resp["status"] == "failed"
    assert resp.get("compensated", False) is True
    # db record removed
    assert req["request_id"] not in svc.db
    # outbox still contains the event for reconciliation
    assert len(svc.outbox) >= 1

    METRICS["tests_run"].append({"test": "compensation_and_outbox", "status": "passed"})


def test_06_reconciliation_and_audit():
    notifier = Notifier()
    svc = RankingService(notifier, log_path=os.path.join(LOGS_PATH, "log_post.txt"))

    # prime outbox with two failed events
    bad_notifier = Notifier()
    bad_notifier.set_behavior({"mode": "always_fail"})
    svc_bad = RankingService(bad_notifier, log_path=os.path.join(LOGS_PATH, "log_post.txt"))
    svc_bad.process_request(TEST_DATA["multiple_ties_complex"])  # fails and leaves outbox

    # move events to main svc outbox for reconciliation demo
    svc.outbox.extend(svc_bad.outbox)

    # now make publisher succeed and reconcile
    notifier.set_behavior({"mode": "always_succeed"})
    res = svc.reconcile_outbox()

    assert res["outbox_remaining"] == 0
    assert res["reconciled"] >= 1

    METRICS["tests_run"].append({"test": "reconciliation_and_audit", "status": "passed", "reconciled": res["reconciled"]})


def test_99_export_results():
    # Summarize and write artifacts for CI/one-click inspection
    summary = {
        "results": {
            "tests_executed": len(METRICS["tests_run"]),
            "tests": METRICS["tests_run"]
        },
        "metrics": {
            "retry_counts": METRICS.get("retry_counts", []),
            "collected_at": int(time.time())
        }
    }

    write_results_artifacts(summary)

    # Basic acceptance: all tests passed
    assert len(METRICS["tests_run"]) >= 6
