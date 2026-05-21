# 数据来源

## 当前数据闭环

项目现在把数据库作为事实源。命令行和 API 的默认流程都是：

```text
真实行情 API -> 标准化 K线 -> 写入 market_bars -> 记录覆盖区间 -> 从数据库读取完整区间 -> 回测 -> 写入 backtest_runs
```

这样可以避免“临时文件跑过一次就找不到来源”的问题，也方便后续补充回测快照、参数版本和数据版本。

## A股数据源

A股主数据源是 AKShare：

```text
src/lh_quant/data/akshare_provider.py
```

入库命令：

```powershell
lhq data download-akshare --symbol 000001 --start 2024-01-01 --end 2024-06-30 --adjust qfq
```

回测命令只从数据库读取完整覆盖区间：

```powershell
lhq backtest-db --symbol 000001 --start 2024-01-01 --end 2024-06-30 --fast 5 --slow 20
```

## 兜底数据源

项目仍保留 Yahoo Finance chart 数据源：

```text
src/lh_quant/data/yahoo.py
```

它不需要 API key，适合原型验证。A股 API 回测链路里，只有 AKShare 不可用时才会尝试 Yahoo Finance 兜底，并且兜底数据同样会入库后再参与回测。

## CSV 的定位

CSV 不再作为回测事实源，只作为历史数据迁移入口：

```powershell
lhq data import-csv --file data\market\old_bars.csv --symbol 000001 --provider CSV导入
```

导入后仍然使用 `lhq backtest-db` 从数据库读取和回测。

## 注意事项

AKShare 和 Yahoo Finance 都适合学习、研究和原型验证。严肃研究或生产系统应该使用条款明确、数据版本可追溯、幸存者偏差可控、公司行为处理清楚，并且能复现实验快照的数据源。
