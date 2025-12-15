# Known Issue Detailed Analysis

## Issue Identification

**Issue ID:** RANK-001  
**Issue Type:** Functional Bug - Algorithm Logic Error  
**Discovered Date:** 2025-12-12  
**Severity:** Medium  
**Status:** Open (Pending Fix)

---

## Problem Overview

The student grade ranking system incorrectly calculates subsequent ranks when handling tied scores. The system uses array indices directly as ranks instead of calculating ranks based on the actual number of people ahead, violating standard ranking rules.

---

## Reproduction Steps

### Minimal Reproduction Scenario

```python
from src.ranking_system import RankingSystem

system = RankingSystem()
system.add_student("Alice", 95)
system.add_student("Bob", 95)
system.add_student("Charlie", 90)

rankings = system.get_rankings_dict()
print(rankings[2]["rank"])  # Output: 3 (Wrong! Should be 2)
```

### Automated Test Reproduction

```powershell
pytest tests/test_ranking.py::TestRankingSystem::test_two_students_tied_first_place -v
```

---

## Expected vs Actual Behavior

### Example 1: Two Students Tied for First

| Name    | Score | Expected Rank | Actual Rank | Status |
|---------|-------|---------------|-------------|--------|
| Alice   | 95    | 1             | 1           | ✅     |
| Bob     | 95    | 1             | 2           | ❌     |
| Charlie | 90    | 2             | 3           | ❌     |

### Example 2: Multiple Tied Groups

| Name | Score | Expected Rank | Actual Rank | Status       |
|------|-------|---------------|-------------|--------------|
| A    | 95    | 1             | 1           | ✅           |
| B    | 95    | 1             | 2           | ❌           |
| C    | 85    | 3             | 3           | ✅ (By luck) |
| D    | 85    | 3             | 4           | ❌           |
| E    | 85    | 3             | 5           | ❌           |
| F    | 80    | 6             | 6           | ✅ (By luck) |

---

## Root Cause Analysis

### Problem Code Location

**File:** `src/ranking_system.py`  
**Line:** 37  
**Function:** `RankingSystem.calculate_rankings()`

### Current Implementation (Incorrect)

```python
def calculate_rankings(self) -> List[Student]:
    sorted_students = sorted(self.students, key=lambda s: s.score, reverse=True)
    
    # 🐛 Problem: Uses index directly, doesn't consider ties
    for index, student in enumerate(sorted_students):
        student.rank = index + 1  # index=0→rank=1, index=1→rank=2...
    
    return sorted_students
```

### Problem Analysis

1. **Using Index as Rank**
   - `enumerate()` returns an `index` starting from 0 and incrementing
   - Each student's rank = `index + 1`
   - Index increments even when scores are the same

2. **Ignoring Score Comparison**
   - No comparison between adjacent students' scores
   - No tracking of "current expected rank"

3. **Violating Ranking Rules**
   - Standard Competition Ranking rules:
     - Same score → same rank
     - Next different score → rank = total people ahead + 1

---

## Fix Approaches

### Approach 1: Track Previous Score and Rank

```python
def calculate_rankings(self) -> List[Student]:
    sorted_students = sorted(self.students, key=lambda s: s.score, reverse=True)
    
    current_rank = 1  # Current rank
    
    for index, student in enumerate(sorted_students):
        if index > 0 and student.score < sorted_students[index - 1].score:
            # When score changes, rank = index + 1
            current_rank = index + 1
        
        student.rank = current_rank
    
    return sorted_students
```

### Approach 2: Group-based Counting

```python
from itertools import groupby

def calculate_rankings(self) -> List[Student]:
    sorted_students = sorted(self.students, key=lambda s: s.score, reverse=True)
    
    position = 0
    for score, group in groupby(sorted_students, key=lambda s: s.score):
        group_list = list(group)
        rank = position + 1  # Rank for current group
        
        for student in group_list:
            student.rank = rank
        
        position += len(group_list)  # Update position count
    
    return sorted_students
```

### Approach 3: Explicit Counting

```python
def calculate_rankings(self) -> List[Student]:
    sorted_students = sorted(self.students, key=lambda s: s.score, reverse=True)
    
    prev_score = None
    current_rank = 1
    people_count = 0  # Number of people already ranked
    
    for student in sorted_students:
        people_count += 1
        
        if student.score != prev_score:
            # Update rank when score changes
            current_rank = people_count
        
        student.rank = current_rank
        prev_score = student.score
    
    return sorted_students
```

---

## Test Verification

After fixing, all tests should pass:

```powershell
pytest tests/test_ranking.py -v
```

Expected results:
```
test_simple_ranking_no_ties PASSED
test_two_students_tied_first_place PASSED ← Currently failing
test_multiple_ties_complex PASSED ← Currently failing
test_all_students_same_score PASSED ← Currently failing
test_with_json_data PASSED ← Currently failing
test_invalid_score_negative PASSED
test_invalid_score_over_100 PASSED
```

---

## Impact Assessment

### Functional Impact
- ✅ No ties: Works correctly
- ❌ With ties: Incorrect ranking

### Business Impact
- Scholarship awards may be unfair
- Honor roll displays incorrect
- Student rights affected

### Security Impact
- No security risks
- No data leakage concerns

---

## Related Standards

**Standard Competition Ranking:**
- 1224 ranking: Three first (1,1,1), next is fourth (4)
- **This project should follow:** Ties consume ranks, subsequent ranks continuous
  - Example: Two first (1,1), next is second (2)

**Other Ranking Methods Comparison:**
- **Modified Competition Ranking:** 1,1,3,4...
- **Dense Ranking:** 1,1,2,3... (doesn't consume ranks)
- **Ordinal Ranking:** 1,2,3,4... (ignores ties)

This project's bug: Implemented "ordinal ranking" but business requires "dense ranking".

---

## Appendix: Test Coverage Matrix

| Test Scenario       | Current Status | After Fix     |
|---------------------|----------------|---------------|
| No ties             | ✅ PASS        | ✅ PASS       |
| Two tied for first  | ❌ FAIL        | ✅ PASS       |
| Multiple tied groups| ❌ FAIL        | ✅ PASS       |
| All same score      | ❌ FAIL        | ✅ PASS       |
| JSON data           | ❌ FAIL        | ✅ PASS       |
| Input validation    | ✅ PASS        | ✅ PASS       |

---

**Last Updated:** 2025-12-12  
**Analyst:** AI Engineer
