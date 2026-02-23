import gspread
import smtplib
from email.mime.text import MIMEText
from oauth2client.service_account import ServiceAccountCredentials

# 1. Google Sheets Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
#add JSON file here, Example: C:\Users\admin\Desktop\apikey.json
creds = ServiceAccountCredentials.from_json_keyfile_name(r"ADD THE LOCATION OF YOUR apikey.json FILE HERE", scope)
client = gspread.authorize(creds)
sheet_id = "https://docs.google.com/spreadsheets/d/13_cxh-bfXh9ZCITZTaz3bsUWLLJHyHeoHpyvYB_DuFI/edit?gid=0#gid=0"
# Open the sheet by name or URL
sheet = client.open_by_url(sheet_id)
worksheet = sheet.get_worksheet(0)
data = worksheet.find("EMAIL")
print(data)
