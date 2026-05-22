# 数据、处理、策略与因子同步优化报告

日期：2026-05-22  
范围：`src/lh_quant`、`apps/web`、数据链路、策略/因子体系、外部数据源可行性  
方法：并行 agent 审查 + 本地代码检查 + 外部来源可行性核对

## 0. 一句话结论

当前项目已经是一个可以跑通 A 股日线回测的 MVP，但距离“像聚宽一样”的量化研究平台还差四层能力：可信数据底座、因子/策略资产库、真实研究工作流、可解释的回测与对比系统。

最应该马上做的不是继续堆 UI 卡片，而是先把“数据是否完整、因子从哪里来、策略如何管理、回测用的到底是哪版数据”这些底层问题补上。否则界面再像平台，用户一跑策略就会发现核心能力不够硬。

## 1. 当前状态判断

### 已经具备的能力

- 后端可以通过 AKShare 拉取 A 股日线行情，并落到本地数据库。
- 已有基础数据校验：OHLCV 数值、日期可解析、价格范围、成交量非负、重复 symbol/datetime 检查。
- 已有基础策略注册表，内置均线、动量突破、RSI 反转三类策略。
- 已有单标的回测引擎、收益曲线、交易记录、部分绩效指标。
- 前端已有平台式布局雏形，包含研究区、策略参数、数据目录、结果区、历史回测等模块。

### 核心问题

- 数据层只有行情表和导入记录，缺少证券主数据、交易日历、复权因子、停牌/ST/退市、指数成分、财务与因子表。
- 缓存判断只看 ingestion 是否覆盖请求区间，没有按交易日历检查缺失交易日、停牌、半截数据、空返回。
- 回测结果没有绑定行情快照、数据源版本、参数版本，之后很难复现。
- 策略接口只支持 `-1/0/1` 信号，无法表达组合权重、调仓频率、风控约束、多标的选股。
- 因子层目前基本不存在，前端的数据目录里标成 `planned`，但没有后端模型和同步管线支撑。
- 前端很多入口看起来像功能，但实际上是静态展示或无动作按钮，用户会很快失去信任。
- 外部策略/因子不能简单“直接同步过来”。行情和因子可以走授权 API；策略代码不能默认抓取，必须处理版权、许可证、服务条款和可执行安全。

## 2. 数据链路优化点

### 2.1 行情下载

当前问题：

- `download_akshare_bars()` 优先调用 AKShare `stock_zh_a_hist`，只有异常时才 fallback 到腾讯接口；如果返回空表，不会进入 fallback。
- README 提到 AKShare 不可用时可 fallback Yahoo，但实际 API 遇到 `AkShareDataError` 会直接返回 400，文档和行为不一致。
- 目前只处理日线 OHLCV，缺少 `amount`、`turnover`、复权方式、涨跌停、停牌状态等常用研究字段。

建议：

- P0：空结果也触发 fallback，并在错误里明确数据源、symbol、date range。
- P0：修正 README，或者真正实现 Yahoo/其他 fallback，避免“文档承诺但系统没有”。
- P1：把数据源抽象成 `MarketDataProvider`，至少支持 AKShare、Tushare 两个 adapter。
- P1：新增数据源健康检查接口，前端显示“当前使用哪个源、最近同步时间、覆盖范围、失败原因”。

### 2.2 数据校验

当前问题：

- 校验停留在单行数值合法性，没有检查交易日连续性。
- 没有证券交易日历，因此无法判断“缺一天是停牌还是数据漏了”。
- 没有 instrument master，无法判断 symbol 是否真实存在、上市/退市区间是否匹配。

建议：

- P0：新增 `trading_calendar` 表，按交易所记录交易日。
- P0：新增 `instruments` 表，记录证券代码、名称、交易所、上市日、退市日、状态、板块。
- P0：缓存命中时按交易日历检查覆盖率，而不是只看请求区间。
- P1：新增数据质量报告：缺失交易日、重复 bar、异常涨跌幅、零成交量、价格为 0、复权跳变。

### 2.3 存储和可复现性

当前问题：

- `market_data_ingestions` 记录导入任务，但回测只保存 summary/trades/equity/signals。
- 回测结果没有记录使用了哪一批行情、哪一个 provider、哪一次同步、哪版策略定义。
- 本地 MySQL 默认连接偏开发机配置，不利于部署和用户配置。

建议：

