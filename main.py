from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, session, flash
from datetime import datetime, date
import json
import os
import re
import csv
from collections import defaultdict, Counter
from grad_data import load_cards, load_grad_signals
from grad_data_v2 import load_cards as load_cards_v2
from legal_config import LEGAL_CONFIG, NOT_ADVICE_DISCLAIMER
from db_auth import (get_user_applications,
                     create_application, update_application,
                     delete_application, get_all_submissions,
                     create_submission, get_all_applications)
from auth_utils import (get_current_user, login_required, create_user, 
                       authenticate_user, login_user, logout_user)
from extractors import FIRM_ALIASES
from security import harden_app, get_replit_user


def normalize_company_name(company_name: str) -> str:
    """Normalize company name using firm aliases to handle spaces, nicknames, and variations."""
    if not company_name:
        return company_name

    # Clean the input
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
    normalized_spaced = normalized_input.replace('&',
                                                 ' & ').replace('+', ' + ')
    normalized_spaced = ' '.join(normalized_spaced.split())  # Normalize spaces

    for canonical_name, aliases in FIRM_ALIASES.items():
        # Check canonical with normalized spacing
        if canonical_name.lower().replace('&', ' & ').replace(
                '+', ' + ') == normalized_spaced:
            return canonical_name
        # Check aliases with normalized spacing
        for alias in aliases:
            if alias.lower().replace('&', ' & ').replace(
                    '+', ' + ') == normalized_spaced:
                return canonical_name

    # Return original if no match found (but title case it)
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


# Load data from JSON file
data_file = 'submissions.json'

app = Flask(__name__)
limiter = harden_app(app)

# Validate SECRET_KEY is properly set
secret_key = app.config.get("SECRET_KEY")
if secret_key in (None, "", "change-me", "please_change_me"):
    import os
    if os.getenv("REPL_SLUG"):  # Only in Replit environment for now
        print("WARNING: Using default SECRET_KEY in development. Set SECRET_KEY environment variable for production.")
    else:
        raise RuntimeError("SECRET_KEY must be set via environment")

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

# Load existing data or create empty
if not os.path.exists(data_file):
    with open(data_file, 'w') as f:
        json.dump([], f)

if not os.path.exists(tracker_file):
    with open(tracker_file, 'w') as f:
        json.dump([], f)


@app.route('/')
def index():
    # Get user info from session
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
            company_data['avg_salary'] = int(company_data['avg_salary'] /
                                             company_data['salary_count'])
        else:
            company_data['avg_salary'] = None

        if company_data['total_submissions'] > 0:
            company_data['success_rate'] = round(
                (company_data['success_count'] / company_data['total_submissions'])
                * 100, 1)
        else:
            company_data['success_rate'] = 0
            
        company_data['recent_roles'] = list(
            company_data['recent_roles'])[:3]  # Show top 3 roles
        
        # Calculate total displayable stories (user submissions only)
        company_data['total_stories'] = company_data['total_submissions']

    # Filter to only companies with actual stories, then sort
    companies_with_stories = [c for c in companies.values() if c['total_stories'] > 0]
    sorted_companies = sorted(companies_with_stories,
                              key=lambda x: x['total_stories'],
                              reverse=True)
    
    # Calculate total stories across all companies
    total_stories = sum(c['total_stories'] for c in companies_with_stories)

    # Load firms from CSV for Explore Companies section
    firms = load_cards("out/grad_program_signals.csv")
    print(f"Loaded {len(firms)} firms from CSV")

    # Create a lookup dictionary for companies data
    companies_lookup = {
        company['name']: company
        for company in sorted_companies
    }

    return render_template('index.html',
                           companies=companies_lookup,
                           sorted_companies=sorted_companies,
                           total_submissions=len(submissions),
                           total_stories=total_stories,
                           firms=firms,
                           user_id=user_id,
                           user_name=user_name)


@app.route('/api/health')
def health():
    return {"status": "ok"}


@app.route('/auth_required')
def auth_required():
    return render_template('auth_required.html')

@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")  # Rate limit login attempts
def login():
    # If user is already logged in, redirect to home
    if get_current_user():
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        login_input = request.form.get('login', '').strip()
        password = request.form.get('password', '')
        
        if not login_input or not password:
            flash('Please enter both username/email and password.', 'error')
            return render_template('login.html')
        
        # Authenticate user
        user = authenticate_user(login_input, password)
        if user:
            login_user(user['id'])
            flash(f'Welcome back, {user["first_name"] or user["username"]}!', 'success')
            
            # Redirect to next page or home
            next_page = request.form.get('next') or request.args.get('next')
            if next_page:
                return redirect(next_page)
            return redirect(url_for('index'))
        else:
            flash('Invalid username/email or password. Account may be locked after 5 failed attempts.', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")  # Rate limit registration attempts  
def register():
    # If user is already logged in, redirect to home
    if get_current_user():
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        
        # Validation
        if not all([email, username, password, confirm_password]):
            flash('Please fill in all required fields.', 'error')
            return render_template('register.html')
            
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')
        
        # Create user
        success, result = create_user(email, username, password, first_name, last_name)
        
        if success:
            flash('Account created successfully! Please log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash(result, 'error')  # result contains error message
            
    return render_template('register.html')

@app.route('/logout')
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'success')
    return redirect(url_for('index'))


@app.route('/submit', methods=['GET', 'POST'])
@limiter.limit("30 per hour")  # Stricter limit for data modification
@login_required
def submit():
    # Get authenticated user info
    current_user = get_current_user()
    if not current_user:
        flash('Please log in to submit an experience.', 'error')
        return redirect(url_for('login'))
    user_id = current_user['id']
    user_name = current_user['username']

    if request.method == 'POST':
        from story_vetting import is_productive_story, check_duplicate_content
        
        # Normalize company name to handle variations
        original_company = request.form['company']
        normalized_company = normalize_company_name(original_company)

        submission_data = {
            # Basic Information
            'company': normalized_company,
            'role': request.form['role'],
            'application_year': request.form.get('application_year', ''),
            'location': request.form.get('location', ''),
            'university': request.form.get('university', ''),
            'outcome': request.form.get('outcome', ''),
            
            # Application Process Overview
            'rating': request.form.get('rating', ''),
            'difficulty': request.form.get('difficulty', ''),
            'num_stages': request.form.get('num_stages', ''),
            'timeline': request.form.get('timeline', ''),
            
            # Application Stages
            'online_application': request.form.get('online_application', ''),
            'online_assessment': request.form.get('online_assessment', ''),
            'interview_rounds': request.form.get('interview_rounds', ''),
            'assessment_centre': request.form.get('assessment_centre', ''),
            
            # Experience Reflection
            'what_went_well': request.form.get('what_went_well', ''),
            'what_could_improve': request.form.get('what_could_improve', ''),
            'advice': request.form.get('advice', ''),
            'salary': request.form.get('salary', ''),
            'final_thoughts': request.form.get('final_thoughts', '')
        }
        
        # Automated vetting - check if story is productive
        is_valid, rejection_reason = is_productive_story(submission_data)
        if not is_valid:
            flash(f'Story not submitted: {rejection_reason}', 'error')
            return render_template("submit.html", user_id=user_id, user_name=user_name, form_data=submission_data)
        
        # Check for duplicate content
        existing_submissions = get_all_submissions()
        is_duplicate, duplicate_company = check_duplicate_content(submission_data, existing_submissions)
        if is_duplicate:
            flash(f'This story appears very similar to an existing {duplicate_company} submission. Please share unique insights from your personal experience.', 'error')
            return render_template("submit.html", user_id=user_id, user_name=user_name, form_data=submission_data)
        
        create_submission(user_id, submission_data)
        flash('Thank you for sharing your experience! Your story will help thousands of students.', 'success')
        return redirect(url_for('index'))

    return render_template("submit.html", user_id=user_id, user_name=user_name)


@app.route('/company/<name>')
def company_page(name):
    from categorizer import classify_text, label

    # Get user-submitted stories from database only
    data = get_all_submissions()
    company_entries = [
        entry for entry in data if entry['company'].lower() == name.lower()
    ]

    # Load firm data from CSV (for company info only, not experiences)
    firms = load_cards_v2("out/grad_program_signals.csv")
    firm_data = None
    for firm in firms:
        if firm['name'].lower() == name.lower():
            firm_data = firm
            # Only show user-submitted experiences, not CSV data
            firm_data['experiences'] = []
            firm_data['total_experiences'] = 0
            break

    # Calculate company stats
    if company_entries:
        success_count = len(
            [e for e in company_entries if e.get('outcome') == 'Success'])
        success_rate = round((success_count / len(company_entries)) * 100, 1)

        salaries = [
            int(e.get('salary', 0)) for e in company_entries
            if e.get('salary') and str(e.get('salary')).isdigit()
        ]
        avg_salary = int(sum(salaries) / len(salaries)) if salaries else None

        roles = list(set([e['role'] for e in company_entries]))

        # Add university breakdown if available
        university_breakdown = None
        if name in FIRM_UNIVERSITY_DATA:
            university_breakdown = FIRM_UNIVERSITY_DATA[name]

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
                    if len(word) > 4:  # Only count meaningful words
                        advice_keywords[word] = advice_keywords.get(word,
                                                                    0) + 1

        top_advice = sorted(advice_keywords.items(),
                            key=lambda x: x[1],
                            reverse=True)[:5]

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
                           firm_data=firm_data)


