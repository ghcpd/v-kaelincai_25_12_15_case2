"""
Test the grade ranking system
These test cases will expose the ranking calculation bug
"""

import sys
import os
import json
import pytest

# Add src directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from ranking_system import RankingSystem, Student


class TestRankingSystem:
    """Test ranking system"""
    
    def setup_method(self):
        """Initialize before each test"""
        self.system = RankingSystem()
    
    def test_simple_ranking_no_ties(self):
        """Test ranking without ties - should pass"""
        self.system.add_student("Alice", 90)
        self.system.add_student("Bob", 80)
        self.system.add_student("Charlie", 70)
        
        rankings = self.system.get_rankings_dict()
        
        assert rankings[0]["rank"] == 1
        assert rankings[1]["rank"] == 2
        assert rankings[2]["rank"] == 3
    
    def test_two_students_tied_first_place(self):
        """
        Test two students tied for first place - will fail!
        Alice 95, Bob 95, Charlie 90
        Expected: Rank 1, Rank 1, Rank 2
        Actual: Rank 1, Rank 2, Rank 3 (Wrong!)
        """
        self.system.add_student("Alice", 95)
        self.system.add_student("Bob", 95)
        self.system.add_student("Charlie", 90)
        
        rankings = self.system.get_rankings_dict()
        
        # First two should both be rank 1
        assert rankings[0]["rank"] == 1, f"First student should be rank 1, actual is rank {rankings[0]['rank']}"
        assert rankings[1]["rank"] == 1, f"Second student should be rank 1 (tied), actual is rank {rankings[1]['rank']}"
        
        # 🚨 This assertion will fail! System outputs rank 3 instead of rank 2
        assert rankings[2]["rank"] == 2, f"Charlie should be rank 2, actual is rank {rankings[2]['rank']}"
    
    def test_multiple_ties_complex(self):
        """
        Test complex scenario with multiple tied groups - will fail!
        Two at 95 (Rank 1)
        Three at 85 (Rank 3)
        One at 80 (Rank 6)
        """
        self.system.add_student("A", 95)
        self.system.add_student("B", 95)
        self.system.add_student("C", 85)
        self.system.add_student("D", 85)
        self.system.add_student("E", 85)
        self.system.add_student("F", 80)
        
        rankings = self.system.get_rankings_dict()
        
        # Check tied for rank 1
        assert rankings[0]["rank"] == 1
        assert rankings[1]["rank"] == 1
        
        # 🚨 These assertions will fail!
        # Three with 85 should be rank 3 (2 people ahead), not ranks 3, 4, 5
        assert rankings[2]["rank"] == 3, f"First 85 should be rank 3, actual is rank {rankings[2]['rank']}"
        assert rankings[3]["rank"] == 3, f"Second 85 should be rank 3, actual is rank {rankings[3]['rank']}"
        assert rankings[4]["rank"] == 3, f"Third 85 should be rank 3, actual is rank {rankings[4]['rank']}"
        
        # 80 should be rank 6 (5 people ahead), not rank 6
        assert rankings[5]["rank"] == 6, f"80 should be rank 6, actual is rank {rankings[5]['rank']}"
    
    def test_all_students_same_score(self):
        """
        Test all students with same score - will fail!
        All should be rank 1
        """
        for i in range(5):
            self.system.add_student(f"Student{i}", 90)
        
        rankings = self.system.get_rankings_dict()
        
        # 🚨 Only the first will be rank 1, others will be 2, 3, 4, 5
        for i, rank_info in enumerate(rankings):
            assert rank_info["rank"] == 1, f"All students should be rank 1, student {i} is rank {rank_info['rank']}"
    
    def test_with_json_data(self):
        """Test with JSON data file - will fail!"""
        data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'students.json')
        
        with open(data_path, 'r', encoding='utf-8') as f:
            students_data = json.load(f)
        
        for student in students_data:
            self.system.add_student(student['name'], student['score'])
        
        rankings = self.system.get_rankings_dict()
        
        # Two with 95 should be rank 1
        assert rankings[0]["rank"] == 1
        assert rankings[1]["rank"] == 1
        
        # 🚨 90 should be rank 3 (2 people ahead), not rank 3
        assert rankings[2]["rank"] == 3, f"90 should be rank 3, actual is rank {rankings[2]['rank']}"
        
        # Three with 85 should all be rank 4 (3 people ahead)
        assert rankings[3]["rank"] == 4
        assert rankings[4]["rank"] == 4
        assert rankings[5]["rank"] == 4
        
        # 🚨 80 should be rank 7 (6 people ahead), not rank 7
        assert rankings[6]["rank"] == 7


class TestInputValidation:
    """Test input validation - these should pass"""
    
    def setup_method(self):
        self.system = RankingSystem()
    
    def test_invalid_score_negative(self):
        """Test negative score"""
        with pytest.raises(ValueError):
            self.system.add_student("Alice", -10)
    
    def test_invalid_score_over_100(self):
        """Test score over 100"""
        with pytest.raises(ValueError):
            self.system.add_student("Bob", 150)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
