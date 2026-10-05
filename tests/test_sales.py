"""Synthetic fixtures only. These tests do NOT certify live FastMoss DOM."""
import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from exceptions import (BrowserNotConnectedError, BrowserSkillError, CategoryDiscoveryError,
                        FilterVerificationError, NoDataError, ParseError)
import bridge_browserskill as bridge
from category_tree import validate_categories, discover_categories
from sales import collect_batch, scrape_sales, reusable, verify_rows
from sales_browser import load_profile, SalesBrowser
from sales_io import (category_filename, file_hash, identity, sanitize_filename, write_csv, write_json, log)
from sales_parser import build_schema, parse_row, parse_table, product_id_from_url
from pet_analysis import (velocity_ratio, join_periods, percentile, score_hot, score_opportunities,
                          analyze_samples, load_directory, run_analysis)
from value_parser import parse_value

ALIASES = {'排名':'rank', '商品':'product_name', '国家':'country', '店铺':'shop',
           '类目':'category', '周销量':'sales_period', '月销量':'sales_period',
           '销量环比':'sales_growth', '销售额':'gmv_period'}
PATH = '宠物用品>猫用品>测试类目'
PROFILE = {'_sha256':'synthetic-profile', 'period_labels':{'week':'fixture-week', 'month':'fixture-month'},
           'header_aliases':ALIASES, 'product_labels':{'price':['售价'], 'listed_at':['上架']}}
ITEM = {'l1':'宠物用品', 'l2':'猫用品', 'l3':'测试类目', 'path':PATH, 'category_id':None}


def row(pid='123', *, period='week', path=PATH, sales='700', rank='1', name='cat toy', shop='store'):
    l1, l2, l3 = path.split('>')
    return dict(product_id=pid, product_name=name, shop=shop, category_path=path,
                country='新加坡', category=l3, country_filter='新加坡', shop_type_filter='跨境店',
                l1_category=l1, l2_category=l2, l3_category=l3, period=period, page=1,
                sales_period=sales, rank=rank, sales_growth='20%', gmv_period='SGD 1.2K',
                scraped_at='2026-10-05T10:00:00+00:00')


class FakeBrowser:
    """Explicit test double, never a live browser or an actual category tree."""
    profile = PROFILE
    def __init__(self, pages=None, failure=None):
        self.calls = []
        self.pages = pages or [[123]]
        self.failure = failure
    def navigate(self): self.calls.append('navigate')
    def select(self, dim, label, expected):
        self.calls.append((dim, label, dict(expected)))
        if self.failure == dim:
            raise FilterVerificationError('synthetic failed filter')
    def wait_for(self, expected): return {'revision':'test', **expected}
    def extract(self, expected, page):
        headers = ['排名', '商品', '国家', '店铺', '类目', '周销量', '销量环比', '销售额']
        rows = [[str(index+1), {'text':'toy', 'links':[f'https://www.fastmoss.com/product/{pid}']},
                 '新加坡', 'store', '测试类目', '700', '20%', 'SGD 1.2K']
                for index, pid in enumerate(self.pages[page-1])]
        return {'headers':headers, 'rows':rows}, {'revision':str(page), 'data_filters':dict(expected)}
    def next_page(self, expected, page): return page < len(self.pages)


class NumericTests(unittest.TestCase):
    def test_formats(self):
        examples = {'1,234':1234, '1.2K':1200, '3.4M':3400000, '1.2万':12000,
                    '3.4亿':340000000, 'SGD 12.5K':12500, '$1.2万':12000,
                    '12.5%':12.5, '-8.3%':-8.3, '1,234.5K':1234500, '0':0}
        for text, value in examples.items():
            with self.subTest(text=text): self.assertEqual(parse_value(text), value)
        self.assertEqual(parse_value('12.5%', percent_as_fraction=True), .125)
    def test_missing_and_ambiguous(self):
        for text in (None, '', '-', 'N/A', '1,2', '1..2K', '1-2', '12K%', float('inf'), True, 'SGD nope'):
            with self.subTest(text=text): self.assertIsNone(parse_value(text))


