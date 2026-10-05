# CLI 完整帮助

## fastmoss_rpa.py --help

```text
FastMoss 统一技能入口

子命令:
  scrape    抓取单个榜单（无筛选）
  filter    带国家/品类/时间筛选抓取
  analyze   生成多维度分析 MD 报告
  sales     严格核验国家/跨境店/三级类目/周期的商品销量榜
  pet-sales 动态读取全部宠物三级类目并批量采集
  pet-analyze 周/月样本交叉分析，生成相对机会报告
  market    调用 FastMoss 品类大盘 API（distribution/base/sales-chart/filter-info）

示例:
  python fastmoss_rpa.py scrape --section products --pages 5 --out out/products.csv
  python fastmoss_rpa.py scrape --section creators --ranking fans --pages 5 --out out/fans.csv
  python fastmoss_rpa.py filter --section products --category 美妆个护,女装与女士内衣 --pages 3 --out out/by_category.csv
  python fastmoss_rpa.py filter --section creators --ranking fans --country 美国,印度尼西亚 --pages 3 --out out/fans_by_country.csv
  python fastmoss_rpa.py analyze creators --fans out/fans.csv --out-md out/creators_report.md
  python fastmoss_rpa.py market distribution --region US,ID,TH --time month --out out/categories.csv
```

## fastmoss_rpa.py sales --help

```text
usage: fastmoss_rpa.py sales [-h] [--country COUNTRY] [--shop-type SHOP_TYPE]
                             [--period {week,month}] [--pages PAGES]
                             [--dom-profile DOM_PROFILE]
                             [--nav-sleep NAV_SLEEP]
                             [--filter-sleep FILTER_SLEEP]
                             [--page-sleep PAGE_SLEEP] [--retries RETRIES]
                             [--resume] --category-path CATEGORY_PATH --out
                             OUT

商品销量榜：国家 AND 店铺类型 AND 三级类目 AND 周期，核验失败不保存。

options:
  -h, --help            show this help message and exit
  --country COUNTRY     实际页面国家标签 (新加坡)
  --shop-type SHOP_TYPE
                        实际页面店铺类型标签 (跨境店)
  --period {week,month}
                        周榜或月榜 (week)
  --pages PAGES         每个三级类目最多页数 (5)
  --dom-profile DOM_PROFILE
                        真实 BrowserSkill 调查的本地 DOM 配置；默认 FASTMOSS_SALES_PROFILE
                        或 local-profiles/sales.json
  --nav-sleep NAV_SLEEP
                        导航最短等待秒数 (6)，之后仍核验 SPA 状态
  --filter-sleep FILTER_SLEEP
                        筛选最短等待秒数 (3)，之后仍核验 SPA 状态
  --page-sleep PAGE_SLEEP
                        分页最短等待秒数 (4)，之后仍核验 SPA 状态
  --retries RETRIES     失败后的额外重试次数 (2)，共最多 3 次
  --resume              仅跳过请求/文件哈希/回执/元数据都匹配的成功文件
  --category-path CATEGORY_PATH
                        一级>二级>三级，必须使用实际发现的标签
  --out OUT             UTF-8-BOM CSV 输出路径
```

## fastmoss_rpa.py pet-sales --help

```text
usage: fastmoss_rpa.py pet-sales [-h] [--country COUNTRY]
                                 [--shop-type SHOP_TYPE]
                                 [--period {week,month}] [--pages PAGES]
                                 [--dom-profile DOM_PROFILE]
                                 [--nav-sleep NAV_SLEEP]
                                 [--filter-sleep FILTER_SLEEP]
                                 [--page-sleep PAGE_SLEEP] [--retries RETRIES]
                                 [--resume] [--category-root CATEGORY_ROOT]
                                 [--out-dir OUT_DIR]
                                 [--category-cache CATEGORY_CACHE]
                                 [--refresh-categories] [--discover-only]
                                 [--limit-categories LIMIT_CATEGORIES]

动态发现宠物三级类目，逐类采集、重试、恢复、manifest 和成功样本合并。

options:
  -h, --help            show this help message and exit
  --country COUNTRY     实际页面国家标签 (新加坡)
  --shop-type SHOP_TYPE
                        实际页面店铺类型标签 (跨境店)
  --period {week,month}
                        周榜或月榜 (week)
  --pages PAGES         每个三级类目最多页数 (5)
  --dom-profile DOM_PROFILE
                        真实 BrowserSkill 调查的本地 DOM 配置；默认 FASTMOSS_SALES_PROFILE
                        或 local-profiles/sales.json
  --nav-sleep NAV_SLEEP
                        导航最短等待秒数 (6)，之后仍核验 SPA 状态
  --filter-sleep FILTER_SLEEP
                        筛选最短等待秒数 (3)，之后仍核验 SPA 状态
  --page-sleep PAGE_SLEEP
                        分页最短等待秒数 (4)，之后仍核验 SPA 状态
  --retries RETRIES     失败后的额外重试次数 (2)，共最多 3 次
  --resume              仅跳过请求/文件哈希/回执/元数据都匹配的成功文件
  --category-root CATEGORY_ROOT
                        一级类目 (宠物用品)
  --out-dir OUT_DIR     单类目 CSV/manifest 目录；非 discover-only 必填
  --category-cache CATEGORY_CACHE
                        三级类目 JSON 缓存路径
  --refresh-categories  重新读取全部三级类目，不复用缓存
  --discover-only       只发现类目，不采集商品
  --limit-categories LIMIT_CATEGORIES
                        仅采集排序后的前 N 个类目，供 smoke test 使用
```

## fastmoss_rpa.py pet-analyze --help

```text
usage: fastmoss_rpa.py pet-analyze [-h] --week-dir WEEK_DIR --month-dir
                                   MONTH_DIR --report REPORT --summary SUMMARY
                                   --candidates CANDIDATES

使用已核验周/月 CSV，离线生成三级类目机会分、商品热度及 A/B/C 商品池。

options:
  -h, --help            show this help message and exit
  --week-dir WEEK_DIR   周榜单类目 CSV 目录
  --month-dir MONTH_DIR
                        月榜单类目 CSV 目录
  --report REPORT       Markdown 报告输出路径
  --summary SUMMARY     三级类目汇总 CSV 输出路径
  --candidates CANDIDATES
                        商品候选池 CSV 输出路径
```
