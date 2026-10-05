# BrowserSkill 页面调查与当前阻塞

本分支没有经过真实 FastMoss 页面验收。云端开发环境未安装 bsk，也未连接用户 Windows 浏览器；没有确认销量榜 URL、周/月中文标签、过滤器 selector、三级类目树、分页 DOM 或数据加载状态。**不能将本分支视为已能直接抓取真实商品的最终版。**

为遵守“不猜 selector”和“宁可失败也不保存错误筛选数据”，没有内置任何销量榜网站 selector。新命令在缺少本地调查 profile 时抛出 FilterVerificationError，不保存 CSV。上游其他榜单的旧 selector 不作为新销量榜的证据。

## 在已连接的 Windows 环境调查

1. 单独 PowerShell 保持运行 `bsk daemon start --foreground`。
2. 第二个 PowerShell 设置 `$env:BSK_AUTO_START = '0'`，运行 `bsk status`，确认扩展连接。
3. 在 FastMoss 浏览器中**实际进入商品销量榜**，复制地址栏 URL。不要把未经观察的 saleslist 路径当已验证事实。
4. 从项目根运行：

```powershell
$url = Read-Host '粘贴实际商品销量榜 URL'
py -3.13 scripts/inspect_sales.py --url $url --out-dir 'F:/fastmoss/data/SG/pet/categories/dom-investigation'
```

工具通过 BrowserSkill status/navigate/snapshot/evaluate 采集证据，导出 snapshot 和 table 表头清单。它不会自动宣称已登录或生成可用 selector。snapshot refs 只用于调查，不用于生产交互。

5. 本地 Codex 使用 BrowserSkill 再创建自己的调查 session，调查商品筛选容器唯一 CSS scope。用 evaluate 在该 scope 读取 option、checked/selected 状态、层级与 ID；逐步选择新加坡、跨境店、宠物一级类目、每个二级类目和三级类目。
6. 确认 scope 后，重新运行上面的脚本并增加 `--scope '实际唯一 CSS selector'`，只导出这个筛选容器的 HTML。门户外的 cascader 弹层必须通过实际 DOM 的触发器/弹层 ID 确定从属关系，不能扫描全页面文本。若该组件不能用当前 profile contract 描述，修改 adapter 并补测试，不能放宽验证。
7. 实际点击周/月选项，记录**实际显示文字**，记录表头、商品名元素、详情链接和分页元素。观察页面是否存在行内国家和三级类目，记录格式；不同语言别名不能假定相等。
8. 观察每次筛选后的 SPA 请求/响应或页面已提交查询状态。核验国家、店铺类型、三级完整路径、周期、页码与已加载数据同时一致。不要将已选 UI 直接复制成 `data_filters`，也不要将 `Date.now()` 当数据 revision。
9. 整理调查 profile，保存在 `local-profiles/sales.json` 或设置 `FASTMOSS_SALES_PROFILE` 指向其他本地文件。`profiles/sales.unverified.example.json` 仅是空 contract，不能作为已验证配置。
10. 执行发现、单类目 pages=1、两类目 week/month 批量和分析，然后人工对照 FastMoss 页面核验每行。真实 smoke test 没通过之前不要跑全量。

## Profile contract

profile 是受信任的本地配置，包含 JS 函数文本；不加载来自商品或网页的脚本作为 profile。它必须由实际 BrowserSkill 页面调查产生。

| 字段 | 要求 |
|---|---|
| url | 实际确认的完整 HTTPS 销量榜 URL，adapter 检查重定向后 URL |
| investigation.transport | BrowserSkill |
| investigation.observed_at | 真实调查时间 |
| investigation.evidence | 调查文件相对 profile 的路径与 SHA256；运行时核验存在和哈希 |
| filter_scope | 唯一商品过滤器容器的已观察 selector |
| table_scope | 唯一销量 table 的已观察 selector，不能将 sticky clone 表头与其他表的行拼接 |
| name_selector | 可选，商品/店铺名子元素已观察 selector；不设置则从第一行提取名称 |
| period_labels | week/month 的真实中文页面标签 |
| header_aliases | 实际表头文字 → canonical field；至少 product_name/sales_period |
| product_labels | 可选，price/listed_at 复合商品单元格字段的实际前缀数组 |
| read_state_js | `(ctx) => object`，读取已提交页面状态 |
| click_filter_js | `(ctx) => object`，使用 ctx.args.dimension/label；返回 clicked 或 already_selected |
| discover_options_js | `(ctx) => array`，使用 ctx.args.level；仅返回当前父类目的选项，label/id/selectable；不把“全部”算成三级类目 |
| next_page_js | `(ctx) => object`，返回 clicked；仅确认实际末页时返回 end:true |

所有 JS hook 接收 `ctx.root`（筛选容器）、`ctx.table`（唯一销量表）、`ctx.args`。**名称、label、scope 都必须经过观察。** 不能用 substring 模糊匹配标签，不能匹配表格中的商品名作为筛选项。

`read_state_js` 返回：

```javascript
{
  logged_in: true,  // 从实际已登录证据读取，不能写常量绕过
  ready: true,
  loading: false,
  no_data: false,
  country: '实际选中标签',
  shop_type: '实际选中标签',
  l1: '实际一级类目',
  l2: '实际二级类目',
  l3: '实际三级类目',
  period: '实际周期标签',
  page: 1,         // 已加载页码数字
  revision: '已提交查询/响应唯一标记或已确认 table revision',
  data_filters: {country, shop_type, l1, l2, l3, period, page}
}
```

以上结构只是 contract，不是网页实测状态。`data_filters` 必须代表**当前 table 已完成加载的筛选条件**，不是期望参数或乐观 UI 状态。国家筛选导致其他筛选重置时，要等已设置条件全部再次确认；任何字段未知就报错。真正变更筛选和分页时必须出现新 revision，连续两次状态稳定后才读表，读表前后状态一致才允许保存。

证据哈希能防止配置和文件不一致，不能自动证明人为编写的 JS 语义正确。必须做真实 smoke test 和人工对照。

## 请本地 Codex 完成的剩余工作

在本仓库 feature/sales-cli 分支中，用你电脑上的真实 BrowserSkill 调查并实现上述 profile，必要时完善 adapter 对真实组件的支持。禁止猜 selector；不要提交完整页面 HTML、snapshot 或登录信息。完成后记录实际 URL、筛选 DOM、周/月标签、三级类目数、一个类目单页商品数、两个类目批量结果、真实 CSV 分析结果，运行 Windows Python 3.13 tests，再提交独立 commit。
