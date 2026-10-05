"""Offline week/month sample analysis. No database, GUI, API, or browser required."""
import json
import math
from collections import defaultdict
from pathlib import Path
from exceptions import FilterVerificationError, NoDataError, ParseError
from sales import verify_rows, reusable
from sales_io import atomic_write, identity, normalize, read_csv, write_csv, log
from value_parser import parse_value

HOT_WEIGHTS = {'week_sales': .35, 'velocity_ratio': .25, 'sales_growth': .15,
               'week_gmv': .10, 'rank_momentum': .10, 'persistent': .05}
OPPORTUNITY_WEIGHTS = {'week_sales': .30, 'velocity_ratio': .30,
                       'high_growth_count': .20, 'inverse_top10_concentration': .20}


def velocity_ratio(week, month):
    if week is None or month is None or month <= 0 or week < 0:
        return None
    return (week / 7) / (month / 30)


def percentile(values):
    """Midrank percentile; ties receive equal scores; singleton gets .5.

    Missing metrics are left missing and receive no weight contribution.
    """
    valid = sorted(value for value in values if value is not None and math.isfinite(value))
    if not valid:
        return [None] * len(values)
    if len(valid) == 1:
        return [.5 if value is not None else None for value in values]
    scores = {}
    for value in set(valid):
        below = sum(item < value for item in valid)
        equal = sum(item == value for item in valid)
        scores[value] = (below + (equal - 1) / 2) / (len(valid) - 1)
    return [scores.get(value) for value in values]


def score_hot(products):
    for row in products:
        row['hot_score'] = 0
    for key, weight in HOT_WEIGHTS.items():
        values = [row.get(key) for row in products]
        # Persistence is an observed binary signal, not a percentile with all ties.
        scores = values if key == 'persistent' else percentile(values)
        for row, score in zip(products, scores):
            row.setdefault('hot_score', 0)
            row['hot_score'] += 100 * weight * (score if score is not None else 0)
    for row in products:
        row['hot_score'] = round(row['hot_score'], 2)
        row['metric_coverage'] = round(sum(weight for key, weight in HOT_WEIGHTS.items()
                                          if row.get(key) is not None), 3)
        grade = 'A' if row['hot_score'] >= 75 else 'B' if row['hot_score'] >= 50 else 'C'
        # Small/insufficient samples cannot justify a top testing grade.
        if grade == 'A' and (len(products) < 5 or row['metric_coverage'] < .75
                             or not row.get('week_sales') or row.get('velocity_ratio') is None):
            grade = 'B'
        row['grade'] = grade
        row['recommendation'] = {'A': '优先爆款测试', 'B': '可测试/观察', 'C': '暂缓'}[grade]
    return products


def score_opportunities(categories):
    for row in categories:
        row['opportunity_score'] = 0
    for key, weight in OPPORTUNITY_WEIGHTS.items():
        scores = percentile([row.get(key) for row in categories])
        for row, score in zip(categories, scores):
            row['opportunity_score'] += 100 * weight * (score if score is not None else 0)
    for row in categories:
        row['opportunity_score'] = round(row['opportunity_score'], 2)
    return categories


def _deduplicate(rows):
    grouped = {}
    for row in rows:
        key = (row['category_path'], identity(row))
        if not key[1]:
            raise ParseError('无法建立商品身份：需要 product_id 或 product_name + shop。')
        if key in grouped:
            raise ParseError(f'同三级类目包含重复商品：{key}；请勿混合多次采集 CSV。')
        grouped[key] = row
    return grouped


