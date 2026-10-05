# Windows PowerShell 执行流程

**当前分支是已测试的离线分析和采集框架，不是已通过 FastMoss 实测的最终采集器。** 必须先按 [DOM_INVESTIGATION.md](DOM_INVESTIGATION.md) 完成真实 BrowserSkill 调查并得到有效 profile，再执行商品采集步骤。未完成时程序明确拒绝保存 CSV。

## 1. 获取独立 feature 分支

保留原目录，推荐另建目录试用：

```powershell
Set-Location 'C:/Users/dstarking'
git clone --branch feature/sales-cli 'https://github.com/dstarking/fastmoss-rpa-fuhe.git' 'fastmoss-rpa-fuhe'
Set-Location 'C:/Users/dstarking/fastmoss-rpa-fuhe'
py -3.13 --version
py -3.13 -m unittest discover -s tests -v
py -3.13 fastmoss_rpa.py --help
py -3.13 fastmoss_rpa.py sales --help
py -3.13 fastmoss_rpa.py pet-sales --help
py -3.13 fastmoss_rpa.py pet-analyze --help
```

新模块仅使用 Python 标准库。上游 scripts/fastmoss_rpa.py 入口仍可用；新增根目录入口供本说明使用。

如果确实要在现有 git 项目目录获取分支，先检查并保存你自己的修改，再添加新 remote；不要 reset 原项目：

```powershell
Set-Location 'C:/Users/dstarking/fastmoss-rpa-skills'
git status --short
git remote add fuhe 'https://github.com/dstarking/fastmoss-rpa-fuhe.git'
git fetch fuhe
git switch --create feature/sales-cli --track fuhe/feature/sales-cli
```

两个仓库可能具有独立根提交，switch 不合并旧历史。若本地已有同名 branch/remote，选新名字；未提交文件冲突时先保存，不要强制覆盖。

## 2. BrowserSkill daemon：单独窗口

```powershell
bsk daemon start --foreground
```

保持窗口运行，不要求 daemon 自动脱离 Windows Job Object；Python 不创建后台 daemon。Chrome/Edge 扩展已连接，FastMoss 已登录。

第二个 PowerShell：

```powershell
Set-Location 'C:/Users/dstarking/fastmoss-rpa-fuhe'
$env:BSK_AUTO_START = '0'
bsk status
New-Item -ItemType Directory -Force 'F:/fastmoss/data/SG/pet/categories', 'F:/fastmoss/report' | Out-Null
```

bridge 查找顺序 `BSK_BIN` → `shutil.which('bsk')` → 清晰错误。需要覆盖路径时设置 `$env:BSK_BIN` 为本机实际 bsk 可执行文件；无需作者路径。bridge 子进程总是禁用自动启动；browser session 使用动态 ID，仅停止本进程创建的 session。

## 3. 完成 DOM 调查（当前尚未完成）

执行 [DOM_INVESTIGATION.md](DOM_INVESTIGATION.md)，真实核验 profile，并把证据留在本地。

```powershell
$env:FASTMOSS_SALES_PROFILE = 'F:/fastmoss/data/SG/pet/categories/dom-investigation/sales.json'
```

profile 中 evidence 路径相对该文件。**不存在的 profile、空模板、缺失证据、未确认筛选或未刷新数据均禁止采集。**

## 4. 仅发现全部三级类目

```powershell
py -3.13 fastmoss_rpa.py pet-sales --country '新加坡' --shop-type '跨境店' --category-root '宠物用品' --discover-only --category-cache 'F:/fastmoss/data/SG/pet/categories/pet_categories.json'
if ($LASTEXITCODE -ne 0) { throw '类目调查未成功，停止' }
```

缓存是 l1/l2/l3/path/category_id 数组，自动去重。任何二级分支发现失败，不发布不完整的新缓存。

## 5. 单类目 pages=1 smoke test

使用实际发现的第一个路径，不硬编码三级名称：

```powershell
$categories = Get-Content -Raw -Encoding UTF8 'F:/fastmoss/data/SG/pet/categories/pet_categories.json' | ConvertFrom-Json
$leaf = $categories[0].path
py -3.13 fastmoss_rpa.py sales --country '新加坡' --shop-type '跨境店' --category-path $leaf --period week --pages 1 --out 'F:/fastmoss/data/test/smoke.csv'
if ($LASTEXITCODE -ne 0) { throw '单类目采集失败，停止' }
Import-Csv -Encoding UTF8 'F:/fastmoss/data/test/smoke.csv' | Select-Object product_id, product_name, country, country_filter, shop_type_filter, category_path, period
```

