"""Sales parser: match semantic headers; never infer td positions.

Runtime header aliases must be confirmed in the DOM profile. English canonical
field names are also accepted for offline fixtures. Unknown columns keep their
position; missing fields stay empty; duplicate mapped columns are rejected.
"""
import re
from urllib.parse import parse_qs, unquote, urlparse
from exceptions import ParseError
from sales_io import FIELDS, normalize

CORE_FIELDS = FIELDS[:14]


def build_schema(headers, aliases=None):
    names = {normalize(k): k for k in CORE_FIELDS}
    names.update({normalize(label): field for label, field in (aliases or {}).items()})
    result = {}
    for index, header in enumerate(headers):
        field = names.get(normalize(header))
        if field and field in result:
            raise ParseError(f'重复表头映射：{header} -> {field}')
        if field:
            if field not in CORE_FIELDS:
                raise ParseError(f'不支持的表头字段：{field}')
            result[field] = index
    if not {'product_name', 'sales_period'} <= result.keys():
        raise ParseError(f'无法确认商品与周期销量表头：{headers}')
    return result


def product_id_from_url(href):
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    for key in ('product_id', 'productId', 'item_id', 'itemId'):
        if len(query.get(key, [])) == 1 and query[key][0].strip():
            return query[key][0].strip()
    # Product-cell links only; do not scan links in shop/action columns.
    match = re.search(r'/(?:product|products|detail)/(?:[^/]+/)?(\d+)(?:/)?$', unquote(parsed.path))
    return match.group(1) if match else ''


def parse_row(headers, cells, aliases=None, product_labels=None):
    schema = build_schema(headers, aliases)
    if len(cells) != len(headers):
        raise ParseError(f'表头/单元格数量不一致：{len(headers)} / {len(cells)}')
    if all(not (c.get('text', '') if isinstance(c, dict) else str(c)).strip() for c in cells):
        return None
    row = {key: '' for key in CORE_FIELDS}
    for field, index in schema.items():
        cell = cells[index]
        row[field] = (cell.get('text', '') if isinstance(cell, dict) else str(cell)).strip()
    product_cell = cells[schema['product_name']]
    text = row['product_name']
    parts = [line.strip() for line in text.splitlines() if line.strip()]
    if isinstance(product_cell, dict) and product_cell.get('name'):
        row['product_name'] = product_cell['name'].strip()
    else:
        row['product_name'] = parts[0] if parts else ''
    # Composite product fields have observed label prefixes, passed by profile.
    for field, prefixes in (product_labels or {}).items():
        if field not in ('price', 'listed_at'):
            continue
        for line in parts[1:]:
            for prefix in prefixes:
                if line.startswith(prefix):
                    row[field] = line[len(prefix):].lstrip('：: ').strip()
    shop_cell = cells[schema['shop']] if 'shop' in schema else None
    if isinstance(shop_cell, dict) and shop_cell.get('name'):
        row['shop'] = shop_cell['name'].strip()
    elif row['shop']:
        row['shop'] = row['shop'].splitlines()[0].strip()
    if isinstance(product_cell, dict):
        ids = {product_id_from_url(href) for href in product_cell.get('links', [])}
        ids.discard('')
        if len(ids) > 1:
            raise ParseError('商品单元格存在多个不同 product_id。')
        if ids:
            row['product_id'] = next(iter(ids))
    if not row['product_name']:
        raise ParseError('非空数据行缺少商品名。')
    return row


def parse_table(payload, aliases=None, product_labels=None):
    if not isinstance(payload, dict) or not isinstance(payload.get('headers'), list):
        raise ParseError('销量表结构无效。')
    headers = payload['headers']
    build_schema(headers, aliases)
    result = []
    for cells in payload.get('rows', []):
        row = parse_row(headers, cells, aliases, product_labels)
        if row:
            result.append(row)
    return result
