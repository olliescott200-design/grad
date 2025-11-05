"""
Intelligent submission vetting system to ensure quality contributions
Uses multi-factor scoring to evaluate authenticity and usefulness
"""

import re

def is_productive_story(submission_data):
    """
    Intelligent content quality assessment using multiple signals
    Returns: (is_valid, rejection_reason)
    """
    
    # Get ALL Step 2 content fields
    step2_fields = {
        'timeline': submission_data.get('timeline', '').strip(),
        'online_application': submission_data.get('online_application', '').strip(),
        'online_assessment': submission_data.get('online_assessment', '').strip(),
        'interview_rounds': submission_data.get('interview_rounds', '').strip(),
        'assessment_centre': submission_data.get('assessment_centre', '').strip(),
        'what_went_well': submission_data.get('what_went_well', '').strip(),
        'what_could_improve': submission_data.get('what_could_improve', '').strip(),
        'advice': submission_data.get('advice', '').strip(),
        'final_thoughts': submission_data.get('final_thoughts', '').strip(),
        'salary': submission_data.get('salary', '').strip()
    }
    
    # Combine all non-empty fields for analysis
    all_content = ' '.join([field for field in step2_fields.values() if field])
    
    # Rule 1: Must have SOME content
    if not all_content or len(all_content) < 3:
        return False, "Please fill in at least one field in Step 2 to share your experience."
    
    # Rule 2: Reject pure questions with no experience
    question_count = all_content.count('?')
    word_count = len(all_content.split())
    if question_count >= 2 and word_count < 15:
        return False, "Please share your experience rather than just asking questions."
    
    # Rule 3: Check for spam/irrelevant patterns
    spam_patterns = [
        r'\b(buy|sale|discount|offer|click here|visit|website)\b',
        r'http[s]?://',  # URLs (usually spam)
        r'\b(viagra|casino|lottery|prize)\b'
    ]
    content_lower = all_content.lower()
    for pattern in spam_patterns:
        if re.search(pattern, content_lower):
            return False, "Please share genuine graduate experiences only."
    
    # Rule 4: Detect extremely generic/low-effort content
    ultra_generic = [
        r'^(good luck|best wishes|hope this helps)[\s\.\!]*$',
        r'^(thanks|thank you|cheers)[\s\.\!]*$',
        r'^(ok|okay|cool|nice)[\s\.\!]*$'
    ]
    if word_count < 4:
        for pattern in ultra_generic:
            if re.match(pattern, content_lower):
                return False, "Please provide more detailed insights from your experience."
    
    # Calculate quality score (0-100)
    quality_score = calculate_quality_score(all_content, step2_fields)
    
    # Rule 5: Minimum quality threshold (score must be >= 25/100)
    if quality_score < 25:
        return False, "Please provide more specific details from your personal experience to help other students."
    
    return True, None


def calculate_quality_score(content, fields_dict):
    """
    Calculate content quality score based on multiple factors
    Returns: score (0-100)
    """
    score = 0
    word_count = len(content.split())
    
    # Factor 1: Content length (0-25 points)
    if word_count >= 50:
        score += 25
    elif word_count >= 30:
        score += 20
    elif word_count >= 15:
        score += 15
    elif word_count >= 8:
        score += 10
    elif word_count >= 4:
        score += 5
    
    # Factor 2: Personal experience indicators (0-25 points)
    personal_indicators = [
        r'\bI\b', r'\bmy\b', r'\bme\b', r'\bmine\b',
        r'\bwe\b', r'\bour\b', r'\bus\b',
        r'\bwas\b', r'\bdid\b', r'\bhad\b', r'\bgot\b'
    ]
    personal_count = sum(1 for indicator in personal_indicators 
                        if re.search(indicator, content, re.IGNORECASE))
    if personal_count >= 5:
        score += 25
    elif personal_count >= 3:
        score += 15
    elif personal_count >= 1:
        score += 8
    
    # Factor 3: Specific details (0-25 points)
    specificity_indicators = [
        r'\d+',  # Numbers
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\b',
        r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\b',
        r'\b(week|month|day|hour)\b',
        r'\b(round|stage|interview|assessment|test)\b',
        r'\b(CV|resume|cover letter|transcript|portfolio)\b'
    ]
    specificity_count = sum(1 for indicator in specificity_indicators 
                           if re.search(indicator, content, re.IGNORECASE))
    if specificity_count >= 5:
        score += 25
    elif specificity_count >= 3:
        score += 15
    elif specificity_count >= 1:
        score += 8
    
    # Factor 4: Multiple fields filled (0-15 points)
    filled_fields = sum(1 for field in fields_dict.values() if field and len(field) > 3)
    if filled_fields >= 4:
        score += 15
    elif filled_fields >= 3:
        score += 10
    elif filled_fields >= 2:
        score += 5
    
    # Factor 5: Actionable advice indicators (0-10 points)
    advice_indicators = [
        r'\b(recommend|suggest|advice|tip|prepare|practice|study|research)\b',
        r'\b(make sure|be sure to|don\'t forget|remember to)\b',
        r'\b(helpful|useful|important|key|crucial|essential)\b'
    ]
    advice_count = sum(1 for indicator in advice_indicators 
                      if re.search(indicator, content, re.IGNORECASE))
    if advice_count >= 3:
        score += 10
    elif advice_count >= 1:
        score += 5
    
    return min(100, score)


def check_duplicate_content(new_submission, existing_submissions):
    """
    Check if the new submission is too similar to existing ones
    Returns: (is_duplicate, similar_company)
    """
    
    # Get content from new submission
    new_advice = new_submission.get('advice', '').strip().lower()
    new_company = new_submission.get('company', '').strip()
    
    if not new_advice or len(new_advice) < 10:
        return False, None
    
    # Check against existing submissions from same company
    for existing in existing_submissions:
        if existing.get('company', '').strip() != new_company:
            continue
            
        existing_advice = existing.get('advice', '').strip().lower()
        
        # Simple similarity check - if 80%+ of words match
        if existing_advice and len(existing_advice) > 10:
            new_words = set(new_advice.split())
            existing_words = set(existing_advice.split())
            
            if len(new_words) > 0:
                overlap = len(new_words & existing_words) / len(new_words)
                if overlap > 0.8:
                    return True, new_company
    
    return False, None


def get_quality_score(submission_data):
    """
    Calculate a quality score for the submission (0-100)
    Higher scores = better quality
    """
    score = 50  # Start at 50
    
    advice = submission_data.get('advice', '').strip()
    what_went_well = submission_data.get('what_went_well', '').strip()
    what_could_improve = submission_data.get('what_could_improve', '').strip()
    
    # Bonus for having advice
    if advice and len(advice.split()) >= 10:
        score += 20
    
    # Bonus for what went well
    if what_went_well and len(what_went_well.split()) >= 8:
        score += 15
    
    # Bonus for improvement areas
    if what_could_improve and len(what_could_improve.split()) >= 8:
        score += 15
    
    # Bonus for specific details
    if any(keyword in advice.lower() for keyword in ['specific', 'practice area', 'interview', 'assessment', 'prepared', 'research']):
        score += 10
    
    return min(100, score)
