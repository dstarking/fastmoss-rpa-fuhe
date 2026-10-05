# 验证记录

验证日期：2026-10-05。开发环境：Linux，Python 3.12.14。不是用户的 Windows Python 3.13 环境。

## 已执行

- `python -m unittest discover -s tests -v`：31 个测试通过。
- 根入口 `--help`、`sales --help`、`pet-sales --help`、`pet-analyze --help`：全部退出码 0；完整输出见 CLI_HELP.md。
- 原有 scrape/filter/analyze/market 的 `--help`：全部退出码 0。原有参数与成功结果 schema 保留；底层失败改抛异常，由最外层决定退出码。
- `python -m compileall -q scripts fastmoss_rpa.py`：通过。
- `git diff --check`：通过。
- 缺少调查 profile 时运行 sales：退出码 1，输出 FilterVerificationError，确认没有保存 CSV。
- 人工构造最小 HTML fixture：表头调序、未知列、商品名/价格/上架时间、product_id、店铺信息、缺失列均通过。没有提交完整 FastMoss 源码。
- 模拟浏览器测试：AND 六步筛选；失败不写文件；重复分页拒收；额外重试 2 次；失败类目不中止；manifest；CSV BOM；回执；resume；文件被改后重新采集。
- **合成数据**集成测试：两个虚构类目，各 6 商品，周/月各 12 行，生成汇总 CSV、候选 CSV、Markdown 报告。临时测试文件不作为真实选品数据交付。
- 单元测试：数值格式、Windows 文件名、同名防碰撞、week/month ID 优先和唯一 fallback、速度比、missing 不当 0、hot_score、opportunity_score、percentile ties、不同市场拒绝分析。
- bridge 模拟测试：BSK_BIN/PATH 顺序、强制 BSK_AUTO_START=0、动态 session ID、仅停止自身 session、daemon 不存在的 foreground 提示、原 evaluate 返回形状。

## 未完成 / 阻塞

| 用户要求 | 结果 |
|---|---|
| 用户电脑 `py -3.13 ...` 和浏览器实际测试 | 未执行；云端无法访问用户 Windows。GitHub Windows Python 3.13 离线测试另见 Actions |
| `bsk status` | 实际执行得到 `bsk: command not found` |
| 实际打开 FastMoss 销量榜 | 未执行，无用户浏览器连接 |
| 实际确认销量榜 URL / 周月标签 | 未确认 |
| 实际发现 FastMoss DOM 和过滤器层级 | 未确认 |
| 实际读取所有宠物三级类目 | 未执行；数量未知，不是 0 个 |
| 一个真实三级类目 pages=1 | 未执行；实际商品数未知 |
| 两个真实三级类目批处理 | 未执行 |
| 对真实测试 CSV 跑 pet-analyze | 未执行；只有合成测试数据通过 |

GitHub Actions 已实际执行 Python 3.13 离线 tests 和 CLI 帮助。首次 Ubuntu 成功，Windows 底层中文日志在 cp1252 环境失败；已修复并新增编码回归测试。修复后的状态与运行链接以仓库 Actions 页面为准。CI 不连接用户 BrowserSkill，不代表已完成真实 DOM 验证。

## 行为边界

没有生产销量榜 selector、URL 或周期标签的猜测实现。真实 DOM adapter 仍需在本地 BrowserSkill 环境调查并完成 profile，必要时修改真实组件交互适配。框架刻意拒绝使用空模板，因此此分支**尚不能直接全量抓取 FastMoss**。

已选 UI 与已提交数据条件分别核验；如果页面没有可调查的 committed data_filters/revision 来源，需要进一步调查或修改 adapter，不能把期望参数复制为已加载数据条件。

普通 CSV 无回执禁止分析；批处理目录仅分析当前 manifest 的成功文件，旧失败类目的残留 CSV 不参与。数据文件 `.receipt.json` 必须一起保留。

评分不做完整市场销量外推、不将低 Top10 样本集中度直接称作低竞争，不保证利润或爆款。所有评分、权重、缺失处理和数据风险写入生成的报告。