@app.route('/companies')
def companies():
    submissions = get_all_submissions()

    # Group submissions by company
    companies = {}
    for submission in submissions:
        company = submission['company']
        if company not in companies:
            company_data = {
                'name': company,
                'total_submissions': 0,
                'success_count': 0,
                'experiences': [],
                'recent_roles': set(),
                'avg_salary': 0,
                'salary_count': 0
            }
            companies[company] = company_data

        companies[company]['total_submissions'] += 1
        if submission.get('outcome') == 'Success':
            companies[company]['success_count'] += 1

        salary = submission.get('salary', '')
        if salary and str(salary).isdigit():
            companies[company]['avg_salary'] += int(salary)
            companies[company]['salary_count'] += 1

        companies[company]['recent_roles'].add(submission['role'])
        companies[company]['experiences'].append(submission)

    # Calculate averages and format data
    for company_data in companies.values():
        if company_data['salary_count'] > 0:
            company_data['avg_salary'] = int(company_data['avg_salary'] /
                                             company_data['salary_count'])
        else:
            company_data['avg_salary'] = None

        if company_data['total_submissions'] > 0:
            company_data['success_rate'] = round(
                (company_data['success_count'] / company_data['total_submissions'])
                * 100, 1)
        else:
            company_data['success_rate'] = 0
            
        company_data['recent_roles'] = list(
            company_data['recent_roles'])[:3]  # Show top 3 roles

        # Keep only recent experiences for display
        company_data['experiences'] = company_data['experiences'][:5]
        
        # Calculate total displayable stories (user submissions only)
        company_data['total_stories'] = company_data['total_submissions']

    # Filter to only companies with stories, then sort
    companies_with_stories = [c for c in companies.values() if c['total_stories'] > 0]
    firms = sorted(companies_with_stories,
                   key=lambda x: x['total_stories'],
                   reverse=True)

    return render_template("companies.html", firms=firms)


@app.route('/api/grad-data')
def api_grad_data():
    return jsonify({"firms": load_cards("out/grad_program_signals.csv")})


@app.route('/api/company-analytics/<company_name>')
def api_company_analytics(company_name):
    """Get analytics data for a specific company"""

    all_applications = get_all_applications()

    # Filter applications for this company
    company_apps = [
        app for app in all_applications
        if app.get('company', '').lower() == company_name.lower()
    ]

    if not company_apps:
        return jsonify({'error': 'No data available'})

    # Calculate company stats
    total_apps = len(company_apps)
    responses = [app for app in company_apps if app.get('response_date')]
    offers = [app for app in company_apps if app.get('status') == 'Offered']

    response_times = []
    for app in responses:
        if app.get('application_date') and app.get('response_date'):
            try:
                app_date = datetime.strptime(app['application_date'],
                                             '%Y-%m-%d').date()
                resp_date = datetime.strptime(app['response_date'],
                                              '%Y-%m-%d').date()
                response_times.append((resp_date - app_date).days)
            except:
                pass

    avg_response_time = round(sum(response_times) /
                              len(response_times)) if response_times else 0

    # Enhanced response analytics
    response_rate = round(
        (len(responses) / total_apps * 100), 1) if total_apps > 0 else 0
    offer_rate = round(
        (len(offers) / total_apps * 100), 1) if total_apps > 0 else 0

    # Calculate stage progression rates
    assessment_invites = len([
        app for app in company_apps if app.get('status') in [
            'Online Assessment Received', 'Phone Interview Scheduled',
            'Assessment Centre Invited', 'Offered'
        ]
    ])
    interview_invites = len([
        app for app in company_apps if app.get('status') in
        ['Phone Interview Scheduled', 'Assessment Centre Invited', 'Offered']
    ])

    assessment_rate = round(
        (assessment_invites / total_apps * 100), 1) if total_apps > 0 else 0
    interview_rate = round(
        (interview_invites / total_apps * 100), 1) if total_apps > 0 else 0

    company_stats = {
        'total_apps':
        total_apps,
        'response_rate':
        response_rate,
        'assessment_progression_rate':
        assessment_rate,
        'interview_progression_rate':
        interview_rate,
        'offer_rate':
        offer_rate,
        'avg_response_time':
        avg_response_time,
        'competitiveness_score':
        round((offer_rate / 100) * (response_rate / 100) *
              100, 1) if offer_rate > 0 and response_rate > 0 else 0
    }

    # Calculate university progression for this company
    uni_progression = defaultdict(
        lambda: {
            'Applied': 0,
            'Online Assessment Received': 0,
            'Phone Interview Scheduled': 0,
            'Assessment Centre Invited': 0,
            'Offered': 0
        })

    for app in company_apps:
        if app.get('university'):
            uni = app['university']
            status = app.get('status', 'Applied')
            uni_progression[uni]['Applied'] += 1
            if status in uni_progression[uni]:
                uni_progression[uni][status] += 1

    # Convert to percentage and filter universities with meaningful data
    university_progression = {}
    for uni, stages in uni_progression.items():
        total_applied = stages.get('Applied', 0)
        if total_applied >= 2:  # Minimum threshold
            university_progression[uni] = {
                'total_apps':
                total_applied,
                'assessment_rate':
                round((stages.get('Online Assessment Received', 0) /
                       total_applied * 100), 1) if total_applied > 0 else 0,
                'interview_rate':
                round(((stages.get('Phone Interview Scheduled', 0) +
                        stages.get('Assessment Centre Invited', 0)) /
                       total_applied * 100), 1) if total_applied > 0 else 0,
                'offer_rate':
                round((stages.get('Offered', 0) / total_applied *
                       100), 1) if total_applied > 0 else 0
            }

    return jsonify({
        'company_stats': company_stats if total_apps > 0 else None,
        'university_progression': university_progression
    })


