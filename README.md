# FastMoss 数据抓取技能（统一版）

> **一个命令，搞定 7 大榜单的 TikTok 小店数据抓取、筛选、分析与品类大盘。**

---

## 这是什么？

[FastMoss](https://www.fastmoss.com) 是一个看 **TikTok 电商（TikTok Shop）** 数据的网站。
这个技能让你用一行命令，把网站上 7 大榜单的数据**自动抓下来存成表格（CSV）**，还能顺便**生成一份带洞察的分析报告（Markdown）**。

以前这是 7 个分开的技能，现在合并成 **1 个**，命令统一、好记、好维护。

> Browser-RPA + 数据分析工具集，覆盖 [fastmoss.com](https://www.fastmoss.com) (TikTok Shop 数据分析平台) 全部 7 个核心模块。基于 [BrowserSkill](https://github.com/Tencent/BrowserSkill) 驱动用户真实浏览器（复用登录态），把 FastMoss 的榜单/趋势/市场数据落成 CSV，并自动生成 Markdown 分析报告。

---

## 项目特点

- **真实浏览器复用登录态** — 通过 BrowserSkill 驱动用户已经登录的 Chrome/Edge，无需扫码、无需 token、无需 captcha 破解。
- **7 个 FastMoss 模块全覆盖** — 商品/达人/店铺/直播/视频&素材/广告引擎/品类大盘，每个模块独立 skill，互不干扰。
- **CSV + Markdown 双输出** — 原始数据进 `data/`，聚合报告生成到 `analysis.md` 或自定义路径，Excel 友好（UTF-8 BOM）。
- **Schema 自动适配** — 6 个 DOM-scraping skill 动态读取 `<thead>`，无论 FastMoss 改字段都不需要改代码。
- **API-first 优先** — `fastmoss-market` 是 API skill，直接调用 FastMoss JSON 接口（通过页面上下文 `fetch()`），无分页、无 SPA 等待、无 selector 维护。
- **多市场对比内置** — 所有 ranking skill 都支持 `--country 美国,印度尼西亚,泰国,马来西亚` 一键多市场抓取并自动切分。



## 它能抓什么？（7 大榜单）

| 榜单 (`--section`) | 能看什么（子榜单） | 举个栗子 |
|---|---|---|
| `products` 商品榜 | 新品 / 销量 / 热推商品 | 美国最近上新的爆品 |
| `creators` 达人榜 | 涨粉 / 带货 / 蓝V / 热门 / 黑马 | 印尼涨粉最快的带货号 |
| `shops` 店铺榜 | 销量 / 热推店铺 | 泰国销量 Top 店铺 |
| `ads` 广告趋势 | 标签 / 关键词 / 品类 | 某品类正在投的广告关键词 |
| `creatives` 素材榜 | 视频 / 音乐 / 标签 | 近期跑量的视频素材 |
| `livestreams` 直播榜 | TT 直播 / 直播爆品 / 直播带货达人 | 直播带货 Top 达人 |
| `market` 品类大盘 | 行业格局 / 市场总览 / 日销趋势 | 美妆行业各国分布 |

---

## 开始之前（只需做一次）

1. 安装好 **BrowserSkill（`bsk`）** 并装好浏览器插件。
2. 用 Chrome / Edge **登录 fastmoss.com**（数据是靠你自己的登录态抓的，所以必须登录）。
3. 命令行执行 `bsk status`，看到下面这行、且数字 ≥ 1 就 OK：
   ```
   browsers connected: 1
   ```

> 如果看不到 `browsers connected`，先打开浏览器、确认已登录 fastmoss.com，再试一次。

---

## 怎么用？四条命令

所有命令都在技能的 `scripts/` 目录里运行（下文用 `python` 指代运行环境）。
把 `<out>` 换成你想存文件的路径即可，父文件夹会自动创建。

### ① 抓取 `scrape` —— 把榜单数据存成 CSV

```bash
# 抓商品榜（前 5 页），商品榜不需要写 --ranking
python fastmoss_rpa.py scrape --section products --pages 5 --out out/products.csv

# 抓达人「涨粉」榜
python fastmoss_rpa.py scrape --section creators --ranking fans --pages 5 --out out/fans.csv

# 其余榜单都要带 --ranking（取值见上表"能看什么"那一列）
python fastmoss_rpa.py scrape --section shops       --ranking sales     --pages 5 --out out/sales.csv
python fastmoss_rpa.py scrape --section ads         --ranking keyword   --pages 5 --out out/keywords.csv
python fastmoss_rpa.py scrape --section creatives   --ranking video     --pages 5 --out out/videos.csv
python fastmoss_rpa.py scrape --section livestreams --ranking tiktok    --pages 5 --out out/tiktok.csv
```

### ② 筛选 `filter` —— 按国家 / 品类 / 时间抓

- **商品榜**可以按 **国家 / 品类 / 店铺类型** 筛（每次选一种）。
- **达人 / 店铺等**可以按 **国家** 筛；达人还能按 **时间**（如 `周榜` / `月榜`）。

```bash
# 商品榜：只要「美妆个护」和「女装与女士内衣」两个品类
python fastmoss_rpa.py filter --section products --category "美妆个护,女装与女士内衣" --pages 3 --out out/by_category.csv

# 商品榜：按国家筛（美国 + 印度尼西亚）
python fastmoss_rpa.py filter --section products --country 美国,印度尼西亚 --pages 3 --out out/by_country.csv

# 达人榜：同时看美国、印尼、泰国、马来西亚
python fastmoss_rpa.py filter --section creators --ranking fans --country 美国,印度尼西亚,泰国,马来西亚 --pages 3 --out out/fans_by_country.csv

# 达人榜：美国近一周带货榜
python fastmoss_rpa.py filter --section creators --ranking commerceTop --country 美国 --time 周榜 --pages 3 --out out/commerce_us_weekly.csv
```

### ③ 分析 `analyze` —— 生成洞察报告（Markdown）

把抓到的 CSV 喂进去，自动产出一份「人话版」分析报告。

```bash
# 商品榜报告（可同时喂入：总榜 + 分国家 + 分品类 + 单店数据）
python fastmoss_rpa.py analyze products \
    --top50 out/top50.csv --by-country out/by_country.csv \
    --by-category out/by_category.csv --shop out/shop_X.csv \
    --out-md report/products_report.md

# 达人榜报告（把各个子榜一起喂进去）
python fastmoss_rpa.py analyze creators --fans out/fans.csv --commerce out/commerce.csv \
    --blue-v out/blue-v.csv --popular out/popular.csv --horse out/horse.csv \
    --out-md report/creators_report.md
```

> 小技巧：如果你是用 ② 的「多国家筛选」抓的数据，直接 `--filtered out/fans_by_country.csv` 就能出一份按国家拆开的分析。

### ④ 品类大盘 `market` —— 行业级数据（走接口，不走翻页）

```bash
# 看多个国家的品类分布（行业格局对比）
python fastmoss_rpa.py market distribution --region US,ID,TH,MY --time month --out out/categories_by_region.csv

# 某个国家的市场总览 + Top 商品
python fastmoss_rpa.py market base --region US --out out/us_market_base.json --top-products-csv out/us_top_products.csv

# 日销趋势（时间序列）
python fastmoss_rpa.py market sales-chart --region US --out out/us_sales_chart.csv

# 然后出一份大盘报告
python fastmoss_rpa.py analyze market --distribution out/categories_by_region.csv --out-md report/market_report.md
```

---

## 国家怎么填？

- **表格榜单**（products / creators / shops / ads / creatives / livestreams）用 **中文标签**：
  ```
  美国 印度尼西亚 英国 越南 泰国 马来西亚 菲律宾 西班牙
  墨西哥 德国 法国 意大利 巴西 日本 新加坡 沙特
  ```
- **品类大盘**（market）用 **英文代码**：
  ```
  US ID GB VN TH MY PH ES MX DE FR IT BR JP SG SA
  ```

多个值用英文逗号 `,` 隔开，例如 `美国,印度尼西亚,泰国`。

---

## 抓出来的文件长啥样？

- 每个榜单生成一个 `.csv` 表格，第一行是表头（列名）。
- 分析报告是 `.md`（Markdown），可用 Typora / VS Code / 记事本打开，也能直接粘进文档。
- CSV 为 UTF-8 编码（带 BOM），**Excel 直接打开中文不乱码**。

商品榜常见列含义（节选）：
`排名 / 商品名 / 价格 / 上架时间 / 国家 / 店铺 / 品类 / 佣金 / 周期销量 / 周期GMV / 总销量 / 总GMV`

---

## 小贴士 & 排错

- **抓到 0 行？** 多半是翻页太快。加上 `--nav-sleep 6 --page-sleep 4` 让脚本多等几秒。
- **提示浏览器没连上？** 先 `bsk status` 确认 `browsers connected ≥ 1`，并确保已登录 fastmoss.com。
- **想多抓几页？** 把 `--pages` 调大（每页约 10~20 条）。
- **Windows 运行环境**：用 Python 3.13 运行（WorkBuddy 自带），一般直接 `python fastmoss_rpa.py ...` 即可。

---

## 和以前 7 个技能的关系

之前是 7 个分开的技能（`fastmoss-products`、`fastmoss-creators` ……）。
现在它们合并进了这 **1 个**。旧的 `.claude/skills/fastmoss-*` 文件夹**暂时保留当备份、没有删除**；
等你用顺手了，随时可以手动删掉旧的。

---

_本技能由 BrowserSkill（`bsk`）驱动你的真实已登录浏览器，复用登录态完成抓取与接口调用。_


## 特别感谢：

https://linux.do 社区佬友 