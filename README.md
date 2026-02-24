# CSC131_Project

This script reads unread emails from an IMAP inbox and extracts basic lead information.
Matching emails are parsed and automatically appended to a Google Sheets worksheet.
Credentials and filters are configured using environment variables (.env).


The application was refactored from legacy IMAP-based email retrieval to Microsoft Graph API using OAuth2 Client Credentials Flow. This transition improves security by eliminating stored passwords and leveraging Azure App Registration for authentication. The system now securely reads Outlook emails and integrates them into Google Sheets using a fully automated pipeline.