- P0：在 `backtest_runs` 中保存 `data_source`、`data_version`、`ingestion_ids`、`strategy_version`、`factor_version`。
- P0：新增 `.env.example`，前端数据库未连接时给出“配置数据库/使用示例数据/重试连接”的明确动作。
- P1：增加 `data_snapshots` 或 `run_inputs` 表，保存回测输入摘要，保证结果可复现。
- P1：建立同步任务表 `sync_jobs`，记录任务状态、进度、错误、耗时、增量范围。

## 3. 数据处理和因子层优化点

### 3.1 因子层缺失

当前问题：

- 前端有因子相关展示，但后端没有统一因子定义、因子值、因子计算任务。
- 策略只能直接在行情 DataFrame 上计算指标，无法复用因子。
- 没有因子元数据：频率、方向、分组、单位、来源、计算公式、依赖字段、更新时间。

建议新增表：

- `factor_definitions`：因子 id、名称、分类、频率、方向、描述、来源、公式、许可证、状态。
- `factor_values`：factor id、symbol、date、value、source、version。
- `factor_runs`：本地计算或外部同步任务记录。
- `factor_exposures`：组合/策略回测后的因子暴露，可 P2 做。

P0 本地先做这些基础因子：

- 收益类：1/5/20/60 日收益率。
- 波动类：20/60 日波动率、ATR。
- 趋势类：MA、EMA、MACD。
- 反转类：RSI、短期反转。
- 流动性类：成交量均值、成交额均值、换手率，前提是补齐字段。

### 3.2 因子同步

可行方向：

- AKShare：适合快速补数据和原型，但商业稳定性和接口变动风险较高。
- Tushare Pro：适合做第一套正式 A 股数据 adapter，接口清晰，有行情、财务、指数、部分特色数据。
- JoinQuant/jqdatasdk：适合补 A 股研究数据和部分因子接口，但要遵守平台权限和调用限制。
- RiceQuant/RQData/RQFactor：更偏专业付费数据和因子研究体系，适合中后期。
- BigQuant：有大量基础因子和数据能力，可调研商业授权后接入。

建议路径：

1. 短期：继续保留 AKShare，但只作为 prototype/default free provider。
2. 第一正式源：接入 Tushare Pro，先同步交易日历、日线行情、复权因子、指数行情、财务指标。
3. 因子体系：先本地计算一批基础因子，再做外部因子同步 adapter。
4. 付费升级：根据预算选择 JoinQuant/RiceQuant/BigQuant 中的一个作为专业因子源。

## 4. 策略系统优化点

### 4.1 策略定义太薄

当前问题：

- 策略定义主要是 `id/name/description/category/params/signal_builder/overlay_builder`。
- 参数类型只有 int/float，前端也是 `Record<string, number>`。
- 约束只支持简单大小关系，无法表达枚举、布尔、标的池、调仓频率、止损、基准、成本模型。

建议：

- P0：扩展参数 schema，支持 `number`、`integer`、`boolean`、`enum`、`date`、`universe`、`factor`。
- P0：策略定义加入 `version`、`author`、`source`、`license`、`tags`、`default_universe`、`supported_frequencies`。
- P1：策略从硬编码注册改成 manifest + Python module plugin。
- P1：新增策略模板：择时、单因子选股、多因子打分、行业中性、轮动策略。

### 4.2 回测引擎离真实研究平台有明显距离

当前问题：

- 单标的、long-only、all-in/clear。
- 信号在同一根 bar close 成交，容易产生未来函数或过于理想的成交假设。
- 没有多标的组合、目标权重、调仓日、仓位上限、行业约束。
- 没有滑点、T+1、涨跌停不可成交、停牌不可成交、成交量容量限制。

建议：

- P0：结果页明确显示当前引擎假设，避免用户误以为是生产级回测。
- P1：新增 portfolio backtest engine，支持多标的、目标权重、调仓周期。
- P1：新增交易成本模型：佣金、印花税、滑点、最小手续费。
- P1：新增 A 股交易约束：T+1、涨跌停、停牌。
- P2：新增容量、冲击成本、撮合模型、订单模型。

### 4.3 策略能不能从外部网站同步

结论：可以同步“元数据、因子值、行情数据”，但不应该默认同步外部平台的策略代码。

可以做：

- 用户自己上传的策略。
- 开源策略仓库，且许可证允许使用。
- 官方 API 或商务授权提供的策略模板。
- 公开论文或公开公式，重新实现为本地策略，并标注来源。

不建议做：

- 自动抓取聚宽/米筐/BigQuant/WorldQuant 等平台的用户策略代码。
- 绕过登录、批量爬取、复制社区策略正文。
- 把外部策略代码直接执行在本地服务里。

推荐实现：

