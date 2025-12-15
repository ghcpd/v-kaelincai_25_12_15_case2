# Student Ranking System (With Known Bug)

## Project Overview

This is a minimal reproducible project for a school grade management system with **a deliberately planted simple ranking calculation bug**, designed to demonstrate a Functional Bug.

## Problem Description

**Bug Type:** Incorrect ranking calculation for tied scores (Off-by-one in ranking logic)

**Manifestation:**
- When multiple students have the same score, they should receive the same rank
- The next student with a different score should have rank = "total people ahead + 1"
- **Actual Behavior:** The code uses array indices as ranks directly, causing non-consecutive ranks after ties

**Example:**
```
Student Scores: Alice 95, Bob 95, Charlie 90
Expected Ranks: Rank 1, Rank 1, Rank 2
Actual Ranks: Rank 1, Rank 2, Rank 3 ❌ (Wrong!)
```

## Project Structure

```
issue_project/
├── src/
│   ├── __init__.py
│   └── ranking_system.py      # Core code (contains bug)
├── tests/
│   ├── __init__.py
│   └── test_ranking.py        # Test cases (will fail)
├── data/
│   └── students.json          # Sample data
├── requirements.txt
├── README.md
└── KNOWN_ISSUE.md            # Detailed problem analysis
```

## Quick Start

### 1. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 2. Run Tests (Will Fail)

```powershell
pytest tests/test_ranking.py -v
```

### 3. Run Main Program to See Bug

```powershell
python src/ranking_system.py
```

**Expected Output (with bug):**
```
Student Ranking Results:
----------------------------------------
Rank 1: Alice - 95 points
Rank 2: Bob - 95 points  ← Should be Rank 1!
Rank 3: Charlie - 90 points  ← Should be Rank 2!
```

## Test Description

The project contains 5 test cases:

✅ **test_simple_ranking_no_ties** - No ties scenario (Pass)  
❌ **test_two_students_tied_first_place** - Two students tied for first (Fail)  
❌ **test_multiple_ties_complex** - Multiple groups of ties (Fail)  
❌ **test_all_students_same_score** - All same score (Fail)  
❌ **test_with_json_data** - Using JSON data (Fail)  
✅ **test_invalid_score_negative** - Input validation (Pass)  
✅ **test_invalid_score_over_100** - Input validation (Pass)

## Bug Root Cause

**File:** [src/ranking_system.py](src/ranking_system.py#L37)  
**Function:** `RankingSystem.calculate_rankings()`  
**Problematic Code:**

```python
for index, student in enumerate(sorted_students):
    student.rank = index + 1  # 🐛 Uses index directly, doesn't handle ties
```

**Correct Logic Should:**
- Track "current rank" and "number of people ranked"
- Same score → same rank
- Different score → rank = number of people ranked + 1

## Impact Scope

- **Functional Impact:** Scholarship awards and honor rolls may be unfair
- **Severity:** Medium (affects fairness and accuracy)
- **Complexity:** Simple (single-point logic error)

## Tech Stack

- Python 3.8+
- pytest 7.4+
- Windows 11 (compatible with other systems)

## Related Documentation

For detailed problem analysis, see [KNOWN_ISSUE.md](KNOWN_ISSUE.md)
