import re
import os

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Import to_decimal if not there
    if 'to_decimal' not in content:
        content = content.replace('from app.calculations import (', 'from app.calculations import (\n    to_decimal,')
    
    # Replace float(x or 0) with to_decimal(x)
    content = re.sub(r'float\(([^)]*?)\s+or\s+0\)', r'to_decimal(\1)', content)
    
    # Replace remaining float(x) with to_decimal(x)
    # Caution: only match safe occurrences like float(payload.get(...))
    content = re.sub(r'float\((payload\.get\("[^"]+"\))\)', r'to_decimal(\1)', content)
    content = re.sub(r'float\((payload\["[^"]+"\])\)', r'to_decimal(\1)', content)
    
    with open(filepath, 'w') as f:
        f.write(content)

update_file('app/models/planning_allowances.py')
update_file('app/models/planning_reviews.py')

print("Update complete")
