"""
GradGuide - Production entry point.
Flask application for law students and graduates to track applications and share experiences.
"""
import os
from server import create_app

# Load environment variables in development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Create Flask app using factory pattern
app = create_app()

# For backward compatibility - expose these so existing imports don't break
from server.support import (
    normalize_company_name, 
    is_helpful_advice,
    FIRM_UNIVERSITY_DATA,
    data_file,
    tracker_file
)

# Validate SECRET_KEY is set
secret_key = app.config.get("SECRET_KEY")
if secret_key in (None, "", "change-me", "please_change_me"):
    if os.getenv("REPL_SLUG"):
        print("⚠️  WARNING: Using default SECRET_KEY in development. Set SECRET_KEY environment variable for production.")
    else:
        raise RuntimeError("SECRET_KEY must be set via environment variable for security")

# Initialize JSON data files if they don't exist
import json
for data_path in [data_file, tracker_file]:
    if not os.path.exists(data_path):
        with open(data_path, 'w') as f:
            json.dump([], f)

if __name__ == '__main__':
    # Development server (use Gunicorn in production via Procfile)
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG") == "1"
    
    print(f"🚀 Starting GradGuide on port {port} (debug={'ON' if debug else 'OFF'})")
    app.run(host='0.0.0.0', port=port, debug=debug)
