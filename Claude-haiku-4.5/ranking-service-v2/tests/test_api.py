"""
Integration tests for Ranking Service v2
- Tests all 7 scenarios from architecture design
- Validates idempotency, error handling, performance
"""

import sys
import os
import json
import pytest
from datetime import datetime

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from models import (
    RequestState,
    ErrorCode,
    StudentInput,
    RankingStrategy
)
from api_handler import get_ranking_service
from idempotency import get_idempotency_store
from observability import get_request_logger, get_metrics


class TestIntegration:
    """Integration test suite."""
    
    def setup_method(self):
        """Setup before each test."""
        # Get service instance
        self.service = get_ranking_service()
        self.idempotency_store = get_idempotency_store()
        self.metrics = get_metrics()
    
    # Test 1: Basic No-Tie Ranking
    def test_001_no_ties(self):
        """Test basic ranking without ties."""
        request = {
            "request_id": "test-001",
            "students": [
                {"name": "Alice", "score": 90},
                {"name": "Bob", "score": 80},
                {"name": "Charlie", "score": 70}
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 200
        assert response["status"] == "SUCCESS"
        assert len(response["results"]) == 3
        
        # Verify ranks
        assert response["results"][0]["rank"] == 1
        assert response["results"][1]["rank"] == 2
        assert response["results"][2]["rank"] == 3
        
        # Verify statistics
        assert response["statistics"]["total_students"] == 3
        assert response["statistics"]["unique_scores"] == 3
        assert len(response["statistics"]["tie_groups"]) == 0
    
    # Test 2: Tied First Place (CRITICAL BUG SCENARIO)
    def test_002_tied_first_place(self):
        """Test tied students for first place (main bug test)."""
        request = {
            "request_id": "test-002",
            "students": [
                {"name": "Alice", "score": 95},
                {"name": "Bob", "score": 95},
                {"name": "Charlie", "score": 90}
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 200
        assert response["status"] == "SUCCESS"
        
        # CRITICAL: Both Alice and Bob should have rank 1
        result_by_name = {r["name"]: r for r in response["results"]}
        assert result_by_name["Alice"]["rank"] == 1, \
            "Alice should be rank 1"
        assert result_by_name["Bob"]["rank"] == 1, \
            "Bob should be rank 1 (tied with Alice)"
        assert result_by_name["Charlie"]["rank"] == 2, \
            "Charlie should be rank 2 (not 3!)"
        
        # Verify tie group detection
        tie_groups = response["statistics"]["tie_groups"]
        assert len(tie_groups) == 1
        assert tie_groups[0]["score"] == 95
        assert tie_groups[0]["count"] == 2
        assert tie_groups[0]["rank"] == 1
    
    # Test 3: Multiple Tie Groups
    def test_003_multiple_tie_groups(self):
        """Test complex scenario with multiple tied groups."""
        request = {
            "request_id": "test-003",
            "students": [
                {"name": "A", "score": 95},
                {"name": "B", "score": 95},
                {"name": "C", "score": 85},
                {"name": "D", "score": 85},
                {"name": "E", "score": 85},
                {"name": "F", "score": 80}
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 200
        assert response["status"] == "SUCCESS"
        
        result_by_name = {r["name"]: r for r in response["results"]}
        
        # Verify rank assignments (DENSE ranking: same score = same rank, next different = next sequential)
        assert result_by_name["A"]["rank"] == 1
        assert result_by_name["B"]["rank"] == 1
        assert result_by_name["C"]["rank"] == 2  # DENSE: next sequential rank after 1
        assert result_by_name["D"]["rank"] == 2
        assert result_by_name["E"]["rank"] == 2
        assert result_by_name["F"]["rank"] == 3  # DENSE: next sequential rank after 2
        
        # Verify tie groups
        tie_groups = response["statistics"]["tie_groups"]
        assert len(tie_groups) == 2
        assert tie_groups[0]["score"] == 95
        assert tie_groups[0]["count"] == 2
        assert tie_groups[1]["score"] == 85
        assert tie_groups[1]["count"] == 3
    
    # Test 4: Idempotency (Same Request Twice)
    def test_004_idempotency(self):
        """Test idempotency: duplicate request returns cached result."""
        request = {
            "request_id": "idem-001",
            "students": [
                {"name": "Alice", "score": 95},
                {"name": "Bob", "score": 90}
            ]
        }
        
        # First request
        response1, status1 = self.service.process_request(request)
        assert status1 == 200
        processing_ms1 = response1["statistics"]["processing_ms"]
        
        # Second request (should be cached)
        response2, status2 = self.service.process_request(request)
        assert status2 == 200
        
        # Verify results are identical
        assert response1["results"] == response2["results"]
        assert response1["statistics"]["total_students"] == \
               response2["statistics"]["total_students"]
        
        # Note: Cached response should have minimal processing time
        # (This is logged but not directly in response in this implementation)
    
    # Test 5: Validation Error (Invalid Score)
    def test_005_validation_error(self):
        """Test validation: reject invalid scores."""
        request = {
            "request_id": "test-005",
            "students": [
                {"name": "Alice", "score": 150}  # Invalid: > 100
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 400
        assert response["status"] == "FAILED"
        assert response["error_code"] == "VALIDATION_ERROR"
        assert len(response["validation_errors"]) > 0
        
        # Check error details
        errors = response["validation_errors"]
        score_error = [e for e in errors if "score" in e["field"]]
        assert len(score_error) > 0
        assert "out of range" in score_error[0]["message"]
    
    # Test 6: Validation Error (Negative Score)
    def test_006_negative_score(self):
        """Test validation: reject negative scores."""
        request = {
            "request_id": "test-006",
            "students": [
                {"name": "Bob", "score": -10}
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 400
        assert response["status"] == "FAILED"
        assert response["error_code"] == "VALIDATION_ERROR"
    
    # Test 7: All Same Score (Everyone Tied for First)
    def test_007_all_same_score(self):
        """Test all students with identical scores."""
        request = {
            "request_id": "test-007",
            "students": [
                {"name": f"Student{i}", "score": 90}
                for i in range(5)
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 200
        assert response["status"] == "SUCCESS"
        
        # All should have rank 1
        for result in response["results"]:
            assert result["rank"] == 1, \
                f"{result['name']} should be rank 1"
        
        # Verify tie group
        tie_groups = response["statistics"]["tie_groups"]
        assert len(tie_groups) == 1
        assert tie_groups[0]["count"] == 5
        assert tie_groups[0]["rank"] == 1


class TestErrorHandling:
    """Test error handling and edge cases."""
    
    def setup_method(self):
        """Setup before each test."""
        self.service = get_ranking_service()
    
    def test_missing_request_id(self):
        """Test validation: missing request_id."""
        request = {
            "students": [{"name": "Alice", "score": 90}]
            # No request_id
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 400
        assert response["error_code"] == "VALIDATION_ERROR"
    
    def test_missing_students(self):
        """Test validation: missing students list."""
        request = {
            "request_id": "test-error-1"
            # No students
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 400
        assert response["error_code"] == "VALIDATION_ERROR"
    
    def test_empty_students_list(self):
        """Test validation: empty students list."""
        request = {
            "request_id": "test-error-2",
            "students": []
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 400
        assert response["error_code"] == "VALIDATION_ERROR"
    
    def test_missing_student_name(self):
        """Test validation: missing student name."""
        request = {
            "request_id": "test-error-3",
            "students": [
                {"score": 90}  # Missing name
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 400
        assert response["error_code"] == "VALIDATION_ERROR"
    
    def test_missing_student_score(self):
        """Test validation: missing student score."""
        request = {
            "request_id": "test-error-4",
            "students": [
                {"name": "Alice"}  # Missing score
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 400
        assert response["error_code"] == "VALIDATION_ERROR"
    
    def test_non_numeric_score(self):
        """Test validation: non-numeric score."""
        request = {
            "request_id": "test-error-5",
            "students": [
                {"name": "Alice", "score": "ninety"}
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 400
        assert response["error_code"] == "VALIDATION_ERROR"


class TestMetrics:
    """Test metrics collection."""
    
    def setup_method(self):
        """Setup before each test."""
        self.service = get_ranking_service()
        self.metrics = get_metrics()
    
    def test_metrics_collection(self):
        """Test that metrics are collected correctly."""
        request = {
            "request_id": "metrics-test-1",
            "students": [
                {"name": "Alice", "score": 95},
                {"name": "Bob", "score": 95},
                {"name": "Charlie", "score": 90}
            ]
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 200
        
        # Get metrics
        metrics_summary = self.metrics.get_summary()
        
        assert metrics_summary["requests_total"] > 0
        assert metrics_summary["requests_success"] > 0
        assert "processing_latency_ms" in metrics_summary


class TestRankingStrategies:
    """Test different ranking strategies."""
    
    def setup_method(self):
        """Setup before each test."""
        self.service = get_ranking_service()
    
    def test_competition_ranking_default(self):
        """Test COMPETITION ranking (default)."""
        request = {
            "request_id": "strategy-comp-1",
            "students": [
                {"name": "A", "score": 95},
                {"name": "B", "score": 95},
                {"name": "C", "score": 90}
            ],
            "ranking_strategy": "COMPETITION"
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 200
        result_by_name = {r["name"]: r for r in response["results"]}
        
        # Competition: 1, 1, 3
        assert result_by_name["A"]["rank"] == 1
        assert result_by_name["B"]["rank"] == 1
        assert result_by_name["C"]["rank"] == 3
    
    def test_dense_ranking(self):
        """Test DENSE ranking."""
        request = {
            "request_id": "strategy-dense-1",
            "students": [
                {"name": "A", "score": 95},
                {"name": "B", "score": 95},
                {"name": "C", "score": 90}
            ],
            "ranking_strategy": "DENSE"
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 200
        result_by_name = {r["name"]: r for r in response["results"]}
        
        # Dense: 1, 1, 2
        assert result_by_name["A"]["rank"] == 1
        assert result_by_name["B"]["rank"] == 1
        assert result_by_name["C"]["rank"] == 2
    
    def test_ordinal_ranking(self):
        """Test ORDINAL ranking."""
        request = {
            "request_id": "strategy-ord-1",
            "students": [
                {"name": "A", "score": 95},
                {"name": "B", "score": 95},
                {"name": "C", "score": 90}
            ],
            "ranking_strategy": "ORDINAL"
        }
        
        response, status = self.service.process_request(request)
        
        assert status == 200
        result_by_name = {r["name"]: r for r in response["results"]}
        
        # Ordinal: 1, 2, 3
        assert result_by_name["A"]["rank"] == 1
        assert result_by_name["B"]["rank"] == 2
        assert result_by_name["C"]["rank"] == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
