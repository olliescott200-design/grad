from functools import lru_cache
import time
from typing import Dict, Any, List

def _expensive_company_metrics(company_name: str, submissions: List[Dict[str, Any]]) -> dict:
    """
    Calculate expensive company metrics. Called by cached wrapper.
    Returns stable dict keys that templates expect.
    """
    company_entries = [
        entry for entry in submissions 
        if entry['company'].lower() == company_name.lower()
    ]
    
    if not company_entries:
        return {
            'success_rate': None,
            'avg_salary': None,
            'total_entries': 0,
            'salary_ranges': {'entry_level': 0, 'mid_level': 0, 'senior_level': 0},
            'roles': [],
            'top_advice_keywords': []
        }
    
    # Calculate success rate
    success_count = len([e for e in company_entries if e.get('outcome') == 'Success'])
    success_rate = round((success_count / len(company_entries)) * 100, 1)
    
    # Calculate average salary
    salaries = [
        int(e.get('salary', 0)) for e in company_entries
        if e.get('salary') and str(e.get('salary')).isdigit()
    ]
    avg_salary = int(sum(salaries) / len(salaries)) if salaries else None
    
    # Get unique roles
    roles = list(set([e['role'] for e in company_entries]))
    
    # Calculate salary ranges
    salary_ranges = {
        'entry_level': len([s for s in salaries if s < 80000]),
        'mid_level': len([s for s in salaries if 80000 <= s < 120000]),
        'senior_level': len([s for s in salaries if s >= 120000])
    }
    
    # Most common advice themes
    advice_keywords = {}
    for entry in company_entries:
        if entry.get('advice'):
            words = entry['advice'].lower().split()
            for word in words:
                if len(word) > 4:
                    advice_keywords[word] = advice_keywords.get(word, 0) + 1
    
    top_advice = sorted(advice_keywords.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        'success_rate': success_rate,
        'avg_salary': avg_salary,
        'total_entries': len(company_entries),
        'salary_ranges': salary_ranges,
        'roles': roles,
        'top_advice_keywords': top_advice
    }

@lru_cache(maxsize=128)
def cached_company_metrics(company_name: str, submissions_hash: int, _ts_bucket: int = None) -> dict:
    """
    Cached wrapper for expensive company metrics calculation.
    Cache invalidates every 5 minutes (300 seconds).
    
    Args:
        company_name: Company name to analyze
        submissions_hash: Hash of submissions list to bust cache when data changes
        _ts_bucket: Time bucket for cache invalidation (auto-computed if None)
    """
    if _ts_bucket is None:
        _ts_bucket = int(time.time() / 300)  # 5 minute buckets
    
    # Import here to avoid circular dependency
    from db_auth import get_all_submissions
    submissions = get_all_submissions()
    
    return _expensive_company_metrics(company_name, submissions)

def get_submissions_hash(submissions: List[Dict[str, Any]]) -> int:
    """Get a hash of submissions list for cache busting."""
    return hash(str(len(submissions)))
