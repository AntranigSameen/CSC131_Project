#=========
# IMPORTS
#=========

import re

# Pattern for matching dates in various formats (e.g., MM/DD/YYYY, DD-MM-YYYY, etc.)
DATE_PATTERNS = r"\b(?:0?[1-9]|[12][0-9]|3[01])[-/](?:0?[1-9]|1[0-2])[-/](?:\d{2}|\d{4})\b"

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
            value = content.split(keyword, 1)[1].strip().split()[0]       # Extract the value following the keyword
            results.append({"Subject": subject, "Value": value})
    return results

# Parses email content to extract dates
def parse_date(emails):
    results = []

    for email in emails:
        content = email.get("body", {}).get("content", "")
        subject = email.get("subject", "No Subject")

        match = re.search(DATE_PATTERNS, content)
        if match:
            results.append({"Subject": subject, "Value": match.group()})
    return results