def safe_csv_cell(value):
    text = str(value)
    if text.lstrip(" \t\r\n").startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{text}"
    return text