class ParserTests(unittest.TestCase):
    def test_minimal_html_fixture(self):
        from html_fixture import read_fixture
        html = (ROOT/'tests/fixtures/sales_table.html').read_text(encoding='utf-8')
        records = parse_table(read_fixture(html), ALIASES, PROFILE['product_labels'])
        self.assertEqual(records[0]['product_name'], 'Cat Toy')
        self.assertEqual(records[0]['product_id'], '1234567890123456789')
        self.assertEqual(records[0]['sales_period'], '1.2万')
        self.assertEqual(records[0]['shop'], 'Pet Store')
        self.assertEqual(records[0]['total_gmv'], '')

    def test_header_reorder_unknown_and_missing(self):
        headers = ['未知', '周销量', '商品', '国家', '排名']
        parsed = parse_row(headers, ['ignored', '1.2万', {'text':'Toy\n售价：SGD 9.9\n上架：2026-01-01',
                                    'links':['https://www.fastmoss.com/e-commerce/detail/123']}, '新加坡', '2'],
                           ALIASES, PROFILE['product_labels'])
        self.assertEqual(parsed['sales_period'], '1.2万')
        self.assertEqual(parsed['product_name'], 'Toy')
        self.assertEqual(parsed['product_id'], '123')
        self.assertEqual(parsed['price'], 'SGD 9.9')
        self.assertEqual(parsed['listed_at'], '2026-01-01')
        self.assertEqual(parsed['total_sales'], '')
    def test_id_extraction(self):
        self.assertEqual(product_id_from_url('https://host/product/123?foo=1'), '123')
        self.assertEqual(product_id_from_url('https://host/e-commerce/detail/1729123333333333333'), '1729123333333333333')
        self.assertEqual(product_id_from_url('https://host/page?product_id=009'), '009')
        self.assertEqual(product_id_from_url('https://host/shop/123'), '')
    def test_ambiguous_cells_fail(self):
        with self.assertRaises(ParseError): parse_row(['product_name','sales_period'], ['Toy'])
        with self.assertRaises(ParseError): build_schema(['商品','商品','周销量'], ALIASES)
        with self.assertRaises(ParseError): build_schema(['商品','未知'], ALIASES)
    def test_name_and_shop(self):
        parsed = parse_row(['product_name','shop','sales_period'],
                           [{'text':'badge\nToy', 'name':'Toy'}, {'text':'store\n店铺销量:99'}, '1'])
        self.assertEqual(parsed['product_name'], 'Toy')
        self.assertEqual(parsed['shop'], 'store')


class FilenameTests(unittest.TestCase):
    def test_windows_non_utf8_log_never_aborts(self):
        buffer = io.BytesIO()
        stream = io.TextIOWrapper(buffer, encoding='cp1252')
        log('宠物用品', stream=stream)
        stream.flush()
        self.assertIn(b'\\u5ba0', buffer.getvalue())

    def test_windows_invalid_reserved_and_collisions(self):
        self.assertEqual(sanitize_filename('a<>:"/\\|?*b. '), 'a_________b')
        self.assertEqual(sanitize_filename('CON.txt'), '_CON.txt')
        self.assertEqual(sanitize_filename('..'), '_')
        a = {**ITEM, 'l3':'a/b', 'path':'宠物用品>猫用品>a/b'}
        b = {**ITEM, 'l3':'a?b', 'path':'宠物用品>猫用品>a?b'}
        self.assertNotEqual(category_filename(a).casefold(), category_filename(b).casefold())


