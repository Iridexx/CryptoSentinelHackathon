export type KillSwitchState = 'running' | 'soft_stop' | 'hard_stop' | 'degraded';

export type SpotPosition = {
  position_id: string;
  asset: string;
  size: string;
  entry_price: string;
  current_price: string;
  pnl_unrealized: string;
  status: string;
  opened_at: string;
};

export type SpotTrade = {
  trade_id: string;
  asset: string;
  side: string;
  amount: string;
  price: string;
  status: string;
  timestamp_utc: string;
};

export type SpotView = {
  open_positions: SpotPosition[];
  history: SpotTrade[];
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  win_rate_pct: number;
  trade_count: number;
};

export type PnlPoint = {
  timestamp_utc: string;
  total_equity_usd: string;
  drawdown_pct: string;
};

export type GlobalView = {
  total_equity_usd: string;
  initial_equity_usd: string;
  pnl_total_usd: string;
  pnl_total_pct: number;
  drawdown_pct: string;
  max_drawdown_pct: string;
  drawdown_cap_pct: number;
  exposure_pct: string;
  daily_pnl_usd: string;
  agent_status: string;
  trades_today: number;
  open_spot_positions: number;
  open_perp_positions: number;
  pnl_history: PnlPoint[];
};

export type AgentStatus = {
  kill_switch?: KillSwitchState;
  mode?: string;
  execution_mode?: string;
  markets_enabled?: string;
  minimum_trade_frequency?: string;
  [key: string]: unknown;
};

export type HealthPayload = {
  status?: string;
  checks?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ExecutionStatus = {
  mode?: string;
  network?: string;
  provider?: string;
  spot?: {
    active_provider?: string;
    providers?: unknown[];
  };
  perp?: {
    active_provider?: string;
    providers?: unknown[];
  };
  enabled?: boolean;
  [key: string]: unknown;
};

export type ExecutionProviderSelectionResponse = {
  active: string;
  providers: unknown[];
  selection_scope: string;
};

export type ExecutionWalletProviderView = {
  provider: string;
  market: 'spot' | 'perp';
  address?: string | null;
  network: string;
  configured: boolean;
  active: boolean;
  balance_bnb?: string | null;
  balance_status: string;
};

export type ExecutionWalletAddressView = {
  address: string;
  active: boolean;
  network: string;
  balance_bnb?: string | null;
  balance_status: string;
};

export type RpcEndpointView = {
  index: number;
  label: string;
  active: boolean;
  reachable: boolean;
  latency_ms?: number | null;
  chain_id?: number | null;
  status: 'reachable' | 'unreachable' | 'chain_mismatch';
};

export type ExecutionWalletsResponse = {
  network: string;
  chain_id: number;
  bsc_network?: 'testnet' | 'mainnet';
  active_wallet_address?: string | null;
  spot_active_provider: string;
  perp_active_provider: string;
  available_wallets: ExecutionWalletAddressView[];
  active_rpc_endpoint_index?: number | null;
  wallets: ExecutionWalletProviderView[];
  rpc_endpoints: RpcEndpointView[];
};

export type DataCoverageStatus = 'insufficient' | 'warming_up' | 'ready';

export type DataCoverageItem = {
  asset: string;
  market: 'spot' | 'perp';
  symbol: string;
  available_candles: number;
  required_candles: number;
  status: DataCoverageStatus;
  first_candle_at?: string | null;
  last_candle_at?: string | null;
  updated_at?: string | null;
  age_seconds?: number | null;
  source: string;
};

export type DataCoverageResponse = {
  generated_at: string;
  active_markets: string[];
  items: DataCoverageItem[];
};

export type LogEntry = {
  timestamp?: string | null;
  level?: string | null;
  logger?: string | null;
  message: string;
};

export type LogResponse = {
  available: boolean;
  source: string;
  entries: LogEntry[];
  truncated: boolean;
};

export type AgentSettings = Record<string, string | number | boolean>;

export type SettingsResponse = {
  settings: AgentSettings;
  source: string;
  persisted: boolean;
};

export type CredentialCheck = {
  name: string;
  configured: boolean;
  status: string;
};

export type CredentialValidationResponse = {
  checks: CredentialCheck[];
  lock_expires_at: string;
  lock_ttl_seconds: number;
};

export type MarketAsset = {
  id: string;
  symbol: string;
  name: string;
  current_price?: number | null;
  price_change_percentage_24h?: number | null;
  market_cap?: number | null;
  total_volume?: number | null;
};

export type MarketListResponse = {
  provider: string;
  currency: string;
  items: MarketAsset[];
};
