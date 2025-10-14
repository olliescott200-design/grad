import os
from flask import Flask, request, render_template
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman

def create_app():
    """Create and configure the Flask application with production settings."""
    app = Flask(
        __name__, 
        template_folder="../templates", 
        static_folder="../static"
    )

    # Base config
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-me")
    app.config["ENV"] = os.getenv("FLASK_ENV", "production")
    app.config["PREFERRED_URL_SCHEME"] = "https"
    
    # Session config
    app.config["SESSION_COOKIE_SECURE"] = True
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    
    # Development overrides
    if os.getenv("FLASK_DEBUG") == "1":
        app.config["ENV"] = "development"
        app.config["DEBUG"] = True
        app.config["SESSION_COOKIE_SECURE"] = False

    # Security - CSRF Protection
    csrf = CSRFProtect(app)
    
    # Security - Rate Limiting
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=["100 per minute"],
        storage_uri="memory://"
    )
    
    # Security - HTTPS and security headers (but allow for CSP in templates)
    # Only enable in production deployment (not in Replit dev environment)
    if os.getenv("FLASK_DEBUG") != "1" and not os.getenv("REPL_SLUG"):
        Talisman(
            app,
            force_https=True,
            content_security_policy=None,  # Handled per-template
            strict_transport_security=True,
            session_cookie_secure=True
        )

    # Cache headers for static assets
    @app.after_request
    def add_cache_headers(resp):
        """Add appropriate cache headers based on content type."""
        try:
            if request.path.startswith("/static/"):
                # Cache static assets for 1 year
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                # Don't cache dynamic pages (prevents stale data)
                resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                resp.headers["Pragma"] = "no-cache"
                resp.headers["Expires"] = "0"
        except Exception:
            pass
        return resp

    # Register blueprints
    from .views_public import create_blueprint
    public_bp = create_blueprint(limiter)
    app.register_blueprint(public_bp)

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500
    
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return render_template("429.html" if os.path.exists("templates/429.html") else "500.html"), 429

    return app