class AnalyticsTests(unittest.TestCase):
    def test_velocity_zero_and_missing(self):
        self.assertAlmostEqual(velocity_ratio(700, 1500), 2)
        self.assertIsNone(velocity_ratio(700, 0))
        self.assertIsNone(velocity_ratio(None, 1500))
        self.assertEqual(velocity_ratio(0, 100), 0)
    def test_join_id_and_fallback(self):
        products = join_periods([row('123')], [row('123', period='month', sales='1500', rank='3', name='new title')])
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]['join_method'], 'product_id')
        self.assertEqual(products[0]['rank_momentum'], 2)
        self.assertEqual(products[0]['velocity_ratio'], 2)
        products = join_periods([row('')], [row('123', period='month', sales='1500', name='  CAT   toy ')])
        self.assertEqual(products[0]['join_method'], 'name_shop')
        self.assertEqual(products[0]['product_id'], '123')
    def test_different_ids_and_ambiguous_fallback_not_joined(self):
        self.assertEqual(len(join_periods([row('123')], [row('456', period='month')])), 2)
        products = join_periods([row('')], [row('123', period='month'), row('456', period='month')])
        self.assertEqual(len(products), 3)
    def test_percentile_ties(self):
        self.assertEqual(percentile([10,10,None]), [.5,.5,None])
        self.assertEqual(percentile([1,2,3]), [0,.5,1])
    def test_hot_score_weights_idempotent(self):
        items = [dict(week_sales=i, velocity_ratio=i, sales_growth=i, week_gmv=i,
                      rank_momentum=i, persistent=1) for i in range(1,6)]
        score_hot(items)
        self.assertEqual(items[-1]['hot_score'], 100)
        self.assertEqual(items[-1]['grade'], 'A')
        self.assertEqual(items[0]['hot_score'], 5)
        score_hot(items)
        self.assertEqual(items[-1]['hot_score'], 100)
        small = [dict(week_sales=i, velocity_ratio=i, sales_growth=i, week_gmv=i,
                      rank_momentum=i, persistent=1) for i in (1,2)]
        self.assertEqual(score_hot(small)[-1]['grade'], 'B')
    def test_opportunity(self):
        items = [dict(week_sales=i, velocity_ratio=i, high_growth_count=i,
                      inverse_top10_concentration=i/10) for i in range(1,6)]
        self.assertEqual(score_opportunities(items)[-1]['opportunity_score'], 100)
        self.assertEqual(items[0]['opportunity_score'], 0)
    def test_category_relative_and_matched_cohort(self):
        week = [row(str(i), sales=str(i*100)) for i in range(1,7)]
        month = [row(str(i), period='month', sales=str(i*200)) for i in range(1,7)]
        # A week-only entry must not inflate matched-cohort velocity.
        week.append(row('999', sales='1000000'))
        summary, products = analyze_samples(week, month)
        self.assertAlmostEqual(summary[0]['velocity_ratio'], 30/14)
        self.assertEqual(summary[0]['matched_products'], 6)
        self.assertTrue(all(0 <= p['hot_score'] <= 100 for p in products))
    def test_missing_category_period_is_not_zero(self):
        other = '宠物用品>狗用品>测试类目二'
        categories, _ = analyze_samples([row()], [row(period='month'),row('456',period='month',path=other)])
        category = next(c for c in categories if c['category_path']==other)
        self.assertIsNone(category['week_sales'])
        self.assertIsNone(category['velocity_ratio'])

    def test_cross_market_rejected(self):
        other = row(period='month')
        other['country_filter'] = '美国'
        with self.assertRaises(FilterVerificationError): analyze_samples([row()], [other])


class CollectorTests(unittest.TestCase):
    def test_and_filters_bom_and_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'leaf.csv'
            browser = FakeBrowser()
            receipt = scrape_sales(browser, country='新加坡', shop_type='跨境店', category_path=PATH,
                                    period='week', pages=1, out=out)
            self.assertEqual([call[0] for call in browser.calls if isinstance(call,tuple)],
                             ['country','shop_type','l1','l2','l3','period'])
            self.assertEqual(receipt['rows'],1)
            self.assertTrue(out.read_bytes().startswith(b'\xef\xbb\xbf'))
            self.assertTrue(Path(str(out)+'.receipt.json').is_file())
    def test_failed_filter_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'leaf.csv'
            with self.assertRaises(FilterVerificationError):
                scrape_sales(FakeBrowser(failure='l3'), country='新加坡', shop_type='跨境店', category_path=PATH,
                             period='week', pages=1, out=out)
            self.assertFalse(out.exists())
    def test_repeated_pagination_never_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)/'leaf.csv'
            with self.assertRaises(FilterVerificationError):
                scrape_sales(FakeBrowser(pages=[[123],[123]]), country='新加坡', shop_type='跨境店',
                             category_path=PATH, period='week', pages=2, out=out)
            self.assertFalse(out.exists())
    def test_batch_retries_failure_and_resume_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            items = [ITEM, {**ITEM, 'l3':'bad', 'path':'宠物用品>猫用品>bad'}]
            calls = []
            def collector(browser, **kwargs):
                calls.append(kwargs['category_path'])
                if kwargs['category_path'].endswith('>bad'):
                    raise FilterVerificationError('synthetic bad leaf')
                return scrape_sales(browser, **kwargs)
            options = dict(country='新加坡', shop_type='跨境店', period='week', pages=1,
                           out_dir=Path(tmp)/'week', retries=2, collect=collector)
            result = collect_batch(FakeBrowser(), items, **options)
            self.assertEqual(result['succeeded'],1)
            self.assertEqual(result['failed'],1)
            self.assertEqual(calls.count(items[1]['path']),3)
            self.assertTrue((Path(tmp)/'sg_pet_week_all.csv').is_file())
            calls.clear()
            collect_batch(FakeBrowser(), items[:1], **options, resume=True)
            self.assertEqual(calls,[])
            path = Path(tmp)/'week'/category_filename(ITEM)
            path.write_text('tampered',encoding='utf-8')
            collect_batch(FakeBrowser(), items[:1], **options, resume=True)
            self.assertEqual(calls,[PATH])
    def test_analyzer_integration_two_categories(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            second = {**ITEM, 'l2':'狗用品', 'l3':'测试类目二', 'path':'宠物用品>狗用品>测试类目二'}
            def collector(browser, **kwargs):
                # Explicitly synthetic CSV generation for offline integration only.
                records = [row(str(i), period=kwargs['period'], path=kwargs['category_path'],
                               sales=str(i*(100 if kwargs['period']=='week' else 200)), rank=str(7-i)) for i in range(1,7)]
                write_csv(kwargs['out'], records)
                spec = dict(country=kwargs['country'], shop_type=kwargs['shop_type'], category_path=kwargs['category_path'],
                            period=kwargs['period'], pages=kwargs['pages'], profile_sha256=PROFILE['_sha256'])
                receipt = dict(request=spec,sha256=file_hash(kwargs['out']), rows=len(records))
                write_json(str(kwargs['out'])+'.receipt.json',receipt)
                return receipt
            for period in ('week','month'):
                collect_batch(FakeBrowser(), [ITEM,second], country='新加坡',shop_type='跨境店',
                              period=period,pages=1,out_dir=root/period,collect=collector)
            args = SimpleNamespace(week_dir=root/'week',month_dir=root/'month', report=root/'report.md',
                                   summary=root/'summary.csv', candidates=root/'candidates.csv')
            self.assertEqual(run_analysis(args),0)
            report = args.report.read_text(encoding='utf-8')
            for section in ('评分规则','三级类目机会排行榜','A级爆款商品池','B级商品池','失败类目','数据风险说明'):
                self.assertIn(section,report)
            self.assertEqual(len(load_directory(root/'week','week')[0]),12)
    def test_categories_unique_and_fail_closed(self):
        self.assertEqual(len(validate_categories([ITEM,ITEM], '宠物用品')),1)
        with self.assertRaises(CategoryDiscoveryError): validate_categories([ITEM],'美妆')
    def test_unverified_profile_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FilterVerificationError): load_profile(Path(tmp)/'missing.json')
        with self.assertRaises(FilterVerificationError): load_profile(ROOT/'profiles/sales.unverified.example.json')
    def test_state_does_not_trust_selected_ui(self):
        expected = {'country':'新加坡'}
        state = dict(logged_in=True,ready=True,loading=False,revision='test',country='新加坡',data_filters={'country':'美国'})
        self.assertFalse(SalesBrowser.verified(state,expected))
        state['data_filters']['country'] = '新加坡'
        self.assertTrue(SalesBrowser.verified(state,expected))