@app.route('/api/company-insights/<company_name>')
def api_company_insights(company_name):
    """Get detailed insights and analytics for a specific company"""

    all_applications = get_all_applications()

    # Filter applications for this company
    company_apps = [
        app for app in all_applications
        if app.get('company', '').lower() == company_name.lower()
    ]

    if not company_apps:
        return jsonify({'error': 'No data available'})

    # Calculate timeline insights
    monthly_apps = defaultdict(int)
    for app in company_apps:
        if app.get('application_date'):
            try:
                app_date = datetime.strptime(app['application_date'],
                                             '%Y-%m-%d').date()
                month_key = app_date.strftime('%Y-%m')
                monthly_apps[month_key] += 1
            except:
                pass

    # Calculate stage progression insights
    stage_counts = defaultdict(int)
    for app in company_apps:
        status = app.get('status', 'Applied')
        stage_counts[status] += 1

    # Enhanced WAM analysis by application stage
    wam_by_stage = {
        'Applied': {
            'samples': [],
            'avg': 0,
            'min': 0,
            'max': 0
        },
        'Online Assessment Received': {
            'samples': [],
            'avg': 0,
            'min': 0,
            'max': 0
        },
        'Phone Interview Scheduled': {
            'samples': [],
            'avg': 0,
            'min': 0,
            'max': 0
        },
        'Assessment Centre Invited': {
            'samples': [],
            'avg': 0,
            'min': 0,
            'max': 0
        },
        'Offered': {
            'samples': [],
            'avg': 0,
            'min': 0,
            'max': 0
        }
    }

    # WAM distribution ranges
    wam_ranges = {'70-74': 0, '75-79': 0, '80-84': 0, '85+': 0, 'Unknown': 0}

    for app in company_apps:
        wam = app.get('wam', '')
        status = app.get('status', 'Applied')

        if wam and str(wam).replace('.', '').isdigit():
            wam_val = float(wam)

            # Add to stage-specific WAM tracking
            if status in wam_by_stage:
                wam_by_stage[status]['samples'].append(wam_val)

            # Add to range distribution
            if wam_val >= 85:
                wam_ranges['85+'] += 1
            elif wam_val >= 80:
                wam_ranges['80-84'] += 1
            elif wam_val >= 75:
                wam_ranges['75-79'] += 1
            elif wam_val >= 70:
                wam_ranges['70-74'] += 1
        else:
            wam_ranges['Unknown'] += 1

    # Calculate WAM statistics for each stage
    wam_requirements = {}
    for stage, data in wam_by_stage.items():
        if data['samples']:
            data['avg'] = round(sum(data['samples']) / len(data['samples']), 1)
            data['min'] = round(min(data['samples']), 1)
            data['max'] = round(max(data['samples']), 1)
            data['count'] = len(data['samples'])
            wam_requirements[stage] = {
                'average_wam': data['avg'],
                'minimum_wam': data['min'],
                'maximum_wam': data['max'],
                'sample_size': data['count']
            }
        else:
            wam_requirements[stage] = {
                'average_wam': 'N/A',
                'minimum_wam': 'N/A',
                'maximum_wam': 'N/A',
                'sample_size': 0
            }

    # Calculate priority distribution
    priority_counts = defaultdict(int)
    for app in company_apps:
        priority = app.get('priority', 'Medium')
        priority_counts[priority] += 1

    # Generate insights
    insights = []

    # Response time insight
    response_times = []
    for app in company_apps:
        if app.get('application_date') and app.get('response_date'):
            try:
                app_date = datetime.strptime(app['application_date'],
                                             '%Y-%m-%d').date()
                resp_date = datetime.strptime(app['response_date'],
                                              '%Y-%m-%d').date()
                response_times.append((resp_date - app_date).days)
            except:
                pass

    if response_times:
        avg_response = sum(response_times) / len(response_times)
        if avg_response < 7:
            insights.append({
                'type':
                'positive',
                'title':
                'Fast Response Time',
                'description':
                f'Average response time of {round(avg_response)} days indicates efficient recruitment'
            })
        elif avg_response > 30:
            insights.append({
                'type':
                'warning',
                'title':
                'Slow Response Time',
                'description':
                f'Average response time of {round(avg_response)} days - consider following up'
            })

    # Success rate insight
    offers = len(
        [app for app in company_apps if app.get('status') == 'Offered'])
    offer_rate = round((offers / len(company_apps) * 100), 1)

    if offer_rate > 20:
        insights.append({
            'type':
            'positive',
            'title':
            'High Success Rate',
            'description':
            f'{offer_rate}% offer rate suggests good candidate-company fit'
        })
    elif offer_rate < 5:
        insights.append({
            'type':
            'info',
            'title':
            'Competitive Process',
            'description':
            f'{offer_rate}% offer rate indicates highly selective recruitment'
        })

    # Enhanced university success analysis
    university_success_rates = {}
    for app in company_apps:
        if app.get('university'):
            uni = app['university']
            if uni not in university_success_rates:
                university_success_rates[uni] = {
                    'total_apps': 0,
                    'assessment_received': 0,
                    'interview_reached': 0,
                    'offers_received': 0,
                    'avg_wam': [],
                    'successful_wam_range': []
                }

            university_success_rates[uni]['total_apps'] += 1

            # Track WAM data
            if app.get('wam') and str(app['wam']).replace('.', '').isdigit():
                university_success_rates[uni]['avg_wam'].append(
                    float(app['wam']))

            status = app.get('status', 'Applied')
            if status in [
                    'Online Assessment Received', 'Phone Interview Scheduled',
                    'Assessment Centre Invited', 'Offered'
            ]:
                university_success_rates[uni]['assessment_received'] += 1

            if status in [
                    'Phone Interview Scheduled', 'Assessment Centre Invited',
                    'Offered'
            ]:
                university_success_rates[uni]['interview_reached'] += 1

            if status == 'Offered':
                university_success_rates[uni]['offers_received'] += 1
                if app.get('wam') and str(app['wam']).replace('.',
                                                              '').isdigit():
                    university_success_rates[uni][
                        'successful_wam_range'].append(float(app['wam']))

    # Calculate percentages and averages for universities
    uni_analytics = {}
    for uni, data in university_success_rates.items():
        if data['total_apps'] >= 2:  # Minimum threshold for meaningful data
            avg_wam = round(sum(data['avg_wam']) / len(data['avg_wam']),
                            1) if data['avg_wam'] else 'N/A'
            successful_wam_avg = round(
                sum(data['successful_wam_range']) /
                len(data['successful_wam_range']),
                1) if data['successful_wam_range'] else 'N/A'

            uni_analytics[uni] = {
                'total_applications':
                data['total_apps'],
                'assessment_rate':
                round((data['assessment_received'] / data['total_apps']) * 100,
                      1),
                'interview_rate':
                round((data['interview_reached'] / data['total_apps']) * 100,
                      1),
                'offer_rate':
                round((data['offers_received'] / data['total_apps']) * 100, 1),
                'average_applicant_wam':
                avg_wam,
                'average_successful_wam':
                successful_wam_avg,
                'sample_size':
                data['total_apps']
            }

    return jsonify({
        'timeline_data': dict(monthly_apps),
        'stage_progression': dict(stage_counts),
        'wam_distribution': wam_ranges,
        'wam_requirements_by_stage': wam_requirements,
        'university_analytics': uni_analytics,
        'priority_distribution': dict(priority_counts),
        'insights': insights,
        'total_tracked': len(company_apps)
    })


@app.route('/experiences')
def experiences():
    # Load all submissions and display as experiences
    with open(data_file, 'r') as f:
        submissions = json.load(f)

    # Convert submissions to experience format
    experience_items = []
    for sub in submissions:
        # Build main content without duplicating advice
        content_parts = []
        if sub.get('application_stages'):
            content_parts.append(f"Application: {sub['application_stages']}")
        if sub.get('interview_experience'):
            content_parts.append(f"Interview: {sub['interview_experience']}")

        # Don't include advice in content_parts to avoid duplication
        main_content = " • ".join(content_parts) if content_parts else ""

        # Add advice separately if it exists, is different from other content, and is actually helpful
        advice_text = sub.get('advice', '').strip()
        if advice_text and advice_text not in main_content and is_helpful_advice(
                advice_text):
            if main_content:
                main_content += f" • Advice: {advice_text}"
            else:
                main_content = f"Advice: {advice_text}"

        experience_items.append({
            "content":
            main_content,
            "firm_name":
            sub['company'],
            "quality_score":
            0.95,
            "primary_cat":
            sub.get('theme', 'other').lower().replace(' ', '_'),
            "cat_labels": [sub.get('theme', 'Other')],
            "is_submission":
            True,
            "experience_type":
            sub.get('experience_type', ''),
            "role":
            sub.get('role', ''),
            "timestamp":
            sub.get('timestamp', ''),
            "user_name":
            sub.get('user_name', 'Anonymous'),
            "source":
            sub.get('source', 'user'),
            "pro_tip":
            sub.get('pro_tip', ''),
            "advice":
            advice_text  # Keep for potential separate display but don't duplicate
        })

    # Sort by timestamp (most recent first)
    experience_items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)

    return render_template("experiences.html",
                           experiences=experience_items,
                           is_filtered=True)


