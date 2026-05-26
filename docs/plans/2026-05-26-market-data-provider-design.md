# 多数据源行情 Provider 与归一化设计

日期：2026-05-26

范围：`apps/web` 前端回测配置、`src/lh_quant/api` 回测 API、`src/lh_quant/data` 行情 provider、`src/lh_quant/storage` 行情缓存与回测血缘。

## 1. 背景

当前项目已经能通过 AKShare 拉取 A 股日线行情，并把标准化后的 K 线写入本地数据库，再从数据库读取完整区间执行回测。现有链路对学习和原型验证足够，但数据源被硬编码在 API 回测流程中，用户不能选择来源，也无法系统性比较不同数据源的质量差异。

目标是把行情来源从回测流程中抽象出来，支持前端选择数据源，并让 AKShare、Tushare、Yahoo、CSV 等来源都走统一的归一化、校验、缓存、血缘记录和回测消费逻辑。这样后续可以追踪每次回测到底用了哪一家数据、哪个接口、什么复权口径，也能为跨数据源准确性分析打基础。

## 2. 目标

- 前端回测配置区显示数据源下拉：`自动`、`Tushare`、`AKShare`、`Yahoo`。
- 后端请求契约增加稳定枚举字段：`dataProvider: auto | tushare | akshare | yahoo`。
- 后端新增统一 `MarketDataProvider` 抽象，各 provider adapter 负责下载原始数据并归一化为平台 K 线契约。
- 回测逻辑只消费统一后的 `bars`，不关心外部接口字段、代码格式和单位差异。
- 入库时记录用户请求来源、实际使用来源、具体接口、原始代码、标准代码、数据版本、拉取时间和 fallback 过程。
- `auto` 模式支持明确的 provider chain；用户显式选择某个 provider 时不静默切换。
- 第一版先跑通多数据源链路；Tushare 只支持未复权日线，复权能力留到后续迭代。

## 3. 非目标

- 第一版不实现 Tushare 前复权和后复权。
- 第一版不做完整数据质量 UI，只保证血缘和比较所需字段入库。
- 第一版不重构全部数据表为完整数据平台模型。
- 第一版不接入 JoinQuant、RiceQuant、BigQuant 等专业源。
- 第一版不抓取外部平台策略代码。

## 4. 前端交互

在回测配置区新增“数据来源”下拉，与股票代码、起止日期、复权方式放在同一组。默认选择 `自动`。

选项：

```text
自动
Tushare
AKShare
Yahoo
```

前端请求字段：

```ts
type DataProviderId = "auto" | "tushare" | "akshare" | "yahoo";

type BacktestRequest = {
  symbol: string;
  start: string;
  end: string;
  strategyId: string;
  strategyParams: StrategyParams;
  cash: number;
  commissionRate: number;
  adjust: string;
  dataProvider: DataProviderId;
};
```

回测结果页展示两类来源：

- `requestedProvider`：用户请求的来源，例如 `auto`。
- `actualProvider`：实际成功使用的来源，例如 `AKShare`。

如果 `auto` 发生 fallback，结果页在数据血缘区域展示 provider 尝试过程，方便用户判断本次结果是否可信。

## 5. 后端 Provider 抽象

新增统一 provider 层，建议放在：

```text
src/lh_quant/data/providers.py
```

核心接口：

```python
from dataclasses import dataclass
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class MarketDataResult:
    bars: pd.DataFrame
    requested_provider: str
    actual_provider: str
    source_detail: str
    raw_symbol: str
    normalized_symbol: str
    frequency: str
    adjust: str
    data_version: str
    fetched_at: str
    fallback_chain: list[dict[str, str]]


class MarketDataProvider(Protocol):
    id: str
    name: str

    def download_bars(
        self,
        symbol: str,
        start: str,
        end: str,
        adjust: str,
    ) -> MarketDataResult:
        ...
```

每个 adapter 只负责三件事：