- `strategy_sources`：记录来源、URL、许可证、同步方式、是否可执行。
- `strategy_imports`：记录导入批次、hash、人工审核状态。
- 外部策略默认进入“草稿/只读参考”，必须人工确认许可证并通过安全扫描后才能变成本地可运行策略。
- 对论文类策略，保存公式和 citation，由我们在本地重新实现。

## 5. 前端功能不好用的地方

### 5.1 很多按钮像功能，但实际没有动作

问题：

- 顶部导航“数据/研究/回测/模拟交易/策略库/社区”大部分没有真实路由或功能。
- 研究区的 `strategy.py`、`research.ipynb`、`factor.py` 更像静态装饰。
- “保存/回测/模拟”按钮没有完整工作流。
- 模拟盘只是展示面板，没有组合、订单、持仓、资金、风控。

建议：

- P0：所有不可用入口要么接上功能，要么变成明确的 disabled 状态并显示原因。
- P0：顶部导航至少拆出真实页面：数据、策略库、研究、回测记录。
- P1：研究区支持保存策略草稿、从模板创建策略、运行参数校验。

### 5.2 数据目录只是静态说明

问题：

- 数据目录展示 dataset/fields，但不能看样本、覆盖范围、更新时间、缺失率、同步状态。
- 用户无法判断“我现在能不能放心用这些数据”。

建议：

- P0：数据目录卡片改成数据资产列表，不使用左侧彩色边框。
- P0：每个数据资产显示 provider、coverage、last sync、quality score、row count、status。
- P1：点击数据资产进入详情：字段字典、样本数据、缺失统计、同步日志。

### 5.3 策略配置像 demo，不像研究工具

问题：

- 只有策略下拉和几个数字输入。
- 没有策略搜索、分类、标签、收藏、版本、作者、来源。
- 没有参数预设、恢复默认、参数扫描、批量回测。

建议：

- P0：新增策略库页面，支持分类/搜索/标签/来源/风险等级。
- P0：参数区根据 schema 渲染不同控件，而不是全部数字输入。
- P1：支持参数模板、参数扫描、回测队列。
- P1：结果页支持多次回测对比。

### 5.4 数据库断开时体验差

问题：

- `databaseReady` 为 false 时，运行能力被锁住，但用户不知道下一步该干什么。

建议：

- P0：断开时展示三种动作：配置数据库、使用示例数据、重试连接。
- P0：后端提供 `/api/health/database` 的详细错误分类，但不要泄露密码。
- P1：内置 SQLite/local demo mode，方便新用户先体验完整流程。

## 6. 对标聚宽式平台的缺口

| 模块 | 当前项目 | 聚宽式平台预期 | 优先级 |
| --- | --- | --- | --- |
| 数据源 | AKShare 日线为主 | 行情、财务、指数、基金、期货、宏观、行业、成分、因子 | P0-P2 |
| 数据质量 | 基础行级校验 | 日历级完整性、异常检测、版本和来源追踪 | P0 |
| 因子 | 基本缺失 | 因子库、因子计算、因子分析、因子回测 | P0-P1 |
| 策略 | 三个硬编码策略 | 策略库、模板、导入、版本、社区/示例 | P0-P1 |
| 研究 | 静态代码展示 | Notebook/脚本/数据查询/因子分析 | P1 |
| 回测 | 单标的信号回测 | 多标的组合、调仓、交易约束、成本、基准 | P1 |
| 结果分析 | 基础 summary/chart | 归因、年度/月度收益、回撤区间、交易分析、对比 | P1 |
| 任务系统 | 同步假 async | 真队列、进度、取消、日志、重跑 | P1 |
| 模拟交易 | 静态面板 | 组合、订单、持仓、成交、风控、日志 | P2 |
| 外部同步 | 无正式 connector | 授权数据/因子 connector，策略需许可证 | P0-P1 |

## 7. 推荐迭代路线

### P0：先把平台骨架变可信

1. 新增数据基础表：`instruments`、`trading_calendar`、`corporate_actions`、`sync_jobs`。
2. 改造缓存命中逻辑：按交易日历检查完整性，空结果触发 fallback。
3. 为回测结果绑定 `data_source`、`data_version`、`strategy_version`。
4. 新增因子表：`factor_definitions`、`factor_values`、`factor_runs`。
5. 策略参数 schema 升级，支持 enum/bool/factor/universe。
6. 前端数据目录改为真实数据资产视图。
7. 前端移除或禁用假按钮，导航变成真实页面。
8. 数据库断开时提供配置/示例数据/重试入口。
9. 明确标注当前回测引擎假设，避免误导用户。

