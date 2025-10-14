"""
Support utilities, constants, and helper functions for GradGuide.
Extracted from main.py to avoid circular imports in blueprint pattern.
"""
from rapidfuzz import process, fuzz
from extractors import FIRM_ALIASES

# File paths
data_file = 'submissions.json'
tracker_file = 'applications.json'

# University distribution data for law firms
FIRM_UNIVERSITY_DATA = {
    'Allens': {
        'University of Melbourne': 25,
        'Monash University': 10,
        'University of Sydney': 20,
        'UNSW': 15,
        'University of Queensland': 10,
        'Australian National University': 10,
        'Macquarie University': 5,
        'University of Adelaide': 2,
        'Other': 3
    },
    'Clayton Utz': {
        'University of Melbourne': 20,
        'Monash University': 15,
        'University of Sydney': 20,
        'UNSW': 15,
        'University of Queensland': 10,
        'Australian National University': 10,
        'Macquarie University': 5,
        'University of Adelaide': 3,
        'Other': 2
    },
    'Herbert Smith Freehills': {
        'University of Melbourne': 25,
        'Monash University': 10,
        'University of Sydney': 20,
        'UNSW': 15,
        'University of Queensland': 10,
        'Australian National University': 10,
        'Macquarie University': 5,
        'University of Adelaide': 2,
        'Other': 3
    },
    'Ashurst': {
        'University of Melbourne': 20,
        'Monash University': 15,
        'University of Sydney': 20,
        'UNSW': 15,
        'University of Queensland': 10,
        'Australian National University': 10,
        'Macquarie University': 5,
        'University of Adelaide': 2,
        'Other': 3
    },
    'MinterEllison': {
        'University of Melbourne': 15,
        'Monash University': 20,
        'University of Sydney': 15,
        'UNSW': 15,
        'University of Queensland': 10,
        'Australian National University': 10,
        'Macquarie University': 10,
        'University of Adelaide': 2,
        'Other': 3
    },
    'King & Wood Mallesons': {
        'University of Melbourne': 25,
        'Monash University': 10,
        'University of Sydney': 25,
        'UNSW': 15,
        'University of Queensland': 10,
        'Australian National University': 10,
        'Macquarie University': 2,
        'University of Adelaide': 1,
        'Other': 2
    },
    'Corrs Chambers Westgarth': {
        'University of Melbourne': 20,
        'Monash University': 15,
        'University of Sydney': 20,
        'UNSW': 15,
        'University of Queensland': 10,
        'Australian National University': 10,
        'Macquarie University': 5,
        'University of Adelaide': 2,
        'Other': 3
    },
    'Gilbert + Tobin': {
        'University of Melbourne': 10,
        'Monash University': 5,
        'University of Sydney': 30,
        'UNSW': 30,
        'University of Queensland': 5,
        'Australian National University': 10,
        'Macquarie University': 5,
        'University of Adelaide': 1,
        'Other': 4
    },
    'Lander & Rogers': {
        'University of Melbourne': 35,
        'Monash University': 25,
        'University of Sydney': 5,
        'UNSW': 5,
        'University of Queensland': 5,
        'Australian National University': 10,
        'Macquarie University': 5,
        'University of Adelaide': 5,
        'Other': 5
    },
    'Colin Biggers & Paisley': {
        'University of Melbourne': 20,
        'Monash University': 20,
        'University of Sydney': 10,
        'UNSW': 10,
        'University of Queensland': 10,
        'Australian National University': 10,
        'Macquarie University': 10,
        'University of Adelaide': 5,
        'Other': 5
    }
}


def normalize_company_name(company_name: str) -> str:
    """Normalize company name using firm aliases to handle spaces, nicknames, and variations."""
    if not company_name:
        return company_name

    normalized_input = company_name.strip().lower()

    # Check for exact matches in canonical names
    for canonical_name in FIRM_ALIASES.keys():
        if canonical_name.lower() == normalized_input:
            return canonical_name

    # Check against aliases
    for canonical_name, aliases in FIRM_ALIASES.items():
        for alias in aliases:
            if alias.lower() == normalized_input:
                return canonical_name

    # Handle common spacing variations
    normalized_spaced = normalized_input.replace('&', ' & ').replace('+', ' + ')
    normalized_spaced = ' '.join(normalized_spaced.split())

    for canonical_name, aliases in FIRM_ALIASES.items():
        if canonical_name.lower().replace('&', ' & ').replace('+', ' + ') == normalized_spaced:
            return canonical_name
        for alias in aliases:
            if alias.lower().replace('&', ' & ').replace('+', ' + ') == normalized_spaced:
                return canonical_name

    # Fuzzy matching as fallback for typos
    search_pool = []
    canonical_mapping = {}
    
    for canonical_name, aliases in FIRM_ALIASES.items():
        search_pool.append(canonical_name.lower())
        canonical_mapping[canonical_name.lower()] = canonical_name
        for alias in aliases:
            search_pool.append(alias.lower())
            canonical_mapping[alias.lower()] = canonical_name
    
    result = process.extractOne(
        normalized_input, 
        search_pool, 
        scorer=fuzz.ratio,
        score_cutoff=85
    )
    
    if result:
        matched_name, score, _ = result
        canonical = canonical_mapping.get(matched_name)
        if canonical:
            print(f"Fuzzy match: '{company_name}' → '{canonical}' (score: {score})")
            return canonical
    
    return company_name.strip().title()


def is_helpful_advice(advice_text: str) -> bool:
    """Check if advice text is actually helpful and actionable."""
    if not advice_text or len(advice_text.strip()) < 20:
        return False

    advice_lower = advice_text.lower()

    # Exclude questions
    if (advice_text.strip().endswith('?') or any(q in advice_lower for q in [
            'does that mean', 'what does', 'how does', 'why does', 'is it',
            'are they', 'do you', 'did you', 'have you', 'will they',
            'would you', 'can you', 'could you', 'i wonder', 'wondering if'
    ])):
        return False

    # Exclude non-actionable statements
    if any(na in advice_lower for na in [
            'i think', 'i believe', 'in my opinion', 'it seems',
            'appears to be', 'i heard', 'rumor', 'supposedly', 'allegedly',
            'not sure if', 'unclear', 'partnership doesn\'t have',
            'doesn\'t mean', 'probably', 'likely'
    ]):
        return False

    # Must contain actionable advice indicators
    advice_indicators = [
        'recommend', 'suggest', 'should', 'must', 'need to', 'make sure',
        'prepare', 'practice', 'research', 'apply early', 'tailor', 'focus on',
        'emphasize', 'avoid', 'don\'t', 'be sure to', 'remember to',
        'consider', 'try to'
    ]

    return any(indicator in advice_lower for indicator in advice_indicators)
