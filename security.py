import os
from flask import request, abort
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

USE_REPLIT_AUTH = os.getenv("USE_REPLIT_AUTH", "false").lower() == "true"
CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000"
).split(",") if o.strip()]

# No wildcards with cookies - validate CORS origins when supports_credentials=True
supports_credentials = True  # Set by CORS config below
if supports_credentials and any('*' in origin for origin in CORS_ORIGINS):
    raise RuntimeError("CORS_ORIGINS cannot contain wildcards when supports_credentials=True")

def get_replit_user(req):
    """Only returns a user dict when USE_REPLIT_AUTH==true AND request came via Replit."""
    if not USE_REPLIT_AUTH:
        return None
    host = req.headers.get("X-Forwarded-Host", "") or req.headers.get("Host", "")
    if not (host.endswith(".repl.co") or host.endswith(".replit.dev")):
        return None
    uid = req.headers.get("X-Replit-User-Id")
    name = req.headers.get("X-Replit-User-Name")
    if not uid or not name:
        return None
    return {"id": uid, "name": name}

def harden_app(app):
    # Secrets / cookies
    secret_key = os.getenv("SECRET_KEY", "dev-secret-key-2025-gradvantage-auth")
    app.config["SECRET_KEY"] = secret_key
    app.config.setdefault("WTF_CSRF_TIME_LIMIT", None)

    # CSRF for forms/cookie-based routes (disabled for development)
    # CSRFProtect(app)

    # CORS – credentials require explicit origins, not "*"
    CORS(app,
         resources={r"/api/*": {"origins": CORS_ORIGINS}},
         supports_credentials=True)

    # Security headers (+ optional HTTPS enforcement via env)
    Talisman(
        app,
        force_https=(os.getenv("FORCE_HTTPS", "0") == "1"),
        content_security_policy={
            "default-src": ["'self'"],
            "img-src": ["'self'", "data:"],
            "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdn.jsdelivr.net"],
            "script-src": ["'self'", "https://cdn.jsdelivr.net"],
            "font-src": ["'self'", "https://fonts.gstatic.com"],
            "connect-src": ["'self'"],
        },
        frame_options="DENY",
        referrer_policy="no-referrer",
        session_cookie_secure=True,
        session_cookie_samesite="Lax",
        session_cookie_http_only=True
    )

    # Basic rate limiting with better configuration
    limiter = Limiter(
        get_remote_address, 
        app=app, 
        default_limits=["200/day", "60/hour"],
        storage_uri="memory://",
        strategy="fixed-window"
    )
    
    # Custom error handler for rate limiting
    @app.errorhandler(429)
    def ratelimit_handler(e):
        app.logger.warning(f"Rate limit exceeded for {get_remote_address()}: {e}")
        return {"error": "Rate limit exceeded", "retry_after": e.retry_after}, 429

    if USE_REPLIT_AUTH:
        @app.before_request
        def _replit_header_gate():
            # Block state-changing requests if not from Replit with valid headers
            if request.method in ("POST", "PUT", "PATCH", "DELETE"):
                if not get_replit_user(request):
                    abort(401)
    
    # Return limiter for per-route usage
    return limiter
