export type StrategyParamDefinition = {
  key: string;
  label: string;
  valueType: "int" | "float";
  default: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  helpText: string;
};

export type StrategyConstraint =
  | {
      type: "lt";
      left: string;
      right: string;
      message: string;
    }
  | {
      type: "ordered";
      fields: string[];
      min?: number;
      max?: number;
      message: string;
    };

export type StrategyDefinition = {
  id: string;
  name: string;
  description: string;
  category: string;
  params: StrategyParamDefinition[];
  constraints: StrategyConstraint[];
};

export type StrategiesResponse = {
  strategies: StrategyDefinition[];
};

export type StrategyParams = Record<string, number>;

export type BacktestRequest = {
  symbol: string;
  start: string;
  end: string;
  strategyId: string;
  strategyParams: StrategyParams;
  cash: number;
  commissionRate: number;
  adjust: string;
};

export type BarRecord = {
  datetime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

export type MovingAverageRecord = {
  datetime: string;
  fast: number | null;
  slow: number | null;
};

export type IndicatorPoint = {
  datetime: string;
  value: number | null;
};

export type IndicatorLine = {
  name: string;
  color: string;
  points: IndicatorPoint[];
};

export type SignalRecord = {
  datetime: string;
  signal: number;
  label: string;
  price: number;
};

export type EquityRecord = {
  datetime: string;
  cash: number;
  position: number;
  price: number;
  equity: number;
  drawdown: number;
};

export type TradeRecord = {
  datetime: string;
  side: "buy" | "sell";
  sideText: string;
  price: number;
  quantity: number;
  amount: number;
  commission: number;
};

export type DatabaseStatus = {
  connected: boolean;
  url: string;
  message: string;
};

export type HealthResponse = {
  status: string;
  name: string;
  dataSource: string;
  database: DatabaseStatus;
};

export type BacktestResponse = {
  runId?: string;
  symbol: string;
  strategy: {
    id: string;
    name: string;
    params: BacktestRequest;
  };
  dataSource: {
    provider: string;
    frequency: string;
    adjust: string;
    start: string;
    end: string;
    cached: boolean;
  };
  database: DatabaseStatus;
  metrics: {
    startingCash: number;
    finalEquity: number;
    totalReturn: number;
    annualizedReturn: number | null;
    annualizedVolatility: number | null;
    sharpeRatio: number | null;
    sortinoRatio: number | null;
    calmarRatio: number | null;
    maxDrawdown: number;
    tradeCount: number;
    closedTradeCount: number | null;
    winRate: number | null;
    profitFactor: number | null;
    expectancy: number | null;
    averageWin: number | null;
    averageLoss: number | null;
    totalCommission: number | null;
    exposure: number | null;
    averagePositionWeight: number | null;
    maxPositionWeight: number | null;
    turnover: number | null;
    barCount: number;
    signalCount: number;
  };
  bars: BarRecord[];
  indicatorLines: IndicatorLine[];
  movingAverages: MovingAverageRecord[];
  signals: SignalRecord[];
  equityCurve: EquityRecord[];
  trades: TradeRecord[];
  logs: string[];
};

export type RunSummary = {
  runId: string;
  symbol: string;
  strategyId: string;
  strategyName: string;
  provider: string;
  start: string;
  end: string;
  params: Record<string, unknown>;
  metrics: {
    starting_cash?: number;
    final_equity?: number;
    total_return?: number;
    annualized_return?: number | null;
    annualized_volatility?: number | null;
    sharpe_ratio?: number | null;
    sortino_ratio?: number | null;
    calmar_ratio?: number | null;
    max_drawdown?: number;
    trade_count?: number;
    closed_trade_count?: number | null;
    win_rate?: number | null;
    profit_factor?: number | null;
    expectancy?: number | null;
    average_win?: number | null;
    average_loss?: number | null;
    total_commission?: number | null;
    exposure?: number | null;
    average_position_weight?: number | null;
    max_position_weight?: number | null;
    turnover?: number | null;
  };
  logs: string[];
  createdAt: string;
};

export type RecentRunsResponse = {
  database: DatabaseStatus;
  runs: RunSummary[];
};

export type PersistedRunDetail = {
  database: DatabaseStatus;
  runId: string;
  summary: RunSummary;
  trades: TradeRecord[];
  equityCurve: Omit<EquityRecord, "drawdown">[];
  signals: SignalRecord[];
};

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/health`);
  if (!response.ok) {
    throw new Error("后端健康检查失败");
  }
  return response.json();
}

export async function fetchStrategies(): Promise<StrategiesResponse> {
  const response = await fetch(`${API_BASE_URL}/api/strategies`);
  if (!response.ok) {
    throw new Error("读取策略列表失败");
  }
  return response.json();
}

export async function runBacktest(request: BacktestRequest): Promise<BacktestResponse> {
  const response = await fetch(`${API_BASE_URL}/api/backtests/run`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify(request)
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(normalizeApiError(payload?.detail, response.status));
  }

  return response.json();
}

export async function runMovingAverageBacktest(
  request: BacktestRequest
): Promise<BacktestResponse> {
  return runBacktest({
    ...request,
    strategyId: "moving_average"
  });
}

function normalizeApiError(detail: unknown, status: number): string {
  if (status === 503) {
    return typeof detail === "string" ? detail : "服务暂不可用，请检查数据库和后端服务。";
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => translateValidationMessage(item?.msg)).join("；");
  }
  if (typeof detail === "string") {
    return detail;
  }
  return "后端返回了无法识别的错误";
}

function translateValidationMessage(message: unknown): string {
  if (typeof message !== "string") {
    return "参数校验失败";
  }
  const dictionary: Record<string, string> = {
    "Field required": "缺少必填参数",
    "Input should be greater than 0": "数值必须大于 0",
    "Input should be greater than or equal to 0": "数值不能小于 0"
  };
  return dictionary[message] ?? message;
}

export async function fetchRecentRuns(limit = 8): Promise<RecentRunsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/backtests/runs?limit=${limit}`);
  if (!response.ok) {
    throw new Error("读取回测历史失败");
  }
  return response.json();
}

export async function fetchRunDetail(runId: string): Promise<PersistedRunDetail> {
  const response = await fetch(`${API_BASE_URL}/api/backtests/${runId}`);
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(normalizeApiError(payload?.detail, response.status));
  }
  return response.json();
}