@app.route('/experiences/<firm_name>')
def firm_experiences(firm_name):
    from collections import Counter
    from categorizer import classify_text, label

    # Get university data for this firm
    university_data = FIRM_UNIVERSITY_DATA.get(firm_name, None)

    # Create company slug and title for template
    company_slug = firm_name.lower().replace(' ', '-').replace('&', 'and')
    company_title = firm_name.replace('-', ' ').replace('%20',
                                                        ' ').strip().title()

    # Load submissions data for this firm
    with open(data_file, 'r') as f:
        submissions = json.load(f)

    firm_submissions = [
        s for s in submissions
        if s.get('company', '').lower() == firm_name.lower()
    ]

    # Convert submissions to experience format for display
    items = []
    seen_advice = set()  # Track seen advice to prevent duplicates

    for sub in firm_submissions:
        # Build main content without duplicating advice
        content_parts = []
        if sub.get('application_stages'):
            content_parts.append(
                f"Application process: {sub['application_stages']}")
        if sub.get('interview_experience'):
            content_parts.append(
                f"Interview experience: {sub['interview_experience']}")

        # Don't include advice in content_parts to avoid duplication
        main_content = " • ".join(content_parts) if content_parts else ""

        # Add advice separately if it exists, is different from other content, is actually helpful, and not already shown
        advice_text = sub.get('advice', '').strip()
        if (advice_text and advice_text not in main_content
                and is_helpful_advice(advice_text)
                and advice_text not in seen_advice):
            seen_advice.add(advice_text)
            if main_content:
                main_content += f" • Advice: {advice_text}"
            else:
                main_content = f"Advice: {advice_text}"

        items.append({
            "content":
            main_content,
            "firm_name":
            sub['company'],
            "quality_score":
            0.95,
            "primary_cat":
            sub.get('theme', 'other').lower().replace(' ', '_'),
            "cat_labels": [sub.get('theme', 'Other')],
            "is_submission":
            True,
            "experience_type":
            sub.get('experience_type', ''),
            "role":
            sub.get('role', ''),
            "timestamp":
            sub.get('timestamp', ''),
            "user_name":
            sub.get('user_name', 'Anonymous'),
            "source":
            sub.get('source', 'user'),
            "application_process":
            sub.get('application_stages', ''),
            "application_stages":
            sub.get('application_stages', ''),
            "interview_experience":
            sub.get('interview_experience', ''),
            "pro_tip":
            sub.get('pro_tip', ''),
            "advice":
            advice_text  # Keep for potential separate display but don't duplicate
        })

    # Apply category filter
    active_cat = request.args.get("cat")
    if active_cat:
        items = [
            item for item in items if item.get("primary_cat") == active_cat
        ]

    # Build category counts
    cat_counts = Counter(item["primary_cat"] for item in items
                         if item.get("primary_cat"))

    return render_template("experiences.html",
                           experiences=items,
                           firm_name=firm_name,
                           company=firm_name,
                           company_slug=company_slug,
                           company_title=company_title,
                           is_filtered=True,
                           university_data=university_data,
                           cat_counts=cat_counts,
                           active_cat=active_cat)


