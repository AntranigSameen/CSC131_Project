#=========
# IMPORTS
#=========

import os

#=============
# OUTPUT FILE
#=============

OUTPUT_FILE = "extracted_data.txt"

#===========================
# Store Data in a Text File
#===========================

def store_data(name, date):
    date_find = {entry["Subject"]: entry["Date"] for entry in date}                     # Create a mapping of subjects to dates for easy lookup

    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        for name_entry in name:
            subject = name_entry["Subject"]
            name_value = name_entry["Name"]
            date_value = date_find.get(subject, "")                                     # Get the corresponding date or use an empty string if not found

            line = f"{subject},{name_value},{date_value}\n"
            f.write(line)