def join_periods(week, month):
    weeks, months = _deduplicate(week), _deduplicate(month)
    fallback_month = defaultdict(list)
    fallback_week = defaultdict(list)
    fallback = lambda r: (r['category_path'], normalize(r.get('product_name')), normalize(r.get('shop')))
    for key, row in months.items():
        fallback_month[fallback(row)].append(key)
    for key, row in weeks.items():
        fallback_week[fallback(row)].append(key)
    paired, used = [], set()
    for key, row in weeks.items():
        partner = key if key in months else None
        method = 'product_id' if partner and key[1].startswith('id:') else 'name_shop' if partner else 'week_only'
        if partner is None:
            candidates = fallback_month.get(fallback(row), [])
            if (fallback(row)[1] and fallback(row)[2] and len(candidates) == 1
                    and len(fallback_week[fallback(row)]) == 1):
                possible = candidates[0]
                other = months[possible]
                # Never merge two different nonempty product IDs just because titles match.
                if not row.get('product_id') or not other.get('product_id'):
                    partner = possible
                    method = 'name_shop'
        if partner in used:
            raise ParseError('week/month 关联不唯一。')
        other = months.get(partner)
        if partner:
            used.add(partner)
        paired.append((row, other, method))
    paired.extend((None, row, 'month_only') for key, row in months.items() if key not in used)
    output = []
    for w, m, method in paired:
        row = w or m
        ws, ms = parse_value((w or {}).get('sales_period')), parse_value((m or {}).get('sales_period'))
        wr, mr = parse_value((w or {}).get('rank')), parse_value((m or {}).get('rank'))
        momentum = mr - wr if wr is not None and mr is not None else None
        output.append({
            'category_path': row['category_path'], 'l1_category': row.get('l1_category'),
            'l2_category': row.get('l2_category'), 'l3_category': row.get('l3_category'),
            'product_id': (w or {}).get('product_id') or (m or {}).get('product_id', ''),
            'product_name': row['product_name'], 'shop': row.get('shop', ''), 'price': row.get('price', ''),
            'week_sales': ws, 'month_sales': ms, 'velocity_ratio': velocity_ratio(ws, ms),
            'week_rank': wr, 'month_rank': mr, 'rank_momentum': momentum,
            'sales_growth': parse_value((w or {}).get('sales_growth')),
            'month_sales_growth': parse_value((m or {}).get('sales_growth')),
            'week_gmv': parse_value((w or {}).get('gmv_period')),
            'month_gmv': parse_value((m or {}).get('gmv_period')),
            'persistent': 1 if w and m else 0, 'join_method': method,
            'week_scraped_at': (w or {}).get('scraped_at', ''),
            'month_scraped_at': (m or {}).get('scraped_at', '')})
    return output


def summarize(products):
    grouped = defaultdict(list)
    for row in products:
        grouped[row['category_path']].append(row)
    categories = []
    for path, rows in grouped.items():
        score_hot(rows)
        week = [row for row in rows if row['week_sales'] is not None]
        month = [row for row in rows if row['month_sales'] is not None]
        matched = [row for row in rows if row['persistent'] and row['week_sales'] is not None and row['month_sales'] is not None]
        total_week = sum(row['week_sales'] for row in week) if week else None
        total_month = sum(row['month_sales'] for row in month) if month else None
        # Compare daily velocity on the matched cohort, not unequal TopN unions.
        velocity = velocity_ratio(sum(row['week_sales'] for row in matched),
                                  sum(row['month_sales'] for row in matched)) if matched else None
        top10 = sum(sorted((row['week_sales'] for row in week), reverse=True)[:10])
        concentration = top10 / total_week if total_week is not None and total_week > 0 else None
        high = sum(row['velocity_ratio'] is not None and row['velocity_ratio'] >= 1.5
                   and row['week_sales'] is not None and row['week_sales'] > 0 for row in rows)
        trend = '数据不足' if velocity is None else '爆发' if velocity >= 1.5 else '降温' if velocity < .8 else '稳定'
        categories.append({'category_path': path, 'l1_category': rows[0]['l1_category'],
                           'l2_category': rows[0]['l2_category'], 'l3_category': rows[0]['l3_category'],
                           'sample_products': len(rows), 'week_products': len(week), 'month_products': len(month),
                           'matched_products': len(matched), 'week_sales': total_week, 'month_sales': total_month,
                           'week_gmv': sum(row['week_gmv'] or 0 for row in week) if any(row['week_gmv'] is not None for row in week) else None,
                           'month_gmv': sum(row['month_gmv'] or 0 for row in month) if any(row['month_gmv'] is not None for row in month) else None,
                           'velocity_ratio': velocity, 'high_growth_count': high if week else None,
                           'top10_sample_concentration': concentration,
                           'inverse_top10_concentration': 1 - concentration if concentration is not None else None,
                           'trend': trend, 'a_products': sum(row['grade'] == 'A' for row in rows)})
    score_opportunities(categories)
    return sorted(categories, key=lambda row: (-row['opportunity_score'], row['category_path']))


