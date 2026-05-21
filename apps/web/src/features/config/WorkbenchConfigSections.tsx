import type { Dispatch, SetStateAction } from "react";
import type {
  BacktestRequest,
  StrategyDefinition,
  StrategyParamDefinition,
  StrategyParams
} from "../../api";

type BacktestFormSetter = Dispatch<SetStateAction<BacktestRequest>>;

export function UniverseDataSection({
  form,
  setForm
}: {
  form: BacktestRequest;
  setForm: BacktestFormSetter;
}) {
  return (
    <section className="form-section">
      <h2>Universe/Data</h2>
      <label>
        股票代码
        <input
          value={form.symbol}
          onChange={(event) =>
            setForm((current) => ({ ...current, symbol: event.target.value.trim() }))
          }
          placeholder="000001"
        />
      </label>
      <div className="field-grid">
        <label>
          开始日期
          <input
            type="date"
            value={form.start}
            onChange={(event) => setForm((current) => ({ ...current, start: event.target.value }))}
          />
        </label>
        <label>
          结束日期
          <input
            type="date"
            value={form.end}
            onChange={(event) => setForm((current) => ({ ...current, end: event.target.value }))}
          />
        </label>
      </div>
      <label>
        复权方式
        <select
          value={form.adjust}
          onChange={(event) => setForm((current) => ({ ...current, adjust: event.target.value }))}
        >
          <option value="qfq">前复权</option>
          <option value="hfq">后复权</option>
          <option value="">不复权</option>
        </select>
      </label>
    </section>
  );
}

export function StrategyConfigSection({
  strategies,
  selectedStrategy,
  strategyId,
  strategyParams,
  onStrategyChange,
  onParamChange
}: {
  strategies: StrategyDefinition[];
  selectedStrategy: StrategyDefinition | null;
  strategyId: string;
  strategyParams: StrategyParams;
  onStrategyChange: (strategyId: string) => void;
  onParamChange: (param: StrategyParamDefinition, value: number) => void;
}) {
  return (
    <section className="form-section">
      <h2>Strategy</h2>
      <label>
        策略模板
        <select
          value={strategyId}
          onChange={(event) => onStrategyChange(event.target.value)}
          disabled={strategies.length === 0}
        >
          {strategies.length === 0 ? <option value={strategyId}>加载策略中</option> : null}
          {strategies.map((strategy) => (
            <option value={strategy.id} key={strategy.id}>
              {strategy.name}
            </option>
          ))}
        </select>
      </label>
      {selectedStrategy ? (
        <div className="strategy-summary">
          <div>
            <strong>{selectedStrategy.category}</strong>
            <span>{selectedStrategy.name}</span>
          </div>
          <p>{selectedStrategy.description}</p>
        </div>
      ) : (
        <div className="strategy-summary muted">正在从后端读取策略模板</div>
      )}
      {selectedStrategy ? (
        <div className="field-grid">
          {selectedStrategy.params.map((param) => (
            <label key={param.key}>
              {param.label}
              <input
                type="number"
                min={param.min}
                max={param.max}
                step={param.step}
                value={strategyParams[param.key] ?? param.default}
                onChange={(event) => onParamChange(param, Number(event.target.value))}
              />
              <span className="param-help">
                {param.helpText}
                {param.unit ? `（单位：${param.unit}）` : ""}
              </span>
            </label>
          ))}
        </div>
      ) : (
        <p className="status-note">策略列表加载完成后会显示可调参数。</p>
      )}
    </section>
  );
}

export function RiskExecutionSection({
  form,
  setForm
}: {
  form: BacktestRequest;
  setForm: BacktestFormSetter;
}) {
  return (
    <section className="form-section">
      <h2>Risk/Execution</h2>
      <div className="field-grid">
        <label>
          初始资金
          <input
            type="number"
            min={1}
            value={form.cash}
            onChange={(event) => setForm((current) => ({ ...current, cash: Number(event.target.value) }))}
          />
        </label>
        <label>
          手续费率
          <input
            type="number"
            min={0}
            step={0.0001}
            value={form.commissionRate}
            onChange={(event) =>
              setForm((current) => ({
                ...current,
                commissionRate: Number(event.target.value)
              }))
            }
          />
        </label>
      </div>
    </section>
  );
}
