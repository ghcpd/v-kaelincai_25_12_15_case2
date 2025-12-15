#!/usr/bin/env python
"""
Comparison script: v1 (legacy) vs v2 (greenfield)
- Runs both versions on canonical test cases
- Generates correctness and performance diffs
- Outputs CSV + JSON for analysis
"""

import sys
import os
import json
import subprocess
import csv
from pathlib import Path
from datetime import datetime

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'issue_project', 'src'))

from api_handler import get_ranking_service


def run_legacy_system(test_data):
    """Run legacy v1 system on test data."""
    results = []
    
    try:
        # Import legacy system
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "ranking_system",
            os.path.join(
                os.path.dirname(__file__),
                '..',
                'issue_project',
                'src',
                'ranking_system.py'
            )
        )
        legacy_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(legacy_module)
        
        # Run each test case
        for test_case in test_data:
            system = legacy_module.RankingSystem()
            for student in test_case['input']['students']:
                system.add_student(student['name'], student['score'])
            
            rankings = system.get_rankings_dict()
            
            results.append({
                'test_case': test_case['test_case'],
                'description': test_case['description'],
                'rankings': rankings,
                'status': 'SUCCESS'
            })
    except Exception as e:
        print(f"Error running legacy system: {e}")
        import traceback
        traceback.print_exc()
    
    return results


def run_v2_system(test_data):
    """Run v2 system on test data."""
    results = []
    service = get_ranking_service()
    
    for test_case in test_data:
        request = test_case['input']
        request['client_id'] = 'comparison_test'
        
        response, status = service.process_request(request)
        
        if status == 200:
            rankings = [
                {
                    'name': r['name'],
                    'score': r['score'],
                    'rank': r['rank']
                }
                for r in response['results']
            ]
            results.append({
                'test_case': test_case['test_case'],
                'description': test_case['description'],
                'rankings': rankings,
                'statistics': response['statistics'],
                'processing_ms': response['statistics']['processing_ms'],
                'status': 'SUCCESS'
            })
        else:
            results.append({
                'test_case': test_case['test_case'],
                'description': test_case['description'],
                'error': response.get('error_message', 'Unknown error'),
                'status': 'FAILED'
            })
    
    return results


def compare_results(legacy_results, v2_results):
    """Compare legacy vs v2 results."""
    diffs = []
    
    for leg_res, v2_res in zip(legacy_results, v2_results):
        test_case = leg_res['test_case']
        leg_rankings = {r['name']: r['rank'] for r in leg_res.get('rankings', [])}
        v2_rankings = {r['name']: r['rank'] for r in v2_res.get('rankings', [])}
        
        differences = []
        for name in leg_rankings:
            if leg_rankings[name] != v2_rankings.get(name):
                differences.append({
                    'student': name,
                    'v1_rank': leg_rankings[name],
                    'v2_rank': v2_rankings.get(name),
                    'diff': v2_rankings.get(name, 0) - leg_rankings[name]
                })
        
        diffs.append({
            'test_case': test_case,
            'description': leg_res['description'],
            'has_differences': len(differences) > 0,
            'difference_count': len(differences),
            'differences': differences,
            'v2_processing_ms': v2_res.get('processing_ms', 0),
            'v2_tie_groups': v2_res.get('statistics', {}).get('tie_groups', [])
        })
    
    return diffs


def main():
    """Main comparison function."""
    print("=" * 70)
    print("Ranking Service: v1 (Legacy) vs v2 (Greenfield) Comparison")
    print("=" * 70)
    print()
    
    # Load test data
    test_data_path = os.path.join(
        os.path.dirname(__file__),
        'data',
        'test_data.json'
    )
    
    with open(test_data_path, 'r') as f:
        test_data = json.load(f)
    
    print(f"Loaded {len(test_data)} test cases from {test_data_path}")
    print()
    
    # Run both systems
    print("Running Legacy v1 System...")
    legacy_results = run_legacy_system(test_data)
    print(f"✓ Completed: {len(legacy_results)} tests")
    print()
    
    print("Running Greenfield v2 System...")
    v2_results = run_v2_system(test_data)
    print(f"✓ Completed: {len(v2_results)} tests")
    print()
    
    # Compare results
    print("Comparing Results...")
    comparison_results = compare_results(legacy_results, v2_results)
    
    # Print summary
    print()
    print("=" * 70)
    print("COMPARISON SUMMARY")
    print("=" * 70)
    
    total_tests = len(comparison_results)
    tests_with_diffs = sum(1 for r in comparison_results if r['has_differences'])
    total_differences = sum(r['difference_count'] for r in comparison_results)
    
    print(f"Total Tests:       {total_tests}")
    print(f"Tests with Diffs:  {tests_with_diffs} ({100*tests_with_diffs/total_tests:.1f}%)")
    print(f"Total Differences: {total_differences}")
    print()
    
    # Print detailed diffs
    print("Detailed Differences:")
    print("-" * 70)
    
    for diff in comparison_results:
        if diff['has_differences']:
            print(f"\n[{diff['test_case']}] {diff['description']}")
            print(f"  Differences: {diff['difference_count']}")
            
            for d in diff['differences']:
                print(f"    {d['student']}: v1={d['v1_rank']} → v2={d['v2_rank']} "
                      f"({'FIXED' if d['diff'] < 0 else 'REGRESSED'})")
            
            if diff['v2_tie_groups']:
                print(f"  Tie Groups in v2: {len(diff['v2_tie_groups'])}")
                for tg in diff['v2_tie_groups']:
                    print(f"    - Score {tg['score']}: {tg['count']} students, rank {tg['rank']}")
    
    # Save results to file
    results_path = os.path.join(
        os.path.dirname(__file__),
        'results',
        'comparison_results.json'
    )
    
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    
    output_data = {
        'timestamp': datetime.utcnow().isoformat(),
        'legacy_results': legacy_results,
        'v2_results': v2_results,
        'comparison': comparison_results,
        'summary': {
            'total_tests': total_tests,
            'tests_with_diffs': tests_with_diffs,
            'total_differences': total_differences
        }
    }
    
    with open(results_path, 'w') as f:
        json.dump(output_data, f, indent=2)
    
    print()
    print(f"Results saved to: {results_path}")
    print()
    print("=" * 70)


if __name__ == '__main__':
    main()
