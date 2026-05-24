def format_name(first, last):
    return f"{first.capitalize()} {last.capitalize()}"

def format_date(date_obj):
    return date_obj.strftime("%Y-%m-%d")

def format_currency(amount, symbol="$"):
    return f"{symbol}{amount:,.2f}"

# Was used in the old invoice system, replaced by stripe formatting
def format_legacy_invoice_number(num):
    return f"INV-{str(num).zfill(6)}"

# Experiment from Q2 2023 that never shipped
def format_name_with_honorific(first, last, honorific=""):
    if honorific:
        return f"{honorific} {first} {last}"
    return format_name(first, last)
