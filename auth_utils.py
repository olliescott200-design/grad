import os
import psycopg2
import psycopg2.extras
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session, request
from datetime import datetime, timedelta
import re

def get_db_connection():
    """Get database connection"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)

def is_valid_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def is_valid_password(password):
    """
    Validate password strength:
    - At least 8 characters
    - Contains at least one uppercase letter
    - Contains at least one lowercase letter  
    - Contains at least one digit
    """
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    
    if not re.search(r'\d', password):
        return False, "Password must contain at least one number"
    
    return True, ""

def create_user(email, username, password, first_name="", last_name=""):
    """Create a new user with hashed password"""
    
    # Validate inputs
    if not is_valid_email(email):
        return False, "Invalid email format"
    
    is_valid, password_msg = is_valid_password(password)
    if not is_valid:
        return False, password_msg
    
    if len(username) < 3 or len(username) > 50:
        return False, "Username must be between 3 and 50 characters"
    
    # Check if username contains only valid characters
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return False, "Username can only contain letters, numbers, hyphens, and underscores"
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Check if user already exists
        cur.execute("SELECT id FROM users WHERE email = %s OR username = %s", (email, username))
        if cur.fetchone():
            return False, "User with this email or username already exists"
        
        # Hash password
        password_hash = generate_password_hash(password, method='pbkdf2:sha256')
        
        # Insert new user
        cur.execute("""
            INSERT INTO users (email, username, password_hash, first_name, last_name, is_active, is_email_verified)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (email, username, password_hash, first_name, last_name, True, False))
        
        user_id = cur.fetchone()['id']
        conn.commit()
        
        return True, user_id
        
    except psycopg2.IntegrityError as e:
        conn.rollback()
        if 'email' in str(e):
            return False, "Email already exists"
        elif 'username' in str(e):
            return False, "Username already exists"
        else:
            return False, "User already exists"
    finally:
        cur.close()
        conn.close()

def authenticate_user(login, password):
    """
    Authenticate user with email/username and password
    Returns user dict if successful, None if failed
    Handles account lockout for security
    """
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Find user by email or username
        cur.execute("""
            SELECT id, email, username, password_hash, first_name, last_name, 
                   is_active, failed_login_attempts, locked_until
            FROM users 
            WHERE (email = %s OR username = %s) AND is_active = TRUE
        """, (login, login))
        
        user = cur.fetchone()
        
        if not user:
            return None
        
        # Check if account is locked
        if user['locked_until'] and user['locked_until'] > datetime.now():
            return None
        
        # Check password
        if check_password_hash(user['password_hash'], password):
            # Reset failed attempts on successful login
            cur.execute("""
                UPDATE users 
                SET failed_login_attempts = 0, locked_until = NULL 
                WHERE id = %s
            """, (user['id'],))
            conn.commit()
            
            # Return user info (without password_hash)
            return {
                'id': user['id'],
                'email': user['email'], 
                'username': user['username'],
                'first_name': user['first_name'],
                'last_name': user['last_name']
            }
        else:
            # Increment failed attempts
            failed_attempts = user['failed_login_attempts'] + 1
            locked_until = None
            
            # Lock account after 5 failed attempts for 15 minutes
            if failed_attempts >= 5:
                locked_until = datetime.now() + timedelta(minutes=15)
            
            cur.execute("""
                UPDATE users 
                SET failed_login_attempts = %s, locked_until = %s
                WHERE id = %s
            """, (failed_attempts, locked_until, user['id']))
            conn.commit()
            
            return None
            
    finally:
        cur.close()
        conn.close()

def get_user_by_id(user_id):
    """Get user by ID"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            SELECT id, email, username, first_name, last_name, is_active
            FROM users 
            WHERE id = %s AND is_active = TRUE
        """, (user_id,))
        
        user = cur.fetchone()
        return dict(user) if user else None
        
    finally:
        cur.close()
        conn.close()

def login_user(user_id):
    """Store user ID in session"""
    session['user_id'] = user_id
    session.permanent = True

def logout_user():
    """Remove user from session"""
    session.pop('user_id', None)

def get_current_user():
    """Get current logged-in user from session"""
    user_id = session.get('user_id')
    if not user_id:
        return None
    
    return get_user_by_id(user_id)

def login_required(f):
    """Decorator to require login for a route"""
    from functools import wraps
    from flask import redirect, url_for, flash
    
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not get_current_user():
            flash('You need to log in to access this page.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function