def load_directory(directory, period):
    directory = Path(directory)
    manifest_path = directory / '_manifest.json'
    info = {'directory': str(directory), 'period': period, 'failed': [], 'success': 0,
            'warnings': [], 'times': [], 'profile_sha256': None}
    inputs = []
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            raise ParseError(f'manifest 无法读取：{exc}') from exc
        if manifest.get('period') != period:
            raise FilterVerificationError(f'{directory} manifest 周期不一致。')
        info['profile_sha256'] = manifest.get('profile_sha256')
        for category, entry in manifest.get('categories', {}).items():
            if entry.get('status') != 'success':
                info['failed'].append({'path': category, 'errors': entry.get('errors', [])})
                continue
            filename = entry.get('file', '')
            if Path(filename).name != filename:
                raise FilterVerificationError('manifest 文件名必须在当前目录内。')
            path = directory / filename
            if entry.get('request', {}).get('category_path') != category:
                raise FilterVerificationError('manifest 类目键与请求不一致。')
            if not reusable(entry, entry.get('request', {}), path):
                raise FilterVerificationError(f'采集回执或哈希不匹配：{path}')
            inputs.append(path)
    else:
        inputs = sorted(path for path in directory.glob('*.csv') if not path.name.startswith('_'))
        info['warnings'].append('目录无批处理 manifest：失败类目总数未知，只能统计存在的完整采集回执。')
    rows = []
    for path in inputs:
        receipt_path = Path(str(path) + '.receipt.json')
        if not receipt_path.is_file():
            raise FilterVerificationError(f'缺少采集回执，无法确认筛选：{path}')
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        spec = receipt.get('request', {})
        if spec.get('period') != period or not reusable({**receipt, 'status': 'success'}, spec, path):
            raise FilterVerificationError(f'CSV 与采集请求不一致：{path}')
        current = read_csv(path)
        rows.extend(current)
        info['success'] += 1
        info['times'].extend(row.get('scraped_at', '') for row in current)
    return rows, info


def analyze_samples(week, month):
    if not week or not month:
        raise NoDataError('周榜和月榜都必须有至少一个已核验成功类目。')
    filters = {(row.get('country_filter'), row.get('shop_type_filter')) for row in week + month}
    if len(filters) != 1:
        raise FilterVerificationError(f'周/月榜国家或店铺类型不一致：{filters}')
    for rows, period in [(week, 'week'), (month, 'month')]:
        for row in rows:
            verify_rows([row], country=row['country_filter'], shop_type=row['shop_type_filter'],
                        category_path=row['category_path'], period=period)
    products = join_periods(week, month)
    categories = summarize(products)
    products.sort(key=lambda row: (row['grade'], -row['hot_score'], row['category_path'], row['product_name']))
    return categories, products


def display(value):
    if value is None or value == '':
        return '—'
    if isinstance(value, float):
        return f'{value:.2f}'
    return str(value).replace('|', '\\|').replace('\n', ' ')


def md_table(rows, columns):
    result = ['| ' + ' | '.join(columns.values()) + ' |',
              '| ' + ' | '.join('---' for _ in columns) + ' |']
    result.extend('| ' + ' | '.join(display(row.get(key)) for key in columns) + ' |' for row in rows)
    return '\n'.join(result)


