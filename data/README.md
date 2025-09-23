# Data Directory

This directory contains data files for the application.

## Security Notice

**Raw datasets must live in a private bucket/database and only aggregated exports are committed to version control.**

### Data Storage Guidelines

- **Raw Data**: Store in private cloud storage (S3, GCS) or secure database
- **Processed Data**: Only commit aggregated, anonymized, or summary data 
- **CSV/JSON Files**: Excluded from git via .gitignore for security
- **Personal Data**: Never commit files containing PII or sensitive information

### What's Safe to Commit

✅ Aggregated statistics and counts  
✅ Anonymized sample data for development  
✅ Data schemas and documentation  
✅ Public reference data  

### What Should Never Be Committed

❌ Raw forum data or user submissions  
❌ API keys, credentials, or secrets  
❌ Personal information or contact details  
❌ Large datasets (>10MB)

For questions about data handling, consult the security team.