1. 把平台 symbol 转成数据源 symbol。
2. 调用外部接口并处理接口级错误。
3. 把原始字段归一化成平台标准 K 线。

平台统一 K 线契约继续使用：

```text
symbol
datetime
open
high
low
close
volume
```

后续 `validate_bars()`、`save_market_bars()`、覆盖率检查、策略信号生成和回测引擎都只消费这个统一结构。

## 6. Provider Registry 与选择规则

新增 provider registry，用稳定 ID 管理 adapter：

```text
auto
tushare
akshare
yahoo
```

显式选择规则：

- 用户选 `tushare`：只尝试 Tushare。失败时返回清晰错误。
- 用户选 `akshare`：只尝试 AKShare。
- 用户选 `yahoo`：只尝试 Yahoo。
- 用户选 `auto`：按后端 provider chain 自动尝试。

第一版 `auto` chain：

```text
adjust=none: Tushare -> AKShare -> Yahoo
adjust=qfq/hfq: AKShare -> Yahoo
```

Tushare 第一版只用于未复权日线。当前端或 API 请求 `dataProvider=tushare` 且 `adjust=qfq/hfq` 时，后端返回“第一版暂不支持 Tushare 复权，请选择不复权或切换 AKShare”。`auto` 模式下遇到复权请求则直接跳过 Tushare。

## 7. 归一化规则

### AKShare

沿用现有 `download_akshare_bars()` 能力：

- 支持 `qfq`、`hfq` 和不复权。
- 优先东方财富日线接口。
- 东方财富失败或空结果时尝试腾讯接口。
- 腾讯接口的成交量按现有逻辑统一到平台口径。

### Tushare

第一版新增未复权日线下载：

- 平台代码 `000001` 转为 `000001.SZ`。
- 平台代码 `600519` 转为 `600519.SH`。
- 调用 Tushare `daily`。
- `trade_date` 转为 `datetime`。
- `vol` 从“手”转换为平台内部的“股”，即乘以 `100`。
- `amount` 第一版暂不进入标准 K 线，但可保留在后续扩展字段规划中。

Tushare token 从环境变量 `TUSHARE_TOKEN` 读取。缺失 token 在 `auto` 模式下记为一次可 fallback 失败；在显式 `tushare` 模式下返回错误。

### Yahoo

Yahoo 适合作为原型或兜底源，不作为严肃 A 股研究的默认正式源。第一版可以继续使用现有 `download_yahoo_bars()`，但必须经过同样的 `MarketDataResult` 包装和入库血缘记录。

## 8. 入库血缘

入库必须同时记录“用户想用什么”和“系统实际用了什么”。

建议在 `market_data_ingestions` 或对应保存函数中至少保存：

```text
requested_provider
actual_provider
source_detail
raw_symbol
normalized_symbol
frequency
adjust
data_version
fetched_at
fallback_chain
requested_start
requested_end
row_count
```

`market_bars` 继续保存标准 K 线，并使用 `actual_provider` 作为 provider 字段。这样同一只股票同一日期可以同时存在 AKShare、Tushare、Yahoo 三份数据，后续才能做横向比较。

回测记录也要绑定来源：

```text
requested_provider
actual_provider
source_detail
data_version
ingestion_id 或 ingestion_ids
fallback_chain
```

这样历史回测详情可以复原“本次结果用的是哪批数据”，而不是只知道 symbol 和日期区间。

## 9. Fallback 与错误处理

可以 fallback 的情况：

```text
TUSHARE_TOKEN 未配置
Tushare 权限不足
外部接口超时
临时网络错误
接口返回空数据
AKShare 字段变化或单接口失败
```

不建议 fallback 的情况：

```text
用户显式选择了某个 provider
symbol 格式不合法
日期区间不合法
adjust 与 provider 能力冲突
统一校验发现严重数据异常
```

`fallback_chain` 示例：

