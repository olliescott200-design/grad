"""
Automated story vetting system to ensure quality submissions
"""

def is_productive_story(submission_data):
    """
    Check if a story submission is productive and valuable
    Returns: (is_valid, rejection_reason)
    """
    
    # Get key fields
    advice = submission_data.get('advice', '').strip()
    what_went_well = submission_data.get('what_went_well', '').strip()
    what_could_improve = submission_data.get('what_could_improve', '').strip()
    
    # Combine all text content for checking
    all_content = f"{advice} {what_went_well} {what_could_improve}".strip()
    
    # Rule 1: Check minimum content length (relaxed to 5 characters)
    if len(all_content) < 5:
        return False, "Please provide some information to help other students."
    
    # Rule 2: Reject if it's ONLY a very short question (more lenient)
    if all_content.endswith('?') and len(all_content.split()) < 5:
        return False, "Please share your experience or advice rather than asking questions."
    
    # Rule 3: Check for conversation snippets (more lenient - 10 words)
    if all_content.startswith('"') or all_content.startswith("'"):
        if len(all_content.split()) < 10:
            return False, "Please provide complete advice rather than conversation snippets."
    
    # Rule 4: Reject generic/templated responses (more lenient - only very short generic ones)
    generic_phrases = [
        "be genuine in your interest, prepare thoroughly, and show enthusiasm for learning",
        "be genuine and prepare thoroughly"
    ]
    
    content_lower = all_content.lower()
    for phrase in generic_phrases:
        if phrase == content_lower.strip():  # Only exact matches of generic templates
            return False, "Please share specific, personalized advice from your experience."
    
    # Rule 5: Check for minimum meaningful words (relaxed to 2 words)
    meaningful_words = [word for word in all_content.split() if len(word) > 3]
    if len(meaningful_words) < 2:
        return False, "Please provide a bit more detail."
    
    return True, None


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
