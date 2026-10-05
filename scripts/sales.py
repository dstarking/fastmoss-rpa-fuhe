"""Fail-closed single-leaf sales collector and resumable category batch."""
import json
from datetime import datetime, timezone
from pathlib import Path
from category_tree import discover_categories, read_cache
from exceptions import FastMossError, FilterVerificationError, NoDataError, ParseError
from sales_browser import SalesBrowser, load_profile
from sales_io import (category_filename, file_hash, identity, read_csv, write_csv, write_json, log)
from sales_parser import parse_table
from value_parser import parse_value


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def request_spec(*, country, shop_type, category_path, period, pages, profile):
    return dict(country=country, shop_type=shop_type, category_path=category_path,
                period=period, pages=pages, profile_sha256=profile['_sha256'])


def verify_rows(rows, *, country, shop_type, category_path, period):
    parts = category_path.split('>')
    if len(parts) != 3:
        raise FilterVerificationError('必须选择准确的三级类目路径。')
    if not rows:
        raise NoDataError('没有可核验的商品数据。')
    for row in rows:
        required = {'country_filter': country, 'shop_type_filter': shop_type,
                    'category_path': category_path, 'period': period,
                    'l1_category': parts[0], 'l2_category': parts[1], 'l3_category': parts[2]}
        if any(row.get(k) != value for k, value in required.items()):
            raise FilterVerificationError(f'CSV 元数据与请求不一致：{row.get("product_name")}')
        # If page provides country/category values, they must match independently.
        if row.get('country') and row['country'] != country:
            raise FilterVerificationError(f'数据行国家不一致：{row["country"]}，所选={country}')
        if row.get('category') and row['category'] not in (parts[2], category_path):
            raise FilterVerificationError(f'数据行类目不一致：{row["category"]}，所选={category_path}')
        if not identity(row):
            raise ParseError('商品缺少 product_id，且商品名 + 店铺也无法建立身份。')
        sales = parse_value(row.get('sales_period'))
        if sales is None or sales < 0:
            raise ParseError(f'周期销量不可解析：{row.get("sales_period")}')


def scrape_sales(browser, *, country, shop_type, category_path, period, pages, out):
    parts = [part.strip() for part in category_path.split('>')]
    if len(parts) != 3 or not all(parts):
        raise FilterVerificationError('--category-path 必须是一级>二级>三级，不能只填父类目。')
    category_path = '>'.join(parts)
    if pages < 1:
        raise FilterVerificationError('--pages 必须 >= 1。')
    browser.navigate()
    expected = {}
    labels = [('country', country), ('shop_type', shop_type),
              *zip(('l1', 'l2', 'l3'), parts),
              ('period', browser.profile['period_labels'][period])]
    for dim, label in labels:
        expected[dim] = label
        browser.select(dim, label, expected)
    browser.wait_for({**expected, 'page': 1})
    output, seen = [], set()
    evidence = []
    for page in range(1, pages + 1):
        payload, state = browser.extract(expected, page)
        rows = parse_table(payload, browser.profile['header_aliases'], browser.profile.get('product_labels'))
        if not rows:
            raise NoDataError(f'第 {page} 页无商品。禁止发布部分文件。')
        for row in rows:
            row.update(scraped_at=utc_now(), country_filter=country, shop_type_filter=shop_type,
                       l1_category=parts[0], l2_category=parts[1], l3_category=parts[2],
                       category_path=category_path, period=period, page=page)
        verify_rows(rows, country=country, shop_type=shop_type, category_path=category_path, period=period)
        keys = [identity(row) for row in rows]
        if len(set(keys)) != len(keys) or any(key in seen for key in keys):
            raise FilterVerificationError(f'第 {page} 页包含重复商品，可能分页没有刷新。')
        seen.update(keys)
        output.extend(rows)
        evidence.append({'page': page, 'revision': state['revision'], 'data_filters': state['data_filters']})
        if page < pages and not browser.next_page(expected, page):
            break
    # Nothing is written until ALL collected pages and requested filters verify.
    write_csv(out, output)
    spec = request_spec(country=country, shop_type=shop_type, category_path=category_path,
                        period=period, pages=pages, profile=browser.profile)
    receipt = dict(request=spec, completed_at=utc_now(), rows=len(output),
                   pages_collected=len(evidence), sha256=file_hash(out), evidence=evidence)
    write_json(str(out) + '.receipt.json', receipt)
    return receipt


def reusable(entry, spec, path):
    if entry.get('status') != 'success' or entry.get('request') != spec or not path.is_file():
        return False
    try:
        receipt = json.loads(Path(str(path) + '.receipt.json').read_text(encoding='utf-8'))
        if (entry.get('sha256') != file_hash(path) or receipt.get('sha256') != entry['sha256']
                or receipt.get('request') != spec):
            return False
        rows = read_csv(path)
        if len(rows) != entry.get('rows') or len(rows) != receipt.get('rows'):
            return False
        verify_rows(rows, **{key: spec[key] for key in ('country', 'shop_type', 'category_path', 'period')})
        return True
    except (FastMossError, OSError, ValueError, KeyError):
        return False