def render_report(categories, products, week_info, month_info, week_rows, month_rows):
    country, shop_type = week_rows[0]['country_filter'], week_rows[0]['shop_type_filter']
    lines = ['# 新加坡宠物用品三级类目销量榜样本报告', '', '## 数据采集信息', '',
             f'- 国家：{country}；店铺类型：{shop_type}。',
             f'- 周榜：成功 {week_info["success"]} 类，已记录失败 {len(week_info["failed"])} 类，商品 {len(week_rows)} 条。',
             f'- 月榜：成功 {month_info["success"]} 类，已记录失败 {len(month_info["failed"])} 类，商品 {len(month_rows)} 条。']
    for info in (week_info, month_info):
        times = sorted(time for time in info['times'] if time)
        lines.append(f'- {info["period"]} 采集时间：{times[0] if times else "未知"} 至 {times[-1] if times else "未知"}；目录：{info["directory"]}。')
        lines.extend('- ' + warning for warning in info['warnings'])
    lines += ['', '## 评分规则', '',
              '产品 hot_score 在同三级类目内按 midrank percentile 计算，权重：周销量 35%、速度比 25%、周榜 FastMoss 销量环比 15%、周 GMV 10%、排名动量 10%、周月持续出现 5%。持续出现按 0/1；其余指标同类目内归一化，单个样本得 0.5。', '',
              '缺失指标贡献为 0，不把无法解析的销量当作 0；输出 metric_coverage。A ≥75，B ≥50，C <50。少于 5 个商品、覆盖权重不足 75%、无有效速度比或周销量为 0 的商品不能评为 A。A级意为优先测试，仍需核验资质、利润、重量与供应链。', '',
              'velocity_ratio = (week_sales / 7) / (month_sales / 30)；月销量为 0 或缺失时为空，不制造无限增速。rank_momentum = month_rank - week_rank，正数代表周榜排名更靠前。FastMoss sales_growth 以百分数数值保存，例如 12.5% → 12.5。', '',
              '类目 opportunity_score：周销量规模 30%、匹配商品群速度比 30%、高增长商品数量 20%、Top10 样本集中度反向指标 20%，在本次类目样本之间按 percentile 归一化。高增长：速度比 ≥1.5 且周销量 >0；爆发 ≥1.5，降温 <0.8，其余稳定，缺失则数据不足。', '',
              '**这只是抓取 TopN 样本的相对机会分，不是 FastMoss 官方评分，不是完整市场份额，也不能证明竞争较低。** 集中度只是 Top10 周销量 / 抓取样本周销量；样本不足 10 个时通常为 100%，信息量有限。', '',
              '## 三级类目机会排行榜', '',
              md_table(categories, {'category_path':'三级类目', 'opportunity_score':'相对机会分',
                                    'week_sales':'周样本销量', 'velocity_ratio':'匹配群速度比',
                                    'high_growth_count':'高增长商品数',
                                    'top10_sample_concentration':'Top10 样本集中度', 'trend':'趋势'})]
    for trend, title in [('爆发', '爆发类目'), ('稳定', '稳定类目'), ('降温', '降温类目')]:
        lines += ['', '## ' + title, '']
        subset = [row for row in categories if row['trend'] == trend]
        lines += [md_table(subset, {'category_path':'三级类目', 'velocity_ratio':'速度比',
                                  'matched_products':'匹配商品数'}) if subset else '本次样本暂无。']
    columns = {'product_name':'商品', 'shop':'店铺', 'week_sales':'周销量', 'month_sales':'月销量',
               'velocity_ratio':'速度比', 'sales_growth':'FastMoss 环比', 'hot_score':'热度分', 'grade':'等级'}
    lines += ['', '## 每个三级类目 Top 商品', '']
    for category in categories:
        lines += ['### ' + category['category_path'], '',
                  md_table([row for row in products if row['category_path'] == category['category_path']][:10], columns), '']
    for grade in ('A', 'B'):
        lines += ['## ' + grade + ('级爆款商品池' if grade == 'A' else '级商品池'), '']
        subset = [row for row in products if row['grade'] == grade]
        lines += [md_table(subset, {'category_path':'三级类目', **columns}) if subset else '本次样本暂无。', '']
    lines += ['## 数据风险说明', '',
              '- 榜单截断、分页深度、会员权限及榜单采集时间不同可能影响可比性。周/月区间实际以 FastMoss 页面为准，固定 7/30 是分析近似。',
              '- 类目速度用周月匹配群；未进入另一榜单的商品不能视作销量为 0。商品名称+店铺 fallback 只在唯一且至少一侧无 ID 时使用；不同非空 ID 不合并。',
              '- 本报告不包含完整店铺数量、广告成本、退款、物流与采购成本；不能由低集中度直接断言低竞争或保证爆款。',
              '- 原始 price/GMV 保留货币文本；比较需要同一国家同币种。未知货币格式留空，不自动换汇。',
              '- 宠物父类目可能含食品、药品；本工具不自动判断资质，测试前需筛除不符合你的非食品非药品范围的商品。',
              '- CSV 回执与哈希可检测文件变化；页面选择和数据提交正确性仍取决于经过真实 BrowserSkill 调查的 DOM profile。']
    if week_info.get('profile_sha256') != month_info.get('profile_sha256'):
        lines.append('- 周/月 DOM profile 哈希不同，需要核对页面语义是否变化。')
    missing = {row['category_path'] for row in week_rows} ^ {row['category_path'] for row in month_rows}
    if missing:
        lines.append('- 仅一侧有成功采集的类目：' + '、'.join(sorted(missing)))
    lines += ['', '## 失败类目', '']
    for info in (week_info, month_info):
        lines.append('### ' + info['period'])
        lines.append('')
        lines.extend('- ' + entry['path'] + '：' + '; '.join(entry['errors']) for entry in info['failed'])
        if not info['failed']:
            lines.append('manifest 未记录失败类目。' if not info['warnings'] else '失败数量未知（无 manifest）。')
        lines.append('')
    return '\n'.join(lines)


def run_analysis(args):
    week, wi = load_directory(args.week_dir, 'week')
    month, mi = load_directory(args.month_dir, 'month')
    categories, products = analyze_samples(week, month)
    write_csv(args.summary, categories, list(categories[0]))
    write_csv(args.candidates, products, list(products[0]))
    report = render_report(categories, products, wi, mi, week, month)
    atomic_write(args.report, lambda stream: stream.write(report))
    log(f'[done] {len(categories)} 类目，{len(products)} 商品 -> {args.report}')
    return 0
