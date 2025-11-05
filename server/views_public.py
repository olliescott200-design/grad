"""
Public-facing routes blueprint for GradGuide.
All user-accessible pages and API endpoints.
"""
from flask import Blueprint, render_template, request, redirect, url_for, jsonify, send_file, session, flash
from datetime import datetime, date
import json
import os
import re
import csv
from collections import defaultdict, Counter

# Import from existing modules
from grad_data import load_cards, load_grad_signals
from grad_data_v2 import load_cards as load_cards_v2
from legal_config import LEGAL_CONFIG, NOT_ADVICE_DISCLAIMER
from db_auth import (
    get_user_applications, create_application, update_application,
    delete_application, get_all_submissions, create_submission, 
    get_all_applications
)
from auth_utils import (
    get_current_user, login_required, create_user,
    authenticate_user, login_user, logout_user
)
from extractors import FIRM_ALIASES
from security import get_replit_user


def create_blueprint(limiter):
    """Create and configure the public routes blueprint."""
    bp = Blueprint("public", __name__)
    
    # Import utility functions from support module
    from server.support import (
        normalize_company_name, is_helpful_advice,
        FIRM_UNIVERSITY_DATA, data_file, tracker_file
    )
    
    @bp.route('/healthz')
    @bp.route('/api/health')
    def healthz():
        """Health check endpoint for monitoring."""
        return jsonify(ok=True, status="healthy")
    
    @bp.route('/')
    def index():
        """Homepage with company listings and stats."""
        current_user = get_current_user()
        user_id = current_user['id'] if current_user else None
        user_name = current_user['username'] if current_user else None

        submissions = get_all_submissions()

        # Group submissions by company for homepage
        companies = {}
        for submission in submissions:
            company = submission['company']
            if company not in companies:
                companies[company] = {
                    'name': company,
                    'total_submissions': 0,
                    'success_count': 0,
                    'avg_salary': 0,
                    'salary_count': 0,
                    'recent_roles': set()
                }

            companies[company]['total_submissions'] += 1
            if submission.get('outcome') == 'Success':
                companies[company]['success_count'] += 1

            salary = submission.get('salary', '')
            if salary and str(salary).isdigit():
                companies[company]['avg_salary'] += int(salary)
                companies[company]['salary_count'] += 1

            companies[company]['recent_roles'].add(submission['role'])

        # Calculate averages and format data
        for company_data in companies.values():
            if company_data['salary_count'] > 0:
                company_data['avg_salary'] = int(company_data['avg_salary'] / company_data['salary_count'])
            else:
                company_data['avg_salary'] = None

            if company_data['total_submissions'] > 0:
                company_data['success_rate'] = round(
                    (company_data['success_count'] / company_data['total_submissions']) * 100, 1)
            else:
                company_data['success_rate'] = 0
                
            company_data['recent_roles'] = list(company_data['recent_roles'])[:3]
            company_data['total_stories'] = company_data['total_submissions']

        companies_with_stories = [c for c in companies.values() if c['total_stories'] > 0]
        sorted_companies = sorted(companies_with_stories, key=lambda x: x['total_stories'], reverse=True)
        total_stories = sum(c['total_stories'] for c in companies_with_stories)

        firms = load_cards("out/grad_program_signals.csv")
        companies_lookup = {company['name']: company for company in sorted_companies}

        return render_template('index.html',
                               companies=companies_lookup,
                               sorted_companies=sorted_companies,
                               total_submissions=len(submissions),
                               total_stories=total_stories,
                               firms=firms,
                               user_id=user_id,
                               user_name=user_name)

    @bp.route('/auth_required')
    def auth_required():
        """Page shown when authentication is required."""
        return render_template('auth_required.html')

    @bp.route('/login', methods=['GET', 'POST'])
    @limiter.limit("10 per minute")
    def login():
        """User login page and handler."""
        if get_current_user():
            return redirect(url_for('public.index'))
        
        if request.method == 'POST':
            login_input = request.form.get('login', '').strip()
            password = request.form.get('password', '')
            
            if not login_input or not password:
                flash('Please enter both username/email and password.', 'error')
                return render_template('login.html')
            
            user = authenticate_user(login_input, password)
            if user:
                login_user(user['id'])
                flash(f'Welcome back, {user["first_name"] or user["username"]}!', 'success')
                
                next_page = request.form.get('next') or request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('public.index'))
            else:
                flash('Invalid username/email or password. Account may be locked after 5 failed attempts.', 'error')
        
        return render_template('login.html')

    @bp.route('/register', methods=['GET', 'POST'])
    @limiter.limit("5 per minute")
    def register():
        """User registration page and handler."""
        if get_current_user():
            return redirect(url_for('public.index'))
            
        if request.method == 'POST':
            email = request.form.get('email', '').strip().lower()
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()
            
            if not all([email, username, password, confirm_password]):
                flash('Please fill in all required fields.', 'error')
                return render_template('register.html')
                
            if password != confirm_password:
                flash('Passwords do not match.', 'error')
                return render_template('register.html')
            
            success, result = create_user(email, username, password, first_name, last_name)
            
            if success:
                flash('Account created successfully! Please log in.', 'success')
                return redirect(url_for('public.login'))
            else:
                flash(result, 'error')
                
        return render_template('register.html')

    @bp.route('/logout')
    def logout():
        """Log out the current user."""
        logout_user()
        flash('You have been logged out successfully.', 'success')
        return redirect(url_for('public.index'))

    @bp.route('/submit', methods=['GET', 'POST'])
    @limiter.limit("30 per hour")
    @login_required
    def submit():
        """Experience submission form."""
        current_user = get_current_user()
        if not current_user:
            flash('Please log in to submit an experience.', 'error')
            return redirect(url_for('public.login'))
        user_id = current_user['id']
        user_name = current_user['username']

        if request.method == 'POST':
            from story_vetting import is_productive_story, check_duplicate_content
            
            original_company = request.form['company']
            normalized_company = normalize_company_name(original_company)

            submission_data = {
                'company': normalized_company,
                'role': request.form['role'],
                'theme': request.form.get('theme', ''),
                'application_year': request.form.get('application_year', ''),
                'location': request.form.get('location', ''),
                'university': request.form.get('university', ''),
                'outcome': request.form.get('outcome', ''),
                'rating': request.form.get('rating', ''),
                'difficulty': request.form.get('difficulty', ''),
                'num_stages': request.form.get('num_stages', ''),
                'timeline': request.form.get('timeline', ''),
                'online_application': request.form.get('online_application', ''),
                'online_assessment': request.form.get('online_assessment', ''),
                'interview_rounds': request.form.get('interview_rounds', ''),
                'assessment_centre': request.form.get('assessment_centre', ''),
                'what_went_well': request.form.get('what_went_well', ''),
                'what_could_improve': request.form.get('what_could_improve', ''),
                'advice': request.form.get('advice', ''),
                'salary': request.form.get('salary', ''),
                'final_thoughts': request.form.get('final_thoughts', '')
            }
            
            is_valid, rejection_reason = is_productive_story(submission_data)
            company_list = sorted(list(FIRM_ALIASES.keys()))
            if not is_valid:
                flash(f'Story not submitted: {rejection_reason}', 'error')
                return render_template("submit.html", user_id=user_id, user_name=user_name, 
                                       form_data=submission_data, company_list=company_list)
            
            existing_submissions = get_all_submissions()
            is_duplicate, duplicate_company = check_duplicate_content(submission_data, existing_submissions)
            if is_duplicate:
                flash(f'This story appears very similar to an existing {duplicate_company} submission. '
                      'Please share unique insights from your personal experience.', 'error')
                return render_template("submit.html", user_id=user_id, user_name=user_name,
                                       form_data=submission_data, company_list=company_list)
            
            create_submission(user_id, submission_data)
            flash('✅ Success! Your experience has been shared and will help thousands of students.', 'success')
            return render_template("submit.html", user_id=user_id, user_name=user_name,
                                   company_list=company_list, submission_success=True, 
                                   submitted_data=submission_data)

        company_list = sorted(list(FIRM_ALIASES.keys()))
        return render_template("submit.html", user_id=user_id, user_name=user_name, company_list=company_list)

    @bp.route('/company/<name>')
    def company_page(name):
        """Individual company profile page."""
        from categorizer import classify_text, label, LABELS
        
        data = get_all_submissions()
        company_entries = [entry for entry in data if entry['company'].lower() == name.lower()]
        
        all_categories = set()
        for entry in company_entries:
            if entry.get('categories'):
                all_categories.update(entry['categories'])
        
        category_labels = {slug: LABELS.get(slug, slug.replace('_', ' ').title()) 
                          for slug in all_categories}

        firms = load_cards_v2("out/grad_program_signals.csv")
        firm_data = None
        for firm in firms:
            if firm['name'].lower() == name.lower():
                firm_data = firm
                firm_data['experiences'] = []
                firm_data['total_experiences'] = 0
                break

        if company_entries:
            success_count = len([e for e in company_entries if e.get('outcome') == 'Success'])
            success_rate = round((success_count / len(company_entries)) * 100, 1)

            salaries = [int(e.get('salary', 0)) for e in company_entries
                        if e.get('salary') and str(e.get('salary')).isdigit()]
            avg_salary = int(sum(salaries) / len(salaries)) if salaries else None

            roles = list(set([e['role'] for e in company_entries]))

            university_breakdown = None
            if name in FIRM_UNIVERSITY_DATA:
                university_breakdown = FIRM_UNIVERSITY_DATA[name]

            salary_ranges = {
                'entry_level': len([s for s in salaries if s < 80000]),
                'mid_level': len([s for s in salaries if 80000 <= s < 120000]),
                'senior_level': len([s for s in salaries if s >= 120000])
            }

            advice_keywords = {}
            for entry in company_entries:
                if entry.get('advice'):
                    words = entry['advice'].lower().split()
                    for word in words:
                        if len(word) > 4:
                            advice_keywords[word] = advice_keywords.get(word, 0) + 1

            top_advice = sorted(advice_keywords.items(), key=lambda x: x[1], reverse=True)[:5]

            company_stats = {
                'success_rate': success_rate,
                'avg_salary': avg_salary,
                'salary_ranges': salary_ranges,
                'roles': roles,
                'total_entries': len(company_entries),
                'university_breakdown': university_breakdown,
                'top_advice_keywords': top_advice
            }
        else:
            company_stats = None

        return render_template('company.html',
                               company=name,
                               entries=company_entries,
                               stats=company_stats,
                               firm_data=firm_data,
                               category_labels=category_labels)

    @bp.route('/companies')
    def companies():
        """Companies directory page."""
        submissions = get_all_submissions()
        companies_dict = {}
        for submission in submissions:
            company = submission['company']
            if company not in companies_dict:
                companies_dict[company] = {
                    'name': company,
                    'total_submissions': 0,
                    'success_count': 0,
                    'experiences': [],
                    'recent_roles': set(),
                    'avg_salary': 0,
                    'salary_count': 0
                }
            companies_dict[company]['total_submissions'] += 1
            if submission.get('outcome') == 'Success':
                companies_dict[company]['success_count'] += 1
            salary = submission.get('salary', '')
            if salary and str(salary).isdigit():
                companies_dict[company]['avg_salary'] += int(salary)
                companies_dict[company]['salary_count'] += 1
            companies_dict[company]['recent_roles'].add(submission['role'])
            companies_dict[company]['experiences'].append(submission)

        for company_data in companies_dict.values():
            if company_data['salary_count'] > 0:
                company_data['avg_salary'] = int(company_data['avg_salary'] / company_data['salary_count'])
            else:
                company_data['avg_salary'] = None
            if company_data['total_submissions'] > 0:
                company_data['success_rate'] = round(
                    (company_data['success_count'] / company_data['total_submissions']) * 100, 1)
            else:
                company_data['success_rate'] = 0
            company_data['recent_roles'] = list(company_data['recent_roles'])[:3]
            company_data['experiences'] = company_data['experiences'][:5]
            company_data['total_stories'] = company_data['total_submissions']

        companies_with_stories = [c for c in companies_dict.values() if c['total_stories'] > 0]
        firms = sorted(companies_with_stories, key=lambda x: x['total_stories'], reverse=True)
        return render_template("companies.html", firms=firms)

    @bp.route('/api/grad-data')
    def api_grad_data():
        """API endpoint for grad program data."""
        return jsonify({"firms": load_cards("out/grad_program_signals.csv")})

    @bp.route('/experiences')
    def experiences():
        """All experiences page."""
        with open(data_file, 'r') as f:
            submissions = json.load(f)
        experience_items = []
        for sub in submissions:
            content_parts = []
            if sub.get('application_stages'):
                content_parts.append(f"Application: {sub['application_stages']}")
            if sub.get('interview_experience'):
                content_parts.append(f"Interview: {sub['interview_experience']}")
            main_content = " • ".join(content_parts) if content_parts else ""
            advice_text = sub.get('advice', '').strip()
            if advice_text and advice_text not in main_content and is_helpful_advice(advice_text):
                if main_content:
                    main_content += f" • Advice: {advice_text}"
                else:
                    main_content = f"Advice: {advice_text}"
            experience_items.append({
                "content": main_content,
                "firm_name": sub['company'],
                "quality_score": 0.95,
                "primary_cat": sub.get('theme', 'other').lower().replace(' ', '_'),
                "cat_labels": [sub.get('theme', 'Other')],
                "is_submission": True,
                "experience_type": sub.get('experience_type', ''),
                "role": sub.get('role', ''),
                "timestamp": sub.get('timestamp', ''),
                "user_name": sub.get('user_name', 'Anonymous'),
                "source": sub.get('source', 'user'),
                "pro_tip": sub.get('pro_tip', ''),
                "advice": advice_text
            })
        experience_items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return render_template("experiences.html", experiences=experience_items, is_filtered=True)

    @bp.route('/tracker')
    @login_required
    def tracker():
        """Application tracker dashboard."""
        current_user = get_current_user()
        if not current_user:
            flash('Please log in to access tracker.', 'error')
            return redirect(url_for('public.login'))
        user_id = current_user['id']
        user_name = current_user['username']
        applications = get_user_applications(user_id)
        return render_template('tracker.html', applications=applications, user_id=user_id, user_name=user_name)

    @bp.route('/tracker/add', methods=['POST'])
    @login_required
    def add_application():
        """Add new application to tracker."""
        current_user = get_current_user()
        if not current_user:
            flash('Please log in to add applications.', 'error')
            return redirect(url_for('public.login'))
        user_id = current_user['id']
        application_data = {
            'user_id': user_id,
            'company': request.form['company'],
            'role': request.form['role'],
            'application_date': request.form['application_date'] if request.form['application_date'] else None,
            'university': request.form.get('university', ''),
            'wam': request.form.get('wam', ''),
            'status': request.form['status'],
            'response_date': request.form.get('response_date', '') if request.form.get('response_date') else None,
            'priority': request.form.get('priority', 'Medium'),
            'notes': request.form.get('notes', '')
        }
        create_application(user_id, application_data)
        return redirect(url_for('public.tracker'))

    @bp.route('/tracker/update/<int:app_id>', methods=['POST'])
    @login_required
    def update_application_route(app_id):
        """Update application status."""
        current_user = get_current_user()
        if not current_user:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        user_id = current_user['id']
        update_data = {}
        if request.json:
            if 'status' in request.json:
                update_data['status'] = request.json['status']
            if 'response_date' in request.json:
                update_data['response_date'] = request.json['response_date'] if request.json['response_date'] else None
            if 'notes' in request.json:
                update_data['notes'] = request.json['notes']
            if 'priority' in request.json:
                update_data['priority'] = request.json['priority']
        updated_app = update_application(app_id, user_id, update_data)
        if updated_app:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Application not found or access denied'}), 404

    @bp.route('/tracker/delete/<int:app_id>', methods=['DELETE'])
    @login_required
    def delete_application_route(app_id):
        """Delete application from tracker."""
        current_user = get_current_user()
        if not current_user:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        user_id = current_user['id']
        success = delete_application(app_id, user_id)
        if success:
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Application not found or access denied'}), 404

    # Legal pages
    @bp.route('/terms')
    def terms():
        return render_template('terms.html', config=LEGAL_CONFIG)

    @bp.route('/privacy')
    def privacy():
        return render_template('privacy.html', config=LEGAL_CONFIG)

    @bp.route('/moderation')
    def moderation():
        return render_template('moderation.html', config=LEGAL_CONFIG)

    @bp.route('/report')
    def report():
        return render_template('report.html', config=LEGAL_CONFIG)

    @bp.route('/law-match', methods=['GET', 'POST'])
    def law_match():
        """Career matching tool to recommend firms based on user profile"""
        if request.method == 'POST':
            # Get form data
            uni = request.form.get('uni', '').strip()
            wam = float(request.form.get('wam', 0))
            interest = request.form.get('interest', '')
            preference = request.form.get('preference', '')
            experience = request.form.get('experience', '')
            location = request.form.get('location', 'any')
            
            # Firm profiles with attributes for matching
            firm_profiles = {
                'Allens': {
                    'prestige': 95, 'salary': 95, 'worklife': 60, 'training': 90,
                    'strengths': ['commercial', 'banking', 'litigation', 'infrastructure'],
                    'locations': ['melbourne', 'sydney', 'brisbane', 'perth'],
                    'wam_cutoff': 75
                },
                'Herbert Smith Freehills': {
                    'prestige': 95, 'salary': 95, 'worklife': 60, 'training': 90,
                    'strengths': ['commercial', 'banking', 'litigation', 'infrastructure', 'competition'],
                    'locations': ['melbourne', 'sydney', 'brisbane', 'perth'],
                    'wam_cutoff': 75
                },
                'King & Wood Mallesons': {
                    'prestige': 95, 'salary': 95, 'worklife': 65, 'training': 88,
                    'strengths': ['commercial', 'banking', 'infrastructure', 'competition'],
                    'locations': ['melbourne', 'sydney', 'brisbane', 'perth'],
                    'wam_cutoff': 75
                },
                'Clayton Utz': {
                    'prestige': 90, 'salary': 90, 'worklife': 70, 'training': 88,
                    'strengths': ['commercial', 'litigation', 'employment', 'property', 'infrastructure'],
                    'locations': ['melbourne', 'sydney', 'brisbane', 'perth', 'adelaide'],
                    'wam_cutoff': 72
                },
                'Gilbert + Tobin': {
                    'prestige': 92, 'salary': 92, 'worklife': 65, 'training': 90,
                    'strengths': ['commercial', 'competition', 'litigation', 'tax'],
                    'locations': ['sydney', 'melbourne'],
                    'wam_cutoff': 75
                },
                'MinterEllison': {
                    'prestige': 88, 'salary': 88, 'worklife': 72, 'training': 85,
                    'strengths': ['commercial', 'property', 'employment', 'government'],
                    'locations': ['melbourne', 'sydney', 'brisbane', 'adelaide', 'perth'],
                    'wam_cutoff': 70
                },
                'Corrs Chambers Westgarth': {
                    'prestige': 88, 'salary': 88, 'worklife': 70, 'training': 85,
                    'strengths': ['commercial', 'banking', 'litigation', 'property'],
                    'locations': ['melbourne', 'sydney', 'brisbane', 'perth'],
                    'wam_cutoff': 72
                },
                'Ashurst': {
                    'prestige': 85, 'salary': 85, 'worklife': 70, 'training': 82,
                    'strengths': ['commercial', 'banking', 'infrastructure'],
                    'locations': ['melbourne', 'sydney', 'brisbane'],
                    'wam_cutoff': 72
                },
                'Lander & Rogers': {
                    'prestige': 75, 'salary': 75, 'worklife': 85, 'training': 80,
                    'strengths': ['property', 'commercial', 'family', 'employment'],
                    'locations': ['melbourne'],
                    'wam_cutoff': 65
                },
                'Colin Biggers & Paisley': {
                    'prestige': 70, 'salary': 72, 'worklife': 82, 'training': 78,
                    'strengths': ['property', 'employment', 'commercial', 'family', 'criminal'],
                    'locations': ['sydney', 'melbourne', 'brisbane'],
                    'wam_cutoff': 65
                }
            }
            
            # Calculate match scores for each firm
            matches = []
            for firm_name, profile in firm_profiles.items():
                score = 0
                reasons = []
                
                # University match (30 points)
                uni_data = FIRM_UNIVERSITY_DATA.get(firm_name, {})
                uni_percentage = uni_data.get(uni, uni_data.get('Other', 0))
                if uni_percentage >= 15:
                    score += 30
                    reasons.append(f"Strong {uni} representation ({uni_percentage}%)")
                elif uni_percentage >= 8:
                    score += 20
                    reasons.append(f"Good {uni} representation ({uni_percentage}%)")
                elif uni_percentage >= 3:
                    score += 10
                    reasons.append(f"Some {uni} representation ({uni_percentage}%)")
                
                # WAM competitiveness (25 points)
                wam_cutoff = profile['wam_cutoff']
                if wam >= wam_cutoff + 10:
                    score += 25
                    reasons.append(f"Well above typical WAM ({wam_cutoff})")
                elif wam >= wam_cutoff + 5:
                    score += 20
                    reasons.append(f"Above typical WAM ({wam_cutoff})")
                elif wam >= wam_cutoff:
                    score += 15
                    reasons.append(f"Meets WAM expectations ({wam_cutoff})")
                elif wam >= wam_cutoff - 5:
                    score += 10
                    reasons.append(f"Competitive WAM (typical ~{wam_cutoff})")
                else:
                    score += 5
                    reasons.append(f"WAM below typical ({wam_cutoff})")
                
                # Practice area match (20 points)
                if interest in profile['strengths']:
                    score += 20
                    area_name = interest.replace('_', ' ').title()
                    reasons.append(f"Strong in {area_name}")
                elif interest == 'other':
                    score += 10
                
                # Preference match (15 points)
                pref_score = profile.get(preference, 70)
                if pref_score >= 90:
                    score += 15
                    reasons.append(f"Excellent for {preference.replace('worklife', 'work-life balance').replace('_', ' ')}")
                elif pref_score >= 80:
                    score += 12
                    reasons.append(f"Very good for {preference.replace('worklife', 'work-life balance').replace('_', ' ')}")
                elif pref_score >= 70:
                    score += 8
                    reasons.append(f"Good for {preference.replace('worklife', 'work-life balance').replace('_', ' ')}")
                else:
                    score += 5
                
                # Location match (10 points)
                if location == 'any' or location in profile['locations']:
                    score += 10
                    if location != 'any':
                        reasons.append(f"Has {location.title()} office")
                
                # Store match
                if score > 0:  # Only include firms with some match
                    matches.append({
                        'firm': firm_name,
                        'score': score,
                        'percentage': min(100, int((score / 100) * 100)),
                        'reasons': reasons,
                        'profile': profile
                    })
            
            # Sort by score
            matches.sort(key=lambda x: x['score'], reverse=True)
            
            # Take top 8 matches
            top_matches = matches[:8]
            
            return render_template('law_match_results.html', 
                                   matches=top_matches,
                                   user_profile={
                                       'uni': uni,
                                       'wam': wam,
                                       'interest': interest,
                                       'preference': preference,
                                       'experience': experience,
                                       'location': location
                                   })
        
        return render_template('law_match.html')

    return bp
