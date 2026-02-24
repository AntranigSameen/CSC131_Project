#=========
# IMPORTS
#=========

import re

#============
# DATE REGEX
#============

DATE_PATTERNS = r"(\d{1,2})[-/](\d{1,2})[-/](\d{2}|\d{4})"                                  # Patterns (e.g., MM/DD/YYYY, DD-MM-YYYY)

#=============
# Data Parser
#=============

# Parses email content to extract names
def parse_name(emails, keyword):
    results = []

    for email in emails:
        content = email.get("body", {}).get("content", "")
        subject = email.get("subject", "No Subject")

        if keyword in content:
            value = re.sub(r'<.*?>', '', content.split(keyword, 1)[1].strip())              # Remove HTML tags if present
            text_value = re.match(r'\w+', value).group()                                    # Extract only word characters for cleaner output
            
            results.append({"Subject": subject, "Name": text_value})
    return results

# Parses email content to extract dates
def parse_date(emails):
    results = []

    for email in emails:
        content = email.get("body", {}).get("content", "")
        subject = email.get("subject", "No Subject")

        match = re.search(DATE_PATTERNS, content)
        if match:
            results.append({"Subject": subject, "Date": match.group()})
    return results