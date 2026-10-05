"""New CLI parsers, isolated from the legacy argument contract."""
import argparse
from sales import run_single, run_pet
from pet_analysis import run_analysis


def nonnegative(value):
    number = float(value)
    if number < 0 or number != number or number == float('inf'):
        raise argparse.ArgumentTypeError('必须是有限的非负数字')
    return number


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('必须 >= 1')
    return number


def retries_int(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError('必须 >= 0')
    return number


def add_browser_options(parser):
    parser.add_argument('--dom-profile', help='真实 BrowserSkill 调查的本地 DOM 配置；默认 FASTMOSS_SALES_PROFILE 或 local-profiles/sales.json')
    parser.add_argument('--nav-sleep', type=nonnegative, default=6, help='导航最短等待秒数 (6)，之后仍核验 SPA 状态')
    parser.add_argument('--filter-sleep', type=nonnegative, default=3, help='筛选最短等待秒数 (3)，之后仍核验 SPA 状态')
    parser.add_argument('--page-sleep', type=nonnegative, default=4, help='分页最短等待秒数 (4)，之后仍核验 SPA 状态')
    parser.add_argument('--retries', type=retries_int, default=2, help='失败后的额外重试次数 (2)，共最多 3 次')
    parser.add_argument('--resume', action='store_true', help='仅跳过请求/文件哈希/回执/元数据都匹配的成功文件')


def parser_for(command):
    parser = argparse.ArgumentParser(prog='fastmoss_rpa.py ' + command)
    if command in ('sales', 'pet-sales'):
        parser.add_argument('--country', default='新加坡', help='实际页面国家标签 (新加坡)')
        parser.add_argument('--shop-type', default='跨境店', help='实际页面店铺类型标签 (跨境店)')
        parser.add_argument('--period', choices=('week', 'month'), default='week', help='周榜或月榜 (week)')
        parser.add_argument('--pages', type=positive_int, default=5, help='每个三级类目最多页数 (5)')
        add_browser_options(parser)
    if command == 'sales':
        parser.description = '商品销量榜：国家 AND 店铺类型 AND 三级类目 AND 周期，核验失败不保存。'
        parser.add_argument('--category-path', required=True, help='一级>二级>三级，必须使用实际发现的标签')
        parser.add_argument('--out', required=True, help='UTF-8-BOM CSV 输出路径')
    elif command == 'pet-sales':
        parser.description = '动态发现宠物三级类目，逐类采集、重试、恢复、manifest 和成功样本合并。'
        parser.add_argument('--category-root', default='宠物用品', help='一级类目 (宠物用品)')
        parser.add_argument('--out-dir', help='单类目 CSV/manifest 目录；非 discover-only 必填')
        parser.add_argument('--category-cache', default='F:/fastmoss/data/SG/pet/categories/pet_categories.json', help='三级类目 JSON 缓存路径')
        parser.add_argument('--refresh-categories', action='store_true', help='重新读取全部三级类目，不复用缓存')
        parser.add_argument('--discover-only', action='store_true', help='只发现类目，不采集商品')
        parser.add_argument('--limit-categories', type=positive_int, help='仅采集排序后的前 N 个类目，供 smoke test 使用')
    elif command == 'pet-analyze':
        parser.description = '使用已核验周/月 CSV，离线生成三级类目机会分、商品热度及 A/B/C 商品池。'
        parser.add_argument('--week-dir', required=True, help='周榜单类目 CSV 目录')
        parser.add_argument('--month-dir', required=True, help='月榜单类目 CSV 目录')
        parser.add_argument('--report', required=True, help='Markdown 报告输出路径')
        parser.add_argument('--summary', required=True, help='三级类目汇总 CSV 输出路径')
        parser.add_argument('--candidates', required=True, help='商品候选池 CSV 输出路径')
    return parser


def main(command, argv):
    parser = parser_for(command)
    args = parser.parse_args(argv)
    if command == 'pet-sales' and not args.discover_only and not args.out_dir:
        parser.error('非 --discover-only 模式必须提供 --out-dir')
    return {'sales': run_single, 'pet-sales': run_pet, 'pet-analyze': run_analysis}[command](args)