class BridgeTests(unittest.TestCase):
    def tearDown(self): bridge._SESSIONS.clear()
    def test_path_precedence_and_autostart_disabled(self):
        with patch.dict(os.environ,{'BSK_BIN':'custom-bsk'},clear=True), patch.object(bridge.subprocess,'run') as run:
            run.return_value = subprocess.CompletedProcess([],0,'ok','')
            bridge.run_bsk(['status'])
            self.assertEqual(run.call_args.args[0][0],'custom-bsk')
            self.assertEqual(run.call_args.kwargs['env']['BSK_AUTO_START'],'0')
        with patch.dict(os.environ,{},clear=True),patch.object(bridge.shutil,'which',return_value='path-bsk'):
            self.assertEqual(bridge.resolve_bsk(),'path-bsk')
    def test_missing_daemon_actionable_error(self):
        with patch.dict(os.environ,{'BSK_BIN':'bsk'},clear=True),patch.object(bridge.subprocess,'run') as run:
            run.return_value = subprocess.CompletedProcess([],1,'','daemon not running')
            with self.assertRaisesRegex(BrowserNotConnectedError,'bsk daemon start --foreground'):
                bridge.run_bsk(['status'])
    def test_session_ids_dynamic_and_only_owned_stop(self):
        with patch.object(bridge,'run_bsk',side_effect=['{"session_id":"dynamic"}','closed']) as run:
            self.assertEqual(bridge._start('test'),'dynamic')
            bridge.session_stop('test')
            self.assertEqual(run.call_args.args[0],['session','stop','dynamic'])
    def test_legacy_evaluate_shape(self):
        with patch.object(bridge,'call',return_value={'ok':True,'data':{'type':'string','value':'"{\\"x\\":1}"'}}):
            self.assertEqual(bridge.evaluate('code','session'),{'x':1})


class CLITests(unittest.TestCase):
    def test_all_help_without_browser(self):
        for command in ([],['sales'],['pet-sales'],['pet-analyze'],['scrape'],['filter'],['analyze'],['market']):
            with self.subTest(command=command):
                result = subprocess.run([sys.executable,str(ROOT/'fastmoss_rpa.py'),*command,'--help'],capture_output=True,text=True,encoding='utf-8')
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertTrue(result.stdout)

if __name__ == '__main__': unittest.main()
