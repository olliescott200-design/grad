import os
import psycopg2
import psycopg2.extras
from flask import request, session, jsonify
from datetime import datetime
from functools import wraps
from security import get_replit_user

def get_db_connection():
    """Get database connection"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)

def get_current_user():
    """Get current user from Replit Auth headers"""
    # Use secure get_replit_user function that validates USE_REPLIT_AUTH
    replit_user = get_replit_user(request)
    if not replit_user:
        return None
    
    # Get additional user info from headers (safe since get_replit_user validated the request)
    user_id = replit_user['id']
    username = replit_user['name'] 
    user_email = request.headers.get('X-Replit-User-Email')
    profile_image = request.headers.get('X-Replit-User-Profile-Image')
    
    # Store/update user in database
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Upsert user
        cur.execute("""
            INSERT INTO users (id, email, first_name, profile_image_url, created_at, updated_at)
            VALUES (%s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (id) DO UPDATE SET 
                email = EXCLUDED.email,
                first_name = EXCLUDED.first_name,
                profile_image_url = EXCLUDED.profile_image_url,
                updated_at = NOW()
            RETURNING *
        """, (user_id, user_email, username, profile_image))
        
        user = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        
        return {
            'user_id': user_id,
            'username': username,
            'email': user_email,
            'profile_image_url': profile_image,
            'db_user': dict(user) if user else None
        }
        
    except Exception as e:
        print(f"Error getting/creating user: {e}")
        return {
            'user_id': user_id,
            'username': username,
            'email': user_email,
            'profile_image_url': profile_image,
            'db_user': None
        }

def login_required(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        current_user = get_current_user()
        if not current_user:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_user_applications(user_id):
    """Get all applications for a user"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT * FROM applications 
        WHERE user_id = %s 
        ORDER BY created_at DESC
    """, (user_id,))
    
    applications = cur.fetchall()
    cur.close()
    conn.close()
    
    return [dict(app) for app in applications]

def create_application(user_id, application_data):
    """Create a new application"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO applications (
            user_id, company, role, application_date, university, wam,
            status, response_date, priority, notes, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
        RETURNING *
    """, (
        user_id,
        application_data.get('company'),
        application_data.get('role'),
        application_data.get('application_date'),
        application_data.get('university'),
        application_data.get('wam'),
        application_data.get('status', 'Applied'),
        application_data.get('response_date'),
        application_data.get('priority', 'Medium'),
        application_data.get('notes', '')
    ))
    
    application = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    return dict(application)

def update_application(application_id, user_id, application_data):
    """Update an existing application"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        UPDATE applications SET
            company = %s, role = %s, application_date = %s, university = %s,
            wam = %s, status = %s, response_date = %s, priority = %s,
            notes = %s, updated_at = NOW()
        WHERE id = %s AND user_id = %s
        RETURNING *
    """, (
        application_data.get('company'),
        application_data.get('role'),
        application_data.get('application_date'),
        application_data.get('university'),
        application_data.get('wam'),
        application_data.get('status'),
        application_data.get('response_date'),
        application_data.get('priority'),
        application_data.get('notes'),
        application_id,
        user_id
    ))
    
    application = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    return dict(application) if application else None

def delete_application(application_id, user_id):
    """Delete an application"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        DELETE FROM applications 
        WHERE id = %s AND user_id = %s
        RETURNING id
    """, (application_id, user_id))
    
    deleted = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    return deleted is not None

def get_all_submissions():
    """Get all submissions for analytics (public data)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT s.*, u.first_name as user_name 
        FROM submissions s
        LEFT JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC
    """)
    
    submissions = cur.fetchall()
    cur.close()
    conn.close()
    
    return [dict(sub) for sub in submissions]

def create_submission(user_id, submission_data):
    """Create a new submission"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO submissions (
            user_id, company, role, experience_type, theme,
            application_stages, interview_experience, assessment_centre,
            program_structure, salary_benefits, culture_environment,
            hours_workload, practice_areas, general_experience,
            pro_tip, advice, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
        RETURNING *
    """, (
        user_id,
        submission_data.get('company'),
        submission_data.get('role'),
        submission_data.get('experience_type'),
        submission_data.get('theme'),
        submission_data.get('application_stages'),
        submission_data.get('interview_experience'),
        submission_data.get('assessment_centre'),
        submission_data.get('program_structure'),
        submission_data.get('salary_benefits'),
        submission_data.get('culture_environment'),
        submission_data.get('hours_workload'),
        submission_data.get('practice_areas'),
        submission_data.get('general_experience'),
        submission_data.get('pro_tip'),
        submission_data.get('advice')
    ))
    
    submission = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()
    
    return dict(submission)

def get_all_applications():
    """Get all applications for analytics"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT a.*, u.first_name as user_name 
        FROM applications a
        LEFT JOIN users u ON a.user_id = u.id
        ORDER BY a.created_at DESC
    """)
    
    applications = cur.fetchall()
    cur.close()
    conn.close()
    
    return [dict(app) for app in applications]