@app.route('/law-match', methods=['GET', 'POST'])
def law_match():
    if request.method == 'POST':
        uni = request.form['uni']
        wam_str = request.form['wam'].strip().lower()
        if wam_str in ['nan', 'inf', '-inf', '+inf']:
            return "Invalid WAM value", 400
        try:
            wam = float(wam_str)
            if not (0 <= wam <= 100):  # WAM should be between 0-100
                return "WAM must be between 0 and 100", 400
        except ValueError:
            return "Invalid WAM value", 400
        interest = request.form['interest']
        preference = request.form['preference']
        experience = request.form.get('experience', 'none')
        location = request.form.get('location', 'any')
        grad_year = request.form.get('grad_year', '2025')

        # Import datetime for timing analysis
        from datetime import datetime
        import csv

        # Advanced candidate profiling for meta-analysis
        candidate_profile = {
            'competitiveness':
            'high' if wam >= 82 else 'medium' if wam >= 75 else 'developing',
            'market_timing':
            'optimal' if 2 <= datetime.now().month <= 5 else
            'late' if datetime.now().month >= 8 else 'early',
            'experience_level':
            experience,
            'career_focus':
            preference
        }

        # Load real firm data from CSV
        firms = load_cards_v2("out/grad_program_signals.csv")
        firm_data_lookup = {firm['name']: firm for firm in firms}

        # Load comprehensive data from processed CSV
        csv_insights = {}
        with open("out/grad_program_signals.csv", 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                firm_name = row.get('firm_name', '').strip()
                if firm_name:
                    if firm_name not in csv_insights:
                        csv_insights[firm_name] = {
                            'total_mentions': 0,
                            'recent_activity': 0,
                            'avg_confidence': 0,
                            'cities': set(),
                            'program_types': set(),
                            'confidence_scores': [],
                            'years': set()
                        }

                    data = csv_insights[firm_name]
                    data['total_mentions'] += 1

                    # Track recent activity (2024-2025)
                    year = row.get('intake_year', '')
                    if year and year.isdigit() and int(year) >= 2024:
                        data['recent_activity'] += 1
                        data['years'].add(int(year))

                    # Track confidence and locations
                    confidence = row.get('confidence', '')
                    if confidence:
                        try:
                            data['confidence_scores'].append(float(confidence))
                        except:
                            pass

                    city = row.get('city', '').strip()
                    if city and city != 'Other/Unknown':
                        data['cities'].add(city)

                    program_type = row.get('program_type', '').strip()
                    if program_type and program_type != 'ambiguous':
                        data['program_types'].add(program_type)

        # Calculate averages for CSV insights
        for firm_name, data in csv_insights.items():
            if data['confidence_scores']:
                data['avg_confidence'] = sum(data['confidence_scores']) / len(
                    data['confidence_scores'])
            data['cities'] = list(data['cities'])
            data['program_types'] = list(data['program_types'])

        # Enhanced firm profiling with real data integration and CSV insights
        base_profiles = {
            'Allens': {
                'tier':
                'top',
                'prestige_score':
                95,
                'training_score':
                90,
                'worklife_score':
                65,
                'competitive_level':
                'very_high',
                'wam_threshold':
                82,
                'strengths':
                ['Corporate M&A', 'Banking & Finance', 'Competition Law'],
                'culture':
                'Traditional, high-performing, competitive'
            },
            'King & Wood Mallesons': {
                'tier':
                'top',
                'prestige_score':
                95,
                'training_score':
                85,
                'worklife_score':
                60,
                'competitive_level':
                'very_high',
                'wam_threshold':
                83,
                'strengths':
                ['Asia-Pacific focus', 'Corporate M&A', 'Capital Markets'],
                'culture':
                'International, demanding, prestigious'
            },
            'Herbert Smith Freehills': {
                'tier':
                'top',
                'prestige_score':
                90,
                'training_score':
                88,
                'worklife_score':
                68,
                'competitive_level':
                'very_high',
                'wam_threshold':
                81,
                'strengths':
                ['Dispute Resolution', 'Energy & Resources', 'Corporate'],
                'culture':
                'Global outlook, collaborative, high standards'
            },
            'Gilbert + Tobin': {
                'tier': 'top',
                'prestige_score': 88,
                'training_score': 92,
                'worklife_score': 75,
                'competitive_level': 'high',
                'wam_threshold': 78,
                'strengths':
                ['Litigation', 'Corporate Advisory', 'Employment'],
                'culture': 'Innovative, collegial, quality-focused'
            },
            'Clayton Utz': {
                'tier': 'mid-top',
                'prestige_score': 85,
                'training_score': 85,
                'worklife_score': 70,
                'competitive_level': 'high',
                'wam_threshold': 76,
                'strengths':
                ['Insurance', 'Construction', 'Government Advisory'],
                'culture': 'Client-focused, collaborative, supportive'
            },
            'Ashurst': {
                'tier': 'mid-top',
                'prestige_score': 82,
                'training_score': 80,
                'worklife_score': 72,
                'competitive_level': 'high',
                'wam_threshold': 75,
                'strengths':
                ['Infrastructure', 'Corporate', 'Financial Services'],
                'culture': 'International, team-oriented, developmental'
            },
            'MinterEllison': {
                'tier': 'mid',
                'prestige_score': 78,
                'training_score': 85,
                'worklife_score': 75,
                'competitive_level': 'moderate',
                'wam_threshold': 73,
                'strengths': ['Government', 'Health', 'Workplace Relations'],
                'culture': 'Diverse, inclusive, development-focused'
            },
            'Corrs Chambers Westgarth': {
                'tier': 'mid',
                'prestige_score': 75,
                'training_score': 82,
                'worklife_score': 78,
                'competitive_level': 'moderate',
                'wam_threshold': 72,
                'strengths':
                ['Corporate', 'Competition', 'Intellectual Property'],
                'culture': 'Collegiate, supportive, quality work'
            },
            'Lander & Rogers': {
                'tier': 'mid',
                'prestige_score': 70,
                'training_score': 88,
                'worklife_score': 85,
                'competitive_level': 'moderate',
                'wam_threshold': 70,
                'strengths': ['Family Law', 'Commercial', 'Property'],
                'culture': 'Melbourne-focused, mentoring, work-life balance'
            }
        }

        # Merge real data with base profiles and CSV insights
        firm_profiles = {}
        for firm_name, base_profile in base_profiles.items():
            profile = base_profile.copy()

            # Add real salary data if available
            real_data = firm_data_lookup.get(firm_name)
            if real_data and real_data.get('avg_salary'):
                profile['avg_salary'] = real_data['avg_salary']
                profile['salary_range'] = real_data.get(
                    'salary_range', f"${real_data['avg_salary']:,.0f}")
            else:
                # Fallback salary estimates based on tier
                salary_estimates = {
                    'top': {
                        'avg': 87000,
                        'range': '82-95k'
                    },
                    'mid-top': {
                        'avg': 82000,
                        'range': '76-88k'
                    },
                    'mid': {
                        'avg': 75000,
                        'range': '70-82k'
                    }
                }
                est = salary_estimates.get(profile['tier'],
                                           salary_estimates['mid'])
                profile['avg_salary'] = est['avg']
                profile['salary_range'] = est['range']

            # Integrate CSV-derived insights
            csv_data = csv_insights.get(firm_name, {})
            profile['csv_activity'] = csv_data.get('recent_activity', 0)
            profile['csv_confidence'] = csv_data.get('avg_confidence', 0.5)
            profile['csv_mentions'] = csv_data.get('total_mentions', 0)
            profile['active_cities'] = csv_data.get('cities', [])
            profile['program_offerings'] = csv_data.get('program_types', [])

            # Calculate market activity score (0-1)
            max_activity = max([
                data.get('recent_activity', 0)
                for data in csv_insights.values()
            ] + [1])
            profile['market_activity'] = csv_data.get(
                'recent_activity', 0) / max_activity if max_activity > 0 else 0

            firm_profiles[firm_name] = profile

        # Enhanced data-driven scoring algorithm
        firm_scores = {}

        for firm, profile in firm_profiles.items():
            score = 40.0  # Lower base score to emphasize data-driven factors
            reasons = []
            confidence_factors = []

            # Market activity bonus (based on real CSV data)
            activity_score = profile.get('market_activity', 0) * 15
            if activity_score >= 10:
                score += activity_score
                reasons.append(f"High recent graduate recruitment activity")
                confidence_factors.append('active_recruiting')
            elif activity_score >= 5:
                score += activity_score
                reasons.append(f"Active graduate recruitment")
                confidence_factors.append('moderate_recruiting')

            # Data confidence bonus (how reliable our insights are)
            csv_confidence = profile.get('csv_confidence', 0.5)
            csv_mentions = profile.get('csv_mentions', 0)
            if csv_confidence >= 0.8 and csv_mentions >= 10:
                score += 8
                confidence_factors.append('high_data_quality')
            elif csv_confidence >= 0.7 and csv_mentions >= 5:
                score += 5
                confidence_factors.append('good_data_quality')

            # University representation (weighted by firm tier and data quality)
            uni_percentage = FIRM_UNIVERSITY_DATA.get(firm, {}).get(
                uni,
                FIRM_UNIVERSITY_DATA.get(firm, {}).get('Other', 0))
            data_weight = 1.0 + (profile.get('csv_confidence', 0.5) - 0.5
                                 )  # Boost for high-quality data
            tier_weight = 1.5 if profile['tier'] == 'top' else 1.2 if profile[
                'tier'] == 'mid-top' else 1.0
            uni_weight = tier_weight * data_weight

            if uni_percentage >= 25:
                uni_bonus = 30 * uni_weight
                score += uni_bonus
                reasons.append(
                    f"Excellent {uni} representation ({uni_percentage}%)")
                confidence_factors.append('excellent_uni_rep')
            elif uni_percentage >= 15:
                uni_bonus = 22 * uni_weight
                score += uni_bonus
                reasons.append(
                    f"Strong {uni} representation ({uni_percentage}%)")
                confidence_factors.append('high_uni_rep')
            elif uni_percentage >= 8:
                uni_bonus = 12 * uni_weight
                score += uni_bonus
                reasons.append(
                    f"Good {uni} representation ({uni_percentage}%)")
                confidence_factors.append('medium_uni_rep')
            elif uni_percentage >= 3:
                uni_bonus = 6 * uni_weight
                score += uni_bonus
                reasons.append(
                    f"Some {uni} representation ({uni_percentage}%)")

            # Enhanced WAM scoring with data-driven thresholds
            wam_threshold = profile.get('wam_threshold', 75)

            # Adjust threshold based on market competition and data
            competition_adjustment = 0
            if profile.get('market_activity',
                           0) > 0.7:  # High activity = more competitive
                competition_adjustment = 2
            elif profile.get('market_activity',
                             0) < 0.3:  # Low activity = less competitive
                competition_adjustment = -2

            adjusted_threshold = wam_threshold + competition_adjustment
            wam_diff = wam - adjusted_threshold

            if wam_diff >= 12:
                score += 40
                reasons.append(
                    f"WAM significantly exceeds expectations ({wam:.1f} vs ~{adjusted_threshold})"
                )
                confidence_factors.append('outstanding_wam')
            elif wam_diff >= 7:
                score += 30
                reasons.append(f"WAM well above requirements ({wam:.1f})")
                confidence_factors.append('excellent_wam')
            elif wam_diff >= 3:
                score += 20
                reasons.append(f"WAM above typical threshold ({wam:.1f})")
                confidence_factors.append('strong_wam')
            elif wam_diff >= 0:
                score += 12
                reasons.append(
                    f"WAM meets current market expectations ({wam:.1f})")
                confidence_factors.append('adequate_wam')
            elif wam_diff >= -3:
                score += 3
                reasons.append(f"WAM slightly below market average")
            elif wam_diff >= -7:
                score -= 5
                reasons.append(f"WAM below typical requirements")
            else:
                score -= 15
                reasons.append(f"WAM significantly below expectations")

            # Preference alignment with dynamic weighting
            pref_weight = 0.3
            if preference == 'prestige':
                pref_score = profile['prestige_score'] * pref_weight
                score += pref_score
                reasons.append(
                    f"High prestige rating ({profile['prestige_score']}/100)")
            elif preference == 'training':
                pref_score = profile['training_score'] * pref_weight
                score += pref_score
                reasons.append(
                    f"Strong training programs ({profile['training_score']}/100)"
                )
            elif preference == 'worklife':
                pref_score = profile['worklife_score'] * pref_weight
                score += pref_score
                reasons.append(
                    f"Good work-life balance ({profile['worklife_score']}/100)"
                )
            elif preference == 'salary':
                salary_score = min(25, (profile['avg_salary'] - 70000) / 1000)
                score += salary_score
                reasons.append(
                    f"Competitive salary (${profile['avg_salary']:,.0f})")

            # Experience level fit (only add specific bonuses, no generic reasons)
            exp_bonus = 0
            if experience == 'extensive' and profile[
                    'competitive_level'] == 'very_high':
                exp_bonus = 15
            elif experience == 'some' and profile['competitive_level'] in [
                    'high', 'moderate'
            ]:
                exp_bonus = 12
            elif experience == 'none' and profile[
                    'competitive_level'] == 'moderate':
                exp_bonus = 15
                reasons.append(
                    "Welcomes graduates without prior legal experience")
            elif experience == 'none' and profile[
                    'competitive_level'] == 'high':
                exp_bonus = 5

            score += exp_bonus

            # Advanced interest area alignment with market intelligence
            interest_bonus = 0
            interest_keywords = {
                'commercial': [
                    'corporate', 'm&a', 'banking', 'finance', 'commercial',
                    'capital markets'
                ],
                'litigation': [
                    'litigation', 'dispute', 'resolution', 'employment',
                    'arbitration'
                ],
                'family': ['family'],
                'criminal': ['criminal'],
                'employment': ['employment', 'workplace', 'industrial'],
                'property': ['property', 'real estate', 'construction'],
                'tax': ['tax', 'revenue'],
                'technology':
                ['technology', 'ip', 'intellectual property', 'data'],
                'energy': ['energy', 'resources', 'mining', 'oil'],
                'other': []
            }

            user_keywords = interest_keywords.get(interest, [])
            matched_strengths = []

            for strength in profile['strengths']:
                for keyword in user_keywords:
                    if keyword.lower() in strength.lower():
                        matched_strengths.append(strength)
                        interest_bonus += 20
                        confidence_factors.append('practice_match')
                        break

            # Provide specific practice area insights
            if matched_strengths:
                if len(matched_strengths) > 1:
                    reasons.append(
                        f"Multiple practice strengths: {', '.join(matched_strengths[:2])}"
                    )
                else:
                    reasons.append(
                        f"Leading expertise in {matched_strengths[0]}")

            # Emerging practice area bonus for forward-thinking candidates
            if interest == 'technology' and any(
                    'tech' in s.lower() or 'ip' in s.lower()
                    for s in profile['strengths']):
                interest_bonus += 10
                reasons.append("Strong in high-growth technology practice")

            score += interest_bonus

            # Enhanced location matching with CSV data
            if location != 'any':
                active_cities = profile.get('active_cities', [])
                real_data = firm_data_lookup.get(firm)

                location_match = False
                if active_cities:
                    for city in active_cities:
                        if location.lower() in city.lower():
                            score += 12
                            reasons.append(f"Active recruitment in {city}")
                            confidence_factors.append('location_match')
                            location_match = True
                            break

                if not location_match and real_data and real_data.get(
                        'top_city'):
                    if location.lower() in real_data['top_city'].lower():
                        score += 6
                        reasons.append(f"Established presence in {location}")

            # Advanced program type and career path alignment
            program_types = profile.get('program_offerings', [])
            if interest in ['clerkship', 'graduate']:
                target_program = 'clerkship' if interest == 'clerkship' else 'graduate'

                if any(target_program in prog.lower()
                       for prog in program_types):
                    score += 10
                    confidence_factors.append('program_match')
                elif program_types:  # Has programs but not exact match
                    score += 5

            # Intelligent career progression analysis
            if experience == 'extensive' and preference == 'prestige':
                if profile['tier'] == 'top' and profile.get(
                        'market_activity', 0) > 0.5:
                    score += 12
                    reasons.append(
                        "Perfect timing for experienced candidate seeking prestige"
                    )
            elif experience == 'none' and preference == 'training':
                if profile['training_score'] >= 85:
                    score += 15
                    reasons.append("Excellent graduate development programs")
                    confidence_factors.append('training_excellence')

            # Market timing intelligence
            current_month = datetime.now().month
            if grad_year == '2025':
                if 2 <= current_month <= 5:  # Peak recruitment season
                    if profile.get('market_activity', 0) > 0.7:
                        score += 8
                        reasons.append("High recruitment activity this season")
                elif current_month >= 8:  # Late season opportunities
                    if profile.get('market_activity', 0) > 0.4:
                        score += 6
                        reasons.append(
                            "Still actively recruiting late in season")

            # Sophisticated WAM contextualization
            if uni in [
                    'University of Melbourne', 'University of Sydney', 'UNSW'
            ]:
                go8_bonus = 3  # Go8 recognition
                if wam >= 80:
                    go8_bonus = 8
                    reasons.append(
                        "Strong WAM from prestigious Go8 university")
                score += go8_bonus

            # Strategic preference matching with market intelligence
            if preference == 'salary':
                salary_competitive = profile.get('avg_salary', 75000)
                if salary_competitive >= 85000:
                    score += 18
                    reasons.append(
                        f"Top-tier compensation (${salary_competitive:,.0f})")
                elif salary_competitive >= 80000:
                    score += 12
                    reasons.append(
                        f"Competitive salary package (${salary_competitive:,.0f})"
                    )
            elif preference == 'prestige' and profile['tier'] == 'top':
                market_reputation = profile.get(
                    'market_activity', 0) * 0.3 + profile.get(
                        'csv_confidence', 0.5) * 0.4
                if market_reputation > 0.6:
                    score += 15
                    reasons.append("Market-leading reputation and visibility")

            # Intelligent experience-firm culture matching
            culture_match = 0
            culture = profile.get('culture', '').lower()
            if experience == 'extensive':
                if 'traditional' in culture or 'demanding' in culture:
                    culture_match = 8
                    reasons.append("Culture rewards experienced professionals")
            elif experience == 'none':
                if 'supportive' in culture or 'development' in culture or 'mentoring' in culture:
                    culture_match = 12
                    reasons.append("Supportive culture for new graduates")
                    confidence_factors.append('culture_fit')
            elif experience == 'some':
                if 'collaborative' in culture or 'team' in culture:
                    culture_match = 10
                    reasons.append(
                        "Collaborative environment values diverse experience")

            score += culture_match

            # Enhanced confidence calculation with data quality factors
            confidence = 'Low'
            high_confidence_factors = [
                'outstanding_wam', 'excellent_wam', 'excellent_uni_rep',
                'active_recruiting', 'high_data_quality'
            ]
            medium_confidence_factors = [
                'strong_wam', 'high_uni_rep', 'practice_match',
                'location_match', 'good_data_quality'
            ]

            if (len(confidence_factors) >= 4
                    or any(f in confidence_factors
                           for f in high_confidence_factors)
                    and len(confidence_factors) >= 2
                    or 'outstanding_wam' in confidence_factors):
                confidence = 'Very High'
            elif (len(confidence_factors) >= 3
                  or any(f in confidence_factors
                         for f in high_confidence_factors) or len([
                             f for f in confidence_factors
                             if f in medium_confidence_factors
                         ]) >= 2):
                confidence = 'High'
            elif (len(confidence_factors) >= 2
                  or any(f in confidence_factors
                         for f in medium_confidence_factors)):
                confidence = 'Medium'

            firm_scores[firm] = {
                'score': max(0, min(100, score)),
                'profile': profile,
                'reasons': reasons[:4],  # Limit to top 4 reasons
                'uni_percentage': uni_percentage,
                'confidence': confidence
            }

        # Intelligent ranking with diversification logic
        sorted_firms = sorted(firm_scores.items(),
                              key=lambda x: x[1]['score'],
                              reverse=True)

        # Smart selection algorithm that ensures diversity
        top_firms = []
        selected_tiers = set()

        for firm, data in sorted_firms:
            tier = data['profile']['tier']

            # Always include top scorer
            if len(top_firms) == 0:
                top_firms.append((firm, data))
                selected_tiers.add(tier)
            # For subsequent firms, prefer diversity unless score gap is huge
            elif len(top_firms) < 5:
                score_gap = top_firms[0][1]['score'] - data['score']

                # If score is still very competitive, add it
                if score_gap <= 20:
                    top_firms.append((firm, data))
                    selected_tiers.add(tier)
                # If we need tier diversity and score is reasonable, include it
                elif tier not in selected_tiers and score_gap <= 35 and data[
                        'score'] >= 50:
                    top_firms.append((firm, data))
                    selected_tiers.add(tier)
                # Otherwise, only include if score is very close
                elif score_gap <= 10:
                    top_firms.append((firm, data))
                    selected_tiers.add(tier)

        # Ensure we have at least 3 recommendations
        while len(top_firms) < min(3, len(sorted_firms)):
            for firm, data in sorted_firms:
                if (firm, data) not in top_firms:
                    top_firms.append((firm, data))
                    break

        # Generate intelligent recommendations with strategic advice
        recommendations = []
        for i, (firm_name, firm_data) in enumerate(top_firms):
            # Smart recommendation typing based on score and confidence
            if i == 0 and firm_data['confidence'] in ['High', 'Very High']:
                rec_type = 'Top Match'
            elif i == 0:
                rec_type = 'Best Option'
            elif firm_data['score'] >= top_firms[0][1]['score'] - 10:
                rec_type = 'Excellent Alternative'
            elif i == 1:
                rec_type = 'Strong Alternative'
            elif firm_data['confidence'] in ['High', 'Very High']:
                rec_type = 'High Confidence'
            else:
                rec_type = 'Consider'

            # Intelligent reason filtering and enhancement
            meaningful_reasons = []
            strategic_advice = []

            for reason in firm_data['reasons']:
                # Skip generic reasons but enhance specific ones
                if not any(generic in reason.lower() for generic in [
                        'be genuine', 'prepare thoroughly', 'show enthusiasm',
                        'good experience level', 'matches firm expectations'
                ]):
                    meaningful_reasons.append(reason)

            # Add strategic application advice based on firm profile
            tier = firm_data['profile']['tier']
            market_activity = firm_data['profile'].get('market_activity', 0)

            if tier == 'top' and market_activity > 0.7:
                strategic_advice.append(
                    "Apply early - highly competitive positions")
            elif firm_data['profile']['training_score'] >= 85:
                strategic_advice.append(
                    "Emphasize learning motivation in application")
            elif 'culture_fit' in firm_data.get('confidence_factors', []):
                strategic_advice.append(
                    "Research firm culture for interview preparation")

            recommendations.append({
                'firm':
                firm_name,
                'confidence':
                firm_data['confidence'],
                'recommendation_type':
                rec_type,
                'score':
                round(firm_data['score'], 1),
                'reasons':
                meaningful_reasons[:3],
                'strategic_advice':
                strategic_advice[:2],
                'profile':
                firm_data['profile'],
                'tier':
                tier,
                'salary_range':
                firm_data['profile'].get('salary_range', 'Contact for details')
            })

        # Advanced strategic insights with sophisticated reasoning
        insights = []
        primary_firm = top_firms[0][1]

        # Strategic WAM positioning analysis
        wam_threshold = primary_firm['profile'].get('wam_threshold', 75)
        top_tier_firms = [
            f for f in top_firms if f[1]['profile']['tier'] == 'top'
        ]

        if wam >= 85:
            competitive_options = len(
                [f for f in sorted_firms if f[1]['score'] >= 75])
            insights.append(
                f"Your exceptional WAM ({wam:.1f}) opens doors to {competitive_options} highly competitive firms - consider applying strategically to 8-12 firms."
            )
        elif wam >= wam_threshold + 8:
            insights.append(
                f"Your strong WAM ({wam:.1f}) positions you well above market requirements - focus on firms matching your interests rather than just prestige."
            )
        elif wam_threshold - 3 <= wam < wam_threshold + 3:
            market_trend = "competitive" if len(
                top_tier_firms) >= 2 else "stable"
            insights.append(
                f"Your WAM is in the competitive range - in this {market_trend} market, emphasize unique experiences and genuine interest in your applications."
            )
        elif wam < wam_threshold - 5:
            mid_tier_matches = len([
                f for f in top_firms[:3]
                if f[1]['profile']['tier'] in ['mid', 'mid-top']
            ])
            if mid_tier_matches >= 2:
                insights.append(
                    "Focus on mid-tier firms where you'll be highly valued - they often provide excellent training and clearer pathways to partnership."
                )
            else:
                insights.append(
                    "Consider highlighting leadership roles, work experience, and demonstrated commercial awareness to differentiate your application."
                )

        # University network strategy analysis
        uni_strengths = {}
        for firm, data in top_firms[:3]:
            uni_pct = data['uni_percentage']
            if uni_pct >= 15:
                uni_strengths[firm] = uni_pct

        if len(uni_strengths) >= 2:
            best_firm, best_pct = max(uni_strengths.items(),
                                      key=lambda x: x[1])
            insights.append(
                f"Your {uni} network is particularly strong at {best_firm} ({best_pct}%) - reach out to recent graduates for insights and referrals."
            )
        elif uni_strengths:
            firm, pct = list(uni_strengths.items())[0]
            insights.append(
                f"Leverage your {uni} connection at {firm} ({pct}% representation) for networking opportunities."
            )

        # Market timing and competition analysis
        high_activity_firms = [
            f[0] for f in top_firms[:3]
            if f[1]['profile'].get('market_activity', 0) > 0.6
        ]
        if len(high_activity_firms) >= 2 and grad_year == '2025':
            insights.append(
                f"Market intelligence shows {', '.join(high_activity_firms[:2])} are actively recruiting - apply early as positions fill quickly."
            )

        # Experience-based strategic advice
        if experience == 'extensive':
            top_competitive = [
                f for f in top_firms[:2]
                if f[1]['profile']['competitive_level'] == 'very_high'
            ]
            if top_competitive:
                insights.append(
                    "Your extensive experience gives you an edge at top-tier firms - highlight specific commercial achievements and client impact."
                )
        elif experience == 'none':
            training_focused = [
                f for f in top_firms[:3]
                if f[1]['profile']['training_score'] >= 85
            ]
            if len(training_focused) >= 2:
                insights.append(
                    "Target firms known for exceptional graduate training - they invest heavily in developing raw talent into skilled lawyers."
                )

        # Portfolio strategy based on score distribution
        score_spread = top_firms[0][1]['score'] - top_firms[2][1][
            'score'] if len(top_firms) >= 3 else 0
        high_confidence_matches = len([
            f for f in top_firms
            if f[1]['confidence'] in ['High', 'Very High']
        ])

        if score_spread < 10 and high_confidence_matches >= 3:
            insights.append(
                "You have multiple excellent matches - create a balanced application portfolio across different firm tiers and practice areas."
            )
        elif high_confidence_matches >= 2:
            insights.append(
                f"Strong alignment with {high_confidence_matches} firms - focus your energy on crafting compelling, firm-specific applications."
            )

        # Interest-practice area intelligence
        practice_matches = []
        for firm, data in top_firms[:3]:
            strengths = data['profile'].get('strengths', [])
            if interest == 'commercial' and any(
                    'Corporate' in s or 'Banking' in s or 'Finance' in s
                    for s in strengths):
                practice_matches.append(firm)
            elif interest == 'litigation' and any(
                    'Litigation' in s or 'Dispute' in s for s in strengths):
                practice_matches.append(firm)

        if len(practice_matches) >= 2:
            insights.append(
                f"Your {interest} interest aligns perfectly with {', '.join(practice_matches[:2])} - research their recent major cases and deals."
            )

        # Location-based market intelligence
        if location != 'any':
            location_matches = [
                f[0] for f in top_firms[:3]
                if location.lower() in str(f[1]['profile'].get(
                    'active_cities', [])).lower()
            ]
            if len(location_matches) >= 2:
                insights.append(
                    f"{location} market shows strong opportunities at {', '.join(location_matches[:2])} - consider the competitive landscape in this city."
                )

        # Generate meta-strategic advice based on overall profile
        meta_insights = []

        # Application timing strategy
        if grad_year == '2025':
            current_month = datetime.now().month
            if current_month <= 4:  # Early in recruitment season
                meta_insights.append(
                    "Apply early - many firms fill positions on a rolling basis, especially for strong candidates."
                )
            elif current_month >= 8:  # Late in season
                meta_insights.append(
                    "Focus on firms still actively recruiting - some opportunities remain for exceptional candidates."
                )

        # Portfolio diversification advice
        tier_distribution = {}
        for firm, data in top_firms:
            tier = data['profile']['tier']
            tier_distribution[tier] = tier_distribution.get(tier, 0) + 1

        if len(tier_distribution) >= 2:
            meta_insights.append(
                "Apply across firm tiers - this maximizes opportunities while building valuable experience regardless of outcome."
            )

        # Market positioning strategy
        if preference == 'prestige' and wam >= 82:
            meta_insights.append(
                "With your profile, consider international firms or emerging practice areas where you can make significant early impact."
            )
        elif preference == 'worklife' and experience == 'some':
            meta_insights.append(
                "Your experience and work-life priorities suggest targeting progressive firms - they often offer more flexible career paths."
            )

        return render_template('law_match_result.html',
                               recommendations=recommendations,
                               insights=insights,
                               meta_insights=meta_insights,
                               user_profile={
                                   'uni': uni,
                                   'wam': wam,
                                   'interest': interest,
                                   'preference': preference,
                                   'experience': experience,
                                   'location': location
                               })

    return render_template('law_match.html')


@app.route('/tracker')
@login_required
def tracker():
    current_user = get_current_user()
    if not current_user:
        flash('Please log in to access tracker.', 'error')
        return redirect(url_for('login'))
    user_id = current_user['id']
    user_name = current_user['username']

    # Get user applications from database
    applications = get_user_applications(user_id)

    return render_template('tracker.html',
                           applications=applications,
                           user_id=user_id,
                           user_name=user_name)


@app.route('/tracker/add', methods=['POST'])
@login_required
def add_application():
    current_user = get_current_user()
    if not current_user:
        flash('Please log in to add applications.', 'error')
        return redirect(url_for('login'))
    user_id = current_user['id']

    application_data = {
        'user_id':
        user_id,
        'company':
        request.form['company'],
        'role':
        request.form['role'],
        'application_date':
        request.form['application_date']
        if request.form['application_date'] else None,
        'university':
        request.form.get('university', ''),
        'wam':
        request.form.get('wam', ''),
        'status':
        request.form['status'],
        'response_date':
        request.form.get('response_date', '')
        if request.form.get('response_date') else None,
        'priority':
        request.form.get('priority', 'Medium'),
        'notes':
        request.form.get('notes', '')
    }

    create_application(user_id, application_data)
    return redirect(url_for('tracker'))


@app.route('/tracker/update/<int:app_id>', methods=['POST'])
@login_required
def update_application_route(app_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = current_user['id']

    update_data = {}
    if request.json:
        if 'status' in request.json:
            update_data['status'] = request.json['status']
        if 'response_date' in request.json:
            update_data['response_date'] = request.json[
                'response_date'] if request.json['response_date'] else None
        if 'notes' in request.json:
            update_data['notes'] = request.json['notes']
        if 'priority' in request.json:
            update_data['priority'] = request.json['priority']

    updated_app = update_application(app_id, user_id, update_data)

    if updated_app:
        return jsonify({'success': True})
    else:
        return jsonify({
            'success': False,
            'error': 'Application not found or access denied'
        }), 404


@app.route('/tracker/delete/<int:app_id>', methods=['DELETE'])
@login_required
def delete_application_route(app_id):
    current_user = get_current_user()
    if not current_user:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    user_id = current_user['id']

    success = delete_application(app_id, user_id)

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({
            'success': False,
            'error': 'Application not found or access denied'
        }), 404


@app.route('/tracker/analytics')
@login_required
def tracker_analytics():
    current_user = get_current_user()
    if not current_user:
        flash('Please log in to view analytics.', 'error')
        return redirect(url_for('login'))
    user_id = current_user['id']

    all_applications = get_all_applications()

    # Personal stats
    user_apps = [
        app for app in all_applications if app.get('user_id') == user_id
    ]

    total_applications = len(user_apps)
    responded_apps = [app for app in user_apps if app.get('response_date')]
    response_rate = round((len(responded_apps) / total_applications *
                           100), 1) if total_applications > 0 else 0

    # Calculate average response time
    response_times = []
    for app in responded_apps:
        if app.get('application_date') and app.get('response_date'):
            app_date = datetime.strptime(app['application_date'],
                                         '%Y-%m-%d').date()
            resp_date = datetime.strptime(app['response_date'],
                                          '%Y-%m-%d').date()
            response_times.append((resp_date - app_date).days)

    avg_response_time = round(sum(response_times) /
                              len(response_times)) if response_times else 0

    # Success rate (offers/total)
    successful_apps = [
        app for app in user_apps if app.get('status') == 'Offered'
    ]
    success_rate = round((len(successful_apps) / total_applications *
                          100), 1) if total_applications > 0 else 0

    personal_stats = {
        'total_applications': total_applications,
        'response_rate': response_rate,
        'avg_response_time': avg_response_time,
        'success_rate': success_rate
    }

    # Enhanced community insights with interview stage progression
    company_stats = {}
    university_stats = {}
    stage_progression = {}

    # Define interview stages in progression order
    interview_stages = [
        'Applied', 'Online Assessment Received', 'Online Assessment Completed',
        'Phone Interview Scheduled', 'Phone Interview Completed',
        'Assessment Centre Invited', 'Assessment Centre Completed',
        'Final Interview Scheduled', 'Final Interview Completed', 'Offered'
    ]

    # Aggregate from tracker data with enhanced analytics
    from typing import Dict, List, Any
    company_counts: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            'total_apps': 0,
            'responses': 0,
            'offers': 0,
            'avg_response_time': 0,
            'response_times': []
        })

    uni_stage_progression = defaultdict(
        lambda: {stage: 0
                 for stage in interview_stages})

    uni_company_progression = defaultdict(
        lambda: defaultdict(lambda: {stage: 0
                                     for stage in interview_stages}))

    # Add user info from submissions.json for university data
    with open(data_file, 'r') as f:
        submissions = json.load(f)

    for sub in submissions:
        if sub.get('university'):
            uni_stage_progression[sub['university']]['Applied'] += 1
            if sub.get('outcome') == 'Success':
                uni_stage_progression[sub['university']]['Offered'] += 1

    for app in all_applications:
        if app.get('company') and app.get('university'):
            company = app['company']
            counts = company_counts[company]
            counts['total_apps'] += 1

            # Track stage progression by university and company
            status = app.get('status', 'Applied')
            uni_stage_progression[app['university']][status] += 1
            uni_company_progression[app['university']][
                app['company']][status] += 1

            # Calculate response times
            if app.get('response_date') and app.get('application_date'):
                try:
                    app_date = datetime.strptime(app['application_date'],
                                                 '%Y-%m-%d').date()
                    resp_date = datetime.strptime(app['response_date'],
                                                  '%Y-%m-%d').date()
                    response_time = (resp_date - app_date).days
                    counts['response_times'].append(response_time)
                    counts['responses'] += 1
                except:
                    pass

            # Track offers
            if status == 'Offered':
                counts['offers'] += 1

    # Calculate enhanced company stats
    for company, counts in company_counts.items():
        total_apps = counts['total_apps']
        if total_apps >= 2:  # Lower threshold for more data
            avg_response_time = 0
            response_times = counts['response_times']
            if response_times:
                avg_response_time = round(
                    sum(response_times) /
                    len(response_times), 1)

            company_stats[company] = {
                'total_apps':
                total_apps,
                'response_rate':
                round((counts['responses'] / total_apps *
                       100), 1) if total_apps > 0 else 0,
                'offer_rate':
                round((counts['offers'] / total_apps *
                       100), 1) if total_apps > 0 else 0,
                'avg_response_time':
                avg_response_time
            }

    # Calculate university progression statistics
    for uni, stages in uni_stage_progression.items():
        total_applied = stages.get('Applied', 0)
        if total_applied >= 2:  # Minimum threshold
            university_stats[uni] = {
                'total_apps':
                total_applied,
                'online_assessment_rate':
                round((stages.get('Online Assessment Received', 0) /
                       total_applied * 100), 1) if total_applied > 0 else 0,
                'interview_rate':
                round(((stages.get('Phone Interview Scheduled', 0) +
                        stages.get('Assessment Centre Invited', 0)) /
                       total_applied * 100), 1) if total_applied > 0 else 0,
                'offer_rate':
                round((stages.get('Offered', 0) / total_applied *
                       100), 1) if total_applied > 0 else 0,
                'stage_breakdown': {
                    stage: stages.get(stage, 0)
                    for stage in interview_stages
                }
            }

    # Create stage progression data for visualization
    for uni, companies in uni_company_progression.items():
        for company, stages in companies.items():
            total_apps = stages.get('Applied', 0)
            if total_apps >= 1:
                if uni not in stage_progression:
                    stage_progression[uni] = {}
                stage_progression[uni][company] = {
                    'total_apps': total_apps,
                    'progression': {
                        stage:
                        round((count / total_apps *
                               100), 1) if total_apps > 0 else 0
                        for stage, count in stages.items()
                    }
                }

    # Sort by success/response rate
    company_stats = dict(
        sorted(company_stats.items(),
               key=lambda x: x[1]['response_rate'],
               reverse=True)[:10])
    university_stats = dict(
        sorted(university_stats.items(),
               key=lambda x: x[1]['success_rate'],
               reverse=True)[:10])

    return render_template('tracker_analytics.html',
                           personal_stats=personal_stats,
                           company_stats=company_stats,
                           university_stats=university_stats,
                           stage_progression=stage_progression,
                           response_time_stats=None)


