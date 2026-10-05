"""Atomic UTF-8-BOM CSV/JSON writes, identities, and Windows-safe filenames."""
import csv
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

FIELDS = ['rank', 'product_id', 'product_name', 'price', 'listed_at', 'country',
          'shop', 'category', 'commission', 'sales_period', 'sales_growth',
          'gmv_period', 'total_sales', 'total_gmv', 'scraped_at', 'country_filter',
          'shop_type_filter', 'l1_category', 'l2_category', 'l3_category',
          'category_path', 'period', 'page']


def sanitize_filename(value, limit=140):
    text = unicodedata.normalize('NFKC', value)
    text = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', text).strip(' .')
    if not text:
        text = '_'
    if re.match(r'^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', text, re.I):
        text = '_' + text
    # Avoid splitting surrogate pairs: Python slices code points.
    return text[:limit].rstrip(' .') or '_'


def category_filename(item):
    text = item['l2'] + '__' + item['l3']
    # Always add path hash: case-insensitive names / truncation / sanitized collisions.
    suffix = hashlib.sha256(item['path'].encode()).hexdigest()[:10]
    return sanitize_filename(text) + '__' + suffix + '.csv'


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC', str(text or '')).casefold().split())


def identity(row):
    pid = str(row.get('product_id') or '').strip()
    if pid:
        return 'id:' + pid
    name, shop = normalize(row.get('product_name')), normalize(row.get('shop'))
    return 'name:' + name + '\x1f' + shop if name and shop else None


def atomic_write(path, writer, *, encoding='utf-8'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding=encoding, newline='') as stream:
            writer(stream)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_csv(path, rows, fields=FIELDS):
    def writer(stream):
        output = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        output.writeheader()
        output.writerows(rows)
    atomic_write(path, writer, encoding='utf-8-sig')


def write_json(path, obj):
    atomic_write(path, lambda stream: json.dump(obj, stream, ensure_ascii=False, indent=2))


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
