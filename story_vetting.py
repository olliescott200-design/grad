"""
Automated story vetting system to ensure quality submissions
"""

def is_productive_story(submission_data):
    """
    Check if a story submission is productive and valuable
    Returns: (is_valid, rejection_reason)
    
    NEW APPROACH: Accept if ANY Step 2 field has meaningful content
    """
    
    # Get ALL possible Step 2 content fields
    step2_fields = [
        submission_data.get('timeline', '').strip(),
        submission_data.get('online_application', '').strip(),
        submission_data.get('online_assessment', '').strip(),
        submission_data.get('interview_rounds', '').strip(),
        submission_data.get('assessment_centre', '').strip(),
        submission_data.get('what_went_well', '').strip(),
        submission_data.get('what_could_improve', '').strip(),
        submission_data.get('advice', '').strip(),
        submission_data.get('final_thoughts', '').strip(),
        submission_data.get('salary', '').strip()
    ]
    
    # Check if ANY field has content
    has_any_content = any(field for field in step2_fields if len(field) > 0)
    
    if not has_any_content:
        return False, "Please fill in at least one field in Step 2 to share your experience."
    
    # Get the longest field (the one with most content)
    longest_field = max(step2_fields, key=len)
    
    # Very minimal validation - just check it's not a super short question
    if longest_field.endswith('?') and len(longest_field.split()) < 3:
        return False, "Please share your experience rather than just asking a question."
    
    # Accept everything else - trust users to provide valuable content
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
