"""Strict numeric parsing: missing/ambiguous values never become zero."""
import math
import re
import unicodedata

_NUMBER = re.compile(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([kKmMbB万亿]?)\s*(%?)')
_MULT = {'': 1, 'K': 1000, 'M': 1000000, 'B': 1000000000,
         '万': 10000, '亿': 100000000}


def parse_value(value, *, percent_as_fraction=False):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    text = unicodedata.normalize('NFKC', str(value)).strip().replace('−', '-')
    text = re.sub(r'^(?:SGD|USD|CNY|RMB|MYR|S\$|US\$|[$¥€£])\s*', '', text, flags=re.I)
    # Validate thousands separators instead of turning '1,2' into 12.
    if ',' in text:
        numeric_part = re.match(r'[+-]?[\d,]+', text).group(0) if re.match(r'[+-]?[\d,]+', text) else ''
        if not re.fullmatch(r'[+-]?\d{1,3}(?:,\d{3})+', numeric_part):
            return None
        text = text.replace(',', '')
    match = _NUMBER.fullmatch(text)
    if not match:
        return None
    number, unit, pct = match.groups()
    if unit and pct:
        return None
    result = float(number) * _MULT[unit.upper() if unit.isascii() else unit]
    if pct and percent_as_fraction:
        result /= 100
    return result if math.isfinite(result) else None