### P1：接近真实研究工作流

1. 接入 Tushare Pro adapter。
2. 同步交易日历、复权因子、指数行情、财务指标。
3. 实现本地基础因子计算管线。
4. 新增策略库页面和策略 manifest。
5. 新增参数扫描和批量回测队列。
6. 回测引擎支持多标的组合、目标权重、调仓周期。
7. 结果页支持 benchmark、年度/月度收益、回撤区间、交易分析。
8. 历史回测支持搜索、过滤、对比、导出。

### P2：做出平台壁垒

1. 接入 JoinQuant/RiceQuant/BigQuant 中至少一个专业因子源。
2. 实现因子分析：IC、IR、分层回测、换手、行业中性。
3. 加入组合归因、风格暴露、行业暴露。
4. 模拟交易从静态面板升级为真实 paper trading。
5. 评估引入 LEAN/自研增强引擎作为高级回测后端。
6. 做策略来源审核与安全执行沙箱。

## 8. 外部来源清单

| 来源 | 适合接什么 | 风险/限制 | 建议 |
| --- | --- | --- | --- |
| AKShare | 免费行情、数据原型 | 接口变动、商业稳定性、部分数据源限制 | 保留为免费 provider，但不要作为唯一正式源 |
| Tushare Pro | A 股行情、财务、指数、日历、复权 | token/积分/权限 | 第一优先级正式接入 |
| JoinQuant/jqdatasdk | A 股研究数据、部分因子 | 平台权限、调用限制、条款 | 接数据/因子，不抓策略代码 |
| RiceQuant/RQData/RQFactor | 专业行情和因子体系 | 商业授权 | 中期接入，适合严肃因子研究 |
| BigQuant | 大量基础因子和平台数据 | 商业授权、平台绑定 | 作为因子源备选 |
| 掘金量化/gm | 交易、模拟、实盘 SDK | 更偏交易接口 | P2 用于模拟/实盘桥接 |
| QuantConnect/LEAN | 开源回测引擎和指标体系 | A 股数据不天然完整，数据下载有条款限制 | 可借鉴/评估引擎，不作为初始数据源 |
| Quantpedia | 策略研究元数据 | 不是代码同步源 | 可做策略灵感/分类，不直接导入执行 |
| WorldQuant/101 Alphas | 公开论文公式 | BRAIN 平台条款禁止抓取/数据库式复制 | 只按公开论文重写公式，不能抓平台内容 |

参考链接：

- AKShare: https://akshare.akfamily.xyz/introduction.html
- Tushare Pro: https://tushare.pro/
- Tushare SDK/API 文档: https://tushare.pro/document/1?doc_id=290
- JoinQuant 数据: https://www.joinquant.com/data
- jqdatasdk: https://github.com/JoinQuant/jqdatasdk
- jqfactor_analyzer: https://github.com/JoinQuant/jqfactor_analyzer
- RiceQuant SDK: https://www.ricequant.com/doc/rqsdk/manual-rqsdk
- RQFactor: https://www.ricequant.com/doc/rqfactor/manual/index-rqfactor
- BigQuant 数据介绍: https://bigquant.com/doc/data_introduction.html
- BigQuant 数据特性: https://bigquant.com/doc/data_features.html
- 掘金量化 SDK: https://www.myquant.cn/docs2/operatingInstruction/study/SDK%E4%B8%8B%E8%BD%BD%E5%8F%8A%E8%AF%B4%E6%98%8E%E6%96%87%E6%A1%A3.html
- QuantConnect LEAN: https://github.com/QuantConnect/Lean
- QuantConnect 本地数据下载说明: https://www.quantconnect.com/docs/v2/local-platform/datasets/downloading-data
- Quantpedia: https://quantpedia.com/
- WorldQuant 条款: https://www.worldquant.com/terms-and-conditions/
- 101 Formulaic Alphas: https://arxiv.org/abs/1601.00991

## 9. 最推荐下一步

下一轮不要再先改视觉，而是直接进入“数据底座 + 策略/因子架构”实现：

1. 建表和 repository：`instruments`、`trading_calendar`、`factor_definitions`、`factor_values`、`sync_jobs`。
2. Provider 抽象：先抽 AKShare，再加 Tushare adapter。
3. 前端数据页：用真实 API 展示数据覆盖、同步状态、质量分。
4. 策略库：从 dropdown 升级为可搜索策略资产库。
5. 回测绑定数据版本：让每次结果可复现。

做到这里，项目才会从“像量化平台的页面”变成“开始有量化平台内核”。
