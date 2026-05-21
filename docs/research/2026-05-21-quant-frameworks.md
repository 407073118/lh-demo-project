# 量化和开源框架调研

日期：2026-05-21

## 什么是量化

量化投资或量化交易，是用数据、统计、数学模型和程序，把投资或交易决策变成可重复验证的流程。
一个典型流程包括：

1. 提出假设，例如动量、均值回归、carry 或某种风险溢价。
2. 收集并清洗数据。
3. 把假设转换成交易信号。
4. 用尽量真实的假设做回测。
5. 评估收益、回撤、换手率、交易成本和稳健性。
6. 真金白银投入前先做模拟交易。
7. 持续监控策略漂移、数据故障和市场状态变化。

难点不只是写代码，而是避免坏数据、过拟合、未来函数、过于理想的手续费假设，以及无法真实执行的策略
带来的虚假信心。

## 开源框架对比

| 框架 | 适合场景 | 优点 | 取舍 |
| --- | --- | --- | --- |
| backtesting.py | 轻量单标的策略研究 | API 小，直接吃 pandas DataFrame，统计和画图上手快 | 偏单标的，不适合复杂组合再平衡或套利 |
| Backtrader | 经典事件驱动回测和交易 | 策略、指标、分析器、经纪商和数据源概念完整 | 生态偏老，项目容易被框架概念绑住 |
| VectorBT | 参数扫描和 notebook 研究 | 基于 pandas/NumPy 的向量化模型，适合批量实验 | 更偏数组思维，事件细节对新手不够直观 |
| Zipline Reloaded | 事件驱动股票研究 | PyData 生态集成好，保留 Quantopian 风格算法模型 | 数据 bundle 和环境成本较高 |
| Qlib | 机器学习量化研究 | 覆盖 alpha、风险、组合、执行和模型训练流水线 | 平台较重，不适合作为最小入门项目 |
| Freqtrade | 加密货币 bot | 支持交易所、回测、dry-run、实盘、WebUI 和优化 | 强绑定加密货币交易 bot 场景 |
| QuantConnect LEAN | 专业多资产引擎 | 事件驱动完整，支持多市场和实盘 | 技术栈重，Python 运行在更大的 LEAN 体系里 |

## 当前技术栈决策

v0.1 先使用小型内部回测引擎，加上框架无关的策略函数。这样能保证底层单元测试、代码清楚、学习曲线平缓，
同时保留后续适配外部框架的空间。

下一步最可能接的是 `backtesting.py`，因为它轻、DataFrame 友好，适合快速做单标的策略验证。
如果要做参数扫描和批量研究，`vectorbt` 更合适。LEAN、Freqtrade、Qlib 和 Zipline Reloaded 更适合
在需求明确后分别开专门方向。

## 资料来源

- backtesting.py 快速开始：https://kernc.github.io/backtesting.py/doc/examples/Quick%20Start%20User%20Guide.html
- Backtrader 文档：https://www.backtrader.com/
- VectorBT 文档：https://vectorbt.dev/
- Zipline Reloaded GitHub：https://github.com/stefan-jansen/zipline-reloaded
- Microsoft Qlib GitHub：https://github.com/microsoft/qlib
- Freqtrade GitHub：https://github.com/freqtrade/freqtrade
- QuantConnect LEAN GitHub：https://github.com/QuantConnect/Lean