@app.route('/tracker/export')
@login_required
def export_tracker():
    current_user = get_current_user()
    if not current_user:
        flash('Please log in to export data.', 'error')
        return redirect(url_for('login'))
    user_id = current_user['id']

    with open(tracker_file, 'r') as f:
        all_applications = json.load(f)

    user_apps = [
        app for app in all_applications if app.get('user_id') == user_id
    ]

    # Create CSV
    output_file = f'tracker_export_{user_id}.csv'
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = [
            'company', 'role', 'application_date', 'wam', 'status',
            'response_date', 'priority', 'notes'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        writer.writeheader()
        for app in user_apps:
            writer.writerow(
                {field: app.get(field, '')
                 for field in fieldnames})

    return send_file(
        output_file,
        as_attachment=True,
        download_name=f'applications_{datetime.now().strftime("%Y%m%d")}.csv')


# Legal & Compliance Routes
@app.route('/terms')
def terms():
    return render_template('terms.html', config=LEGAL_CONFIG)


@app.route('/privacy')
def privacy():
    return render_template('privacy.html', config=LEGAL_CONFIG)


@app.route('/moderation')
def moderation():
    return render_template('moderation.html', config=LEGAL_CONFIG)


@app.route('/report')
def report():
    return render_template('report.html', config=LEGAL_CONFIG)


# Authentication routes
# Old authentication routes removed - now using Replit Auth via headers

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