```json
[
  {
    "provider": "Tushare",
    "status": "failed",
    "reason": "TUSHARE_TOKEN is missing"
  },
  {
    "provider": "AKShare",
    "status": "succeeded",
    "sourceDetail": "AKShare 东方财富日线接口"
  }
]
```

前端和回测日志都应展示这段信息，避免用户误以为自动模式一直使用首选源。

## 10. 数据准确性分析铺垫

第一版只做来源追踪，不立即实现完整比较 UI。但入库结构要支持后续分析：

- 同一 `symbol/start/end/adjust` 下不同 provider 的日期交集。
- 各 provider 缺失日期。
- OHLC 差异。
- volume 差异。
- 复权口径差异。
- 异常日期列表。
- provider 成功率、失败原因和平均耗时。

后续可以新增数据质量报告接口：

```text
GET /api/data/compare?symbol=000001&start=2024-01-01&end=2024-06-30&providers=tushare,akshare
```

这个接口只读取已入库数据，不影响第一版回测链路。

## 11. API 改动点

请求模型：

- `BacktestRunRequest` 增加 `dataProvider`，默认 `auto`。
- `MovingAverageBacktestRequest` 同步增加 `dataProvider`，保持旧接口兼容。

响应模型：

```json
{
  "dataSource": {
    "requestedProvider": "auto",
    "actualProvider": "AKShare",
    "frequency": "1d",
    "adjust": "qfq",
    "start": "2024-01-01",
    "end": "2024-06-30",
    "cached": false,
    "sourceDetail": "AKShare 东方财富日线接口",
    "dataVersion": "akshare:runtime",
    "fallbackChain": []
  }
}
```

旧字段 `provider` 可短期保留，值等于 `actualProvider`，避免前端和测试一次性大改。

## 12. 测试计划

后端单元测试：

- `dataProvider=akshare` 时只查询 AKShare 缓存并调用 AKShare adapter。
- `dataProvider=tushare` 且 `adjust=none` 时调用 Tushare adapter。
- `dataProvider=tushare` 且 `adjust=qfq` 时返回不支持错误。
- `dataProvider=auto` 且 `adjust=none` 时按 `Tushare -> AKShare -> Yahoo` 尝试。
- `dataProvider=auto` 且 `adjust=qfq` 时跳过 Tushare。
- 显式 provider 失败时不 fallback。
- 成功入库时 provider、source_detail、data_version、fallback_chain 正确保存。
- 回测响应包含 `requestedProvider` 和 `actualProvider`。

前端测试：

- 回测表单显示数据源下拉。
- 默认选项为 `自动`。
- 提交请求携带 `dataProvider`。
- 结果页展示请求来源、实际来源和 fallback 过程。

回归测试：

- 未传 `dataProvider` 的旧请求默认走 `auto`。
- 现有 AKShare 回测链路保持可用。
- 现有历史回测详情在缺少新字段时仍能展示。

## 13. 实施顺序

1. 扩展前后端请求/响应类型，加入 `dataProvider` 与数据血缘字段。
2. 新增 provider registry 和 `MarketDataResult`。
3. 把现有 AKShare 下载包装成 `AkShareMarketDataProvider`。
4. 为 Tushare 增加未复权 `daily` 下载与标准化。
5. 把 API 中 `_get_a_share_bars()` 改为统一 provider 选择和缓存逻辑。
6. 扩展入库记录，保存 requested/actual provider 与 fallback chain。
7. 前端添加数据源下拉和结果页血缘展示。
8. 补齐后端与前端测试。

## 14. 后续迭代

- Tushare 复权：接入 `adj_factor` 或稳定 SDK 复权逻辑。
- 数据源健康检查：显示 token 状态、最近成功同步、失败原因。
- 多源数据比较报告：比较 OHLCV 差异和缺失日期。
- 数据质量评分：覆盖率、异常值、重复值、源一致性。
- 更多 provider：JoinQuant、RiceQuant、BigQuant 或本地 parquet。