def collect_batch(browser, items, *, country, shop_type, period, pages, out_dir,
                  retries=2, resume=False, collect=scrape_sales):
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    manifest_path = directory / '_manifest.json'
    previous = {}
    if resume and manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding='utf-8')).get('categories', {})
        except (ValueError, OSError):
            previous = {}
    manifest = {'version': 1, 'started_at': utc_now(), 'period': period, 'country': country,
                'shop_type': shop_type, 'pages': pages, 'profile_sha256': browser.profile['_sha256'],
                'categories': {}}
    failed, merged = [], []
    for item in items:
        path = directory / category_filename(item)
        spec = request_spec(country=country, shop_type=shop_type, category_path=item['path'],
                            period=period, pages=pages, profile=browser.profile)
        prior = previous.get(item['path'], {})
        if resume and reusable(prior, spec, path):
            entry = {**prior, 'resumed': True}
        else:
            entry = {'request': spec, 'file': path.name, 'status': 'failed'}
            errors = []
            for attempt in range(retries + 1):
                try:
                    receipt = collect(browser, country=country, shop_type=shop_type,
                                      category_path=item['path'], period=period, pages=pages, out=path)
                    entry.update(receipt, status='success', attempts=attempt + 1)
                    break
                except (FastMossError, OSError, ValueError) as exc:
                    errors.append(f'{type(exc).__name__}: {exc}')
            if entry['status'] != 'success':
                entry.update(errors=errors, attempts=len(errors))
        manifest['categories'][item['path']] = entry
        if entry['status'] == 'success':
            merged.extend(read_csv(path))
            log(f'[success] {item["path"]}: {entry["rows"]} rows')
        else:
            failed.append({'path': item['path'], **entry})
            log(f'[failed] {item["path"]}: {entry.get("errors")}')
        write_json(manifest_path, manifest)
        write_json(directory / '_failed.json', failed)
    manifest.update(completed_at=utc_now(), succeeded=len(items) - len(failed), failed=len(failed))
    combined = directory.parent / f'{country_code(country)}_pet_{period}_all.csv'
    # Only current-run verified successes are merged; no stale-directory glob.
    write_csv(combined, merged)
    manifest['combined_file'] = str(combined)
    write_json(manifest_path, manifest)
    write_json(directory / '_failed.json', failed)
    return manifest


def country_code(country):
    if country in ('新加坡', 'Singapore', 'SG'):
        return 'sg'
    from sales_io import sanitize_filename
    return sanitize_filename(country).lower()


def run_single(args):
    profile = load_profile(args.dom_profile)
    spec = request_spec(country=args.country, shop_type=args.shop_type, category_path=args.category_path,
                        period=args.period, pages=args.pages, profile=profile)
    receipt_path = Path(str(args.out) + '.receipt.json')
    if args.resume and receipt_path.is_file():
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        if reusable({**receipt, 'status': 'success'}, spec, Path(args.out)):
            log(f'[resume] 已核验：{args.out}')
            return 0
    browser = SalesBrowser(profile, nav_sleep=args.nav_sleep, filter_sleep=args.filter_sleep,
                           page_sleep=args.page_sleep)
    try:
        for attempt in range(args.retries + 1):
            try:
                receipt = scrape_sales(browser, country=args.country, shop_type=args.shop_type,
                                       category_path=args.category_path, period=args.period,
                                       pages=args.pages, out=args.out)
                log(f'[done] {receipt["rows"]} rows -> {args.out}')
                return 0
            except FastMossError:
                if attempt == args.retries:
                    raise
    finally:
        browser.close()


def run_pet(args):
    profile = load_profile(args.dom_profile)
    browser = SalesBrowser(profile, nav_sleep=args.nav_sleep, filter_sleep=args.filter_sleep,
                           page_sleep=args.page_sleep)
    try:
        cache = Path(args.category_cache)
        if args.refresh_categories or args.discover_only or not cache.is_file():
            items = discover_categories(browser, country=args.country, shop_type=args.shop_type,
                                        root=args.category_root, cache=cache)
        else:
            items = read_cache(cache, args.category_root)
        log(f'[categories] {len(items)} 三级类目 -> {cache}')
        if args.discover_only:
            return 0
        if args.limit_categories:
            items = items[:args.limit_categories]
        manifest = collect_batch(browser, items, country=args.country, shop_type=args.shop_type,
                                 period=args.period, pages=args.pages, out_dir=args.out_dir,
                                 retries=args.retries, resume=args.resume)
        return 1 if manifest['failed'] else 0
    finally:
        browser.close()
