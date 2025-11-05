# Overview

GradGuide is a production-ready Flask web application for law students and graduates to track job applications and share authentic experiences about law firms and graduate programs. The system uses custom authentication (username/email and password), PostgreSQL database, automated quality control for submissions, and smart categorization to help users find relevant advice easily.

# Recent Changes

## November 5, 2025
- **Career Match Feature**: Created intelligent law firm matching system
  - Multi-factor scoring algorithm (university representation, WAM competitiveness, practice area alignment, preferences)
  - Scores based on: university match (30pts), WAM (25pts), practice area (20pts), preference alignment (15pts), location (10pts)
  - Firm profiles include prestige, salary, work-life balance, and training ratings
  - Results page shows top 8 matches with detailed reasoning and firm attributes
  - Route: `/law-match` with GET (form) and POST (results) handlers
- **Submission Validation**: Relaxed requirements to accept any Step 2 content
  - Now accepts submissions with ANY single field filled (10 fields total)
  - Removed strict word count and generic phrase checking
  - Trusts users to provide valuable content
- **CSRF Security**: Fixed all 6 forms to use proper hidden input field format
- **WAM Field**: Added to submission form and results display

# Recent Changes (Archive)

## October 2025: Production Refactoring
- **Migrated from Flask dev server to Gunicorn** with 2 workers and 4 threads per worker
- **Implemented app factory pattern** with modular blueprint architecture
- **Added comprehensive security**: CSRF protection, rate limiting (Flask-Limiter), HTTPS headers (Talisman)
- **Restructured codebase**: Created `server/` package with `__init__.py` (app factory), `views_public.py` (blueprint routes), `support.py` (shared utilities), and `caching.py` (analytics caching)
- **Enhanced error handling**: Custom 404 and 500 error pages with branded design
- **Optimized caching**: Implemented cache headers (1 year for static assets, no-cache for dynamic pages)
- **Added CSRF tokens to all forms**: login, register, submit, tracker, law match, and report forms
- **Environment-aware security**: Talisman disabled in Replit development, enabled in production deployment

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Core Application Stack
- **Backend Framework**: Flask 3.0.3 with app factory pattern and blueprints
- **Production Server**: Gunicorn 22.0.0 (2 workers, 4 threads/worker)
- **Template Engine**: Jinja2 for server-side rendering
- **Database**: PostgreSQL (Neon-backed) for users, submissions, and applications
- **Data Storage**: Legacy JSON files + PostgreSQL database
- **Frontend**: HTML/CSS with Bootstrap 5.3 and custom styling
- **Authentication**: Custom auth system with bcrypt password hashing

## Data Processing Pipeline
- **CSV Data Sources**: Multiple forum data files (law_raw.csv, law_whirlpool_2018_2025.csv, raw_all.csv)
- **Content Processing**: Multi-stage cleaning and filtering system to remove forum metadata
- **Quality Scoring**: Rule-based scoring system for experience quality and relevance
- **Content Categorization**: Automatic classification into 11 categories (application timeline, selection process, pay/benefits, etc.)
- **Firm Matching**: Alias-based system for mapping firm variations to canonical names

## Key Features
- **Experience Submission System**: Form-based user experience collection with flexible validation
- **Data-Assisted Drafting**: CSV-backed auto-population of experience forms
- **Company Analytics**: Aggregated firm statistics and program information
- **Career Match Tool**: Intelligent firm recommendation system based on university, WAM, practice area interests, and preferences
- **Content Filtering**: Answer-focused filtering excluding questions and low-quality posts
- **Legal Compliance**: Australian compliance pages for user-generated content platforms

## File Organization
```
├── main.py (Application entry point, exports app for Gunicorn)
├── server/ (Production application package)
│   ├── __init__.py (App factory with security setup)
│   ├── views_public.py (Blueprint with all routes)
│   ├── support.py (Shared utilities and constants)
│   └── caching.py (LRU caching for analytics)
├── submissions.json (Legacy user submissions)
├── applications.json (Legacy application tracking)
├── templates/ (Jinja2 templates with CSRF tokens)
├── static/ (CSS, JS assets)
├── db_auth.py (Database operations for PostgreSQL)
├── auth_utils.py (Authentication helpers)
├── security.py (Security configuration)
├── story_vetting.py (Quality control for submissions)
├── extractors.py (Firm aliases and data extraction)
├── categorizer.py (Content classification)
├── experience_*.py (Quality filtering pipelines)
├── grad_data*.py (CSV data processing)
├── legal_config.py (Compliance configuration)
├── Procfile (Gunicorn deployment configuration)
└── out/ (Processed data outputs)
```

## Data Models
- **Submissions**: Company, role, experience type, application stages, interview experience, advice, salary data
- **Applications**: User application tracking with status, dates, and notes
- **Processed Experiences**: Cleaned forum posts with quality scores and categories
- **Firm Analytics**: Aggregated statistics including salary ranges, program types, and application timelines

# External Dependencies

## Required Python Packages
- **Flask 3.0.3**: Web framework with app factory pattern
- **Gunicorn 22.0.0**: Production WSGI server
- **Flask-WTF**: CSRF protection for forms
- **Flask-Limiter**: Rate limiting (100 requests/minute default)
- **Flask-Talisman**: HTTPS enforcement and security headers
- **Flask-CORS**: Cross-origin resource sharing
- **psycopg2-binary**: PostgreSQL database adapter
- **bcrypt** (via Werkzeug): Password hashing for authentication
- **rapidfuzz**: Fuzzy string matching for company name normalization
- **pandas**: Data manipulation and CSV processing
- **python-dateutil**: Date parsing and handling
- **pyarrow**: Parquet file support for data storage

## Security & Authentication
- **Custom Authentication**: Username/email + password with bcrypt hashing
- **CSRF Protection**: Flask-WTF with tokens in all forms
- **Rate Limiting**: Flask-Limiter with configurable limits per route (10/min login, 5/min registration, 30/hour submissions)
- **HTTPS Enforcement**: Flask-Talisman in production (disabled in Replit dev for easier testing)
- **Secure Sessions**: HTTP-only, secure cookies with SameSite=Lax
- **Password Requirements**: Minimum 8 characters with uppercase, lowercase, and numbers

## Frontend Libraries
- **Bootstrap 5.3**: CSS framework via CDN
- **Google Fonts**: Inter and Nunito font families
- **Custom CSS**: Additional styling for specialized components

## Data Sources
- **Forum CSVs**: Whirlpool forum data with thread titles, content, timestamps
- **User Submissions**: Direct form submissions via Flask routes
- **Legal Templates**: Australian compliance page templates

## Potential Future Integrations
- **Webhook Support**: Configured for Tally/Formspree/Make webhook integration
- **Analytics**: Google Analytics integration mentioned in legal config
- **External Services**: Airtable, Softr, Zapier/Make, Discord integrations planned