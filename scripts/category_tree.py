"""Discover L1 -> every L2 -> every L3 from investigated filter scope."""
import json
from pathlib import Path
from exceptions import CategoryDiscoveryError
from sales_io import write_json


def validate_categories(items, root):
    if not isinstance(items, list) or not items:
        raise CategoryDiscoveryError('三级类目缓存为空或不是数组。')
    result = {}
    for item in items:
        if not isinstance(item, dict) or any(not isinstance(item.get(k), str) or not item[k].strip()
                                             for k in ('l1', 'l2', 'l3', 'path')):
            raise CategoryDiscoveryError(f'三级类目缺少层级字段：{item}')
        if item['l1'] != root or item['path'] != '>'.join(item[k] for k in ('l1', 'l2', 'l3')):
            raise CategoryDiscoveryError(f'类目路径与根类目不一致：{item}')
        if any('>' in item[k] for k in ('l1', 'l2', 'l3')):
            raise CategoryDiscoveryError('类目名称含路径分隔符。')
        result[item['path']] = {**{key: item[key] for key in ('l1', 'l2', 'l3', 'path')},
                                'category_id': item.get('category_id')}
    return [result[path] for path in sorted(result)]


def read_cache(path, root):
    try:
        return validate_categories(json.loads(Path(path).read_text(encoding='utf-8-sig')), root)
    except (OSError, ValueError) as exc:
        raise CategoryDiscoveryError(f'类目缓存无法读取：{path}：{exc}') from exc


def discover_categories(browser, *, country, shop_type, root, cache):
    browser.navigate()
    expected = {}
    for dim, label in [('country', country), ('shop_type', shop_type), ('l1', root)]:
        expected[dim] = label
        browser.select(dim, label, expected)
    items = []
    for l2 in browser.options(2, expected):
        selected = {**expected, 'l2': l2['label']}
        browser.select('l2', l2['label'], selected)
        for l3 in browser.options(3, selected):
            item = {'l1': root, 'l2': l2['label'], 'l3': l3['label'],
                    'path': '>'.join([root, l2['label'], l3['label']]), 'category_id': l3['id']}
            items.append(item)
    items = validate_categories(items, root)
    # No partial category cache is published if any L2 branch failed.
    write_json(cache, items)
    return items