人工对照 FastMoss 当前实际选中条件、页码和表格。元数据相同本身不是网站筛选成功的独立证据；回执的 data_filters 必须来自已提交 table。

## 6. 两类目批量测试，先周后月

```powershell
py -3.13 fastmoss_rpa.py pet-sales --country '新加坡' --shop-type '跨境店' --category-root '宠物用品' --period week --pages 1 --limit-categories 2 --out-dir 'F:/fastmoss/data/test/pet/week' --category-cache 'F:/fastmoss/data/SG/pet/categories/pet_categories.json'
py -3.13 fastmoss_rpa.py pet-sales --country '新加坡' --shop-type '跨境店' --category-root '宠物用品' --period month --pages 1 --limit-categories 2 --out-dir 'F:/fastmoss/data/test/pet/month' --category-cache 'F:/fastmoss/data/SG/pet/categories/pet_categories.json'
py -3.13 fastmoss_rpa.py pet-analyze --week-dir 'F:/fastmoss/data/test/pet/week' --month-dir 'F:/fastmoss/data/test/pet/month' --report 'F:/fastmoss/report/smoke_report.md' --summary 'F:/fastmoss/report/smoke_summary.csv' --candidates 'F:/fastmoss/report/smoke_candidates.csv'
```

检查两份 `_manifest.json` 和 `_failed.json`。单个类目失败会继续其他类目，结束返回 1；成功数据仍有独立回执，分析只读取 manifest 中成功且哈希匹配的文件。

## 7. 全量采集周榜，再采集月榜

```powershell
py -3.13 fastmoss_rpa.py pet-sales --country '新加坡' --shop-type '跨境店' --category-root '宠物用品' --period week --pages 5 --out-dir 'F:/fastmoss/data/SG/pet/week' --category-cache 'F:/fastmoss/data/SG/pet/categories/pet_categories.json' --refresh-categories --resume --nav-sleep 6 --filter-sleep 3 --page-sleep 4 --retries 2

py -3.13 fastmoss_rpa.py pet-sales --country '新加坡' --shop-type '跨境店' --category-root '宠物用品' --period month --pages 5 --out-dir 'F:/fastmoss/data/SG/pet/month' --category-cache 'F:/fastmoss/data/SG/pet/categories/pet_categories.json' --resume --nav-sleep 6 --filter-sleep 3 --page-sleep 4 --retries 2
```

每个文件使用 `二级__三级__路径哈希.csv`，避免 Windows 非法字符、大小写、截断后的同名覆盖。每个文件旁边保留 `.receipt.json`，不要只移动 CSV。

输出：

```text
F:/fastmoss/data/SG/pet/categories/pet_categories.json
F:/fastmoss/data/SG/pet/week/*.csv
F:/fastmoss/data/SG/pet/week/_manifest.json
F:/fastmoss/data/SG/pet/week/_failed.json
F:/fastmoss/data/SG/pet/month/*.csv
F:/fastmoss/data/SG/pet/month/_manifest.json
F:/fastmoss/data/SG/pet/month/_failed.json
F:/fastmoss/data/SG/pet/sg_pet_week_all.csv
F:/fastmoss/data/SG/pet/sg_pet_month_all.csv
```

## 8. 分析真实 CSV

```powershell
py -3.13 fastmoss_rpa.py pet-analyze --week-dir 'F:/fastmoss/data/SG/pet/week' --month-dir 'F:/fastmoss/data/SG/pet/month' --report 'F:/fastmoss/report/sg_pet_l3_bestseller_report.md' --summary 'F:/fastmoss/report/sg_pet_l3_bestseller_summary.csv' --candidates 'F:/fastmoss/report/sg_pet_product_candidates.csv'
```

报告包含采集信息、成功/失败数量、相对机会排行榜、爆发/稳定/降温、每类 Top 商品、A/B 商品池、评分规则、数据风险和失败类目。

## 9. 恢复或重新采集

相同命令加 `--resume`：请求（国家、店铺类型、类目、周期、页数、profile 哈希）、CSV 哈希、receipt 和行元数据都匹配才跳过。失败/被修改文件重新跑；改变页数或筛选也重新跑。想刷新所有成功类目，去掉 `--resume`。断点恢复适合同一次采集；跨天重新采样应去掉 resume 或使用新输出目录，避免把旧时间的数据混入新榜单。

`retries=2` 表示初次失败后额外重试两次。只有整类目成功才写 CSV；当前版本不恢复单类目内的页码。
