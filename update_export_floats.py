import re

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    if 'to_decimal' not in content:
        content = content.replace('to_float,', 'to_float,\n    to_decimal,')
        content = 'from decimal import Decimal\n' + content

    content = re.sub(r'float\(([^)]*?)\s+or\s+0\)', r'to_decimal(\1)', content)
    content = re.sub(r'float\(([^)]*?\.get\("[^"]+"\).*?)\)', r'to_decimal(\1)', content)
    content = re.sub(r'float\(acc_current\)', r'to_decimal(acc_current)', content)
    content = re.sub(r'float\(acc_projected\)', r'to_decimal(acc_projected)', content)
    content = re.sub(r'float\(total_projected\)', r'to_decimal(total_projected)', content)
    content = re.sub(r'float\((isa_logged_by_account[^)]*?)\)', r'to_decimal(\1)', content)
    content = re.sub(r'float\((pension_logged[^)]*?)\)', r'to_decimal(\1)', content)
    content = re.sub(r'float\((allowance)\)', r'to_decimal(\1)', content)
    content = content.replace('to_float(', 'to_decimal(')

    # Match 0.0 when surrounded by specific delimiters
    content = re.sub(r'(?<=[=\[ (,:])0\.0(?=[ ,\]):+])', 'Decimal("0.0")', content)

    data_row_old = "    for col, val in enumerate(values, 1):"
    data_row_new = "    for col, val in enumerate(values, 1):\n        if hasattr(val, 'quantize'):\n            val = float(val)"
    content = content.replace(data_row_old, data_row_new)

    with open(filepath, 'w') as f:
        f.write(content)

update_file('app/routes/export.py')
print("Update complete")
