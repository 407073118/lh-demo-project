# LH Quant

LH Quant 是一个用于学习量化研究的 Python 入门项目。它包含真实行情下载、数据校验、策略信号、简单回测引擎和命令行工具，适合先把完整流程跑通。

项目刻意保持轻量：

- `pandas` 和 `numpy` 负责数据处理
- `typer` 和 `rich` 负责命令行交互
- `sqlalchemy` 和本地 MySQL 负责行情缓存、回测记录和可追溯数据闭环
- `pytest` 和 `ruff` 负责测试和代码检查
- `backtesting.py` 和 `vectorbt` 放在可选依赖里，后续需要时再接

这只是学习和研究脚手架，不是投资建议，也不是实盘交易系统。

## 快速开始

```powershell
cd E:\lh
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
pytest
lhq demo-backtest --periods 120 --fast 10 --slow 30
```

默认数据库连接为本地 MySQL：

```text
mysql+pymysql://root:123456@localhost:3306/lh_quant?charset=utf8mb4
```

如果你想换成别的库，可以设置环境变量：

```powershell
$env:LH_QUANT_DATABASE_URL="mysql+pymysql://root:123456@localhost:3306/lh_quant?charset=utf8mb4"
```

## 真实行情数据

项目默认以数据库为事实源：先把真实行情下载并入库，再从数据库读取完整区间进行回测。
A股优先使用 AKShare，只有 API 回测链路中 AKShare 不可用时才会尝试 Yahoo Finance 兜底。

```powershell
lhq data download-akshare --symbol 000001 --start 2024-01-01 --end 2024-06-30 --adjust qfq
lhq backtest-db --symbol 000001 --start 2024-01-01 --end 2024-06-30 --fast 5 --slow 20
```

CSV 只作为历史数据迁移入口，不再作为回测事实源。导入后仍然从数据库回测：

```powershell
lhq data import-csv --file data\market\old_bars.csv --symbol 000001 --provider CSV导入
```

Yahoo 的 chart 接口适合学习和原型验证，但它不是正式 SLA 数据服务。严肃研究或生产系统应该接入授权清晰、数据版本可追溯、公司行为处理明确的数据源。

## Web 工作台

前端位于 `apps/web`，使用 React、Vite 和 ECharts。工作台现在按 Universe/Data、Strategy、Risk/Execution 拆分配置区，并把回测结果拆成概览、收益/风险、价格/信号、订单/成交、数据血缘等标签页。

策略列表接口 `/api/strategies` 会返回参数定义和 `constraints`，前端与后端共享这些约束来校验快慢均线、突破/退出窗口、RSI 阈值等跨参数关系。回测接口 `/api/backtests/run` 返回更完整的指标，包括 Sortino、Calmar、胜率、盈亏比、期望、佣金、暴露和换手率。已落库运行可以通过 `/api/backtests/{runId}` 读取摘要、权益点、交易记录和信号点，最近回测列表会使用这个接口打开历史运行摘要。

## 项目结构

```text
src/lh_quant/
  data/          数据契约、真实数据下载、开发演示数据生成
  storage/       MySQL/SQLite 表结构、行情入库、回测记录
  strategies/    不绑定具体框架的策略函数
  backtest/      最小信号回测引擎
  cli.py         命令行入口
apps/web/        A股研究工作台前端
docs/
  research/      量化和开源框架调研
  data-sources.md
tests/           数据契约、策略、回测和 CLI 测试
```

## 为什么不一开始就上重框架

第一版使用一个很小的内部回测引擎，是为了让核心概念看得见：K 线、信号、成交、持仓、权益和指标。策略代码保持框架无关，后续可以按需求接 `backtesting.py`、`vectorbt`、`zipline-reloaded`、`Qlib` 或 `LEAN`。
