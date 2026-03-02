## CSC131_Project

This script reads unread emails from an IMAP inbox and extracts basic lead information.
Matching emails are parsed and automatically appended to a Google Sheets worksheet.
Credentials and filters are configured using environment variables (.env).


The application was refactored from legacy IMAP-based email retrieval to Microsoft Graph API using OAuth2 Client Credentials Flow. This transition improves security by eliminating stored passwords and leveraging Azure App Registration for authentication. The system now securely reads Outlook emails and integrates them into Google Sheets using a fully automated pipeline.

## Setup

After cloning this repository, run the appropriate setup script for your operating system to install all required dependencies: 

**Mac/Linux:**
```bash
./scripts/setup.sh
```

**Windows:** (only run this if it doesnt auto run in your powershell if done will prompt user to hit any key)
```powershell
.\scripts\setup.ps1
```

This will:
- Create a virtual environment (`.venv`)
- Install all required Python packages
- Set up the development environment
