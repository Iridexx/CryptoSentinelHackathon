import { Capacitor, CapacitorHttp } from '@capacitor/core';

const BACKEND_URL = (import.meta.env.VITE_BACKEND_API_BASE_URL as string | undefined)?.replace(/\/+$/, '');
const READ_TOKEN = import.meta.env.VITE_API_READ_TOKEN as string | undefined;

export type KillSwitchState = 'running' | 'soft_stop' | 'hard_stop' | 'degraded';

export interface AgentStatus {
  mode: string;
  markets_enabled: string;
  execution_mode: string;
  kill_switch: KillSwitchState;
  fast_loop_last_tick: string | null;
  slow_loop_last_tick: string | null;
}

export interface EligibleTokensResponse {
  count: number;
  tokens: string[];
}

export interface AgentWatchlistResponse {
  eligible_count: number;
  eligible_tokens: string[];
  selected_count: number;
  selected_tokens: string[];
}

export interface SpotPositionView {
  position_id: string;
  asset: string;
  size: string;
  entry_price: string;
  current_price: string;
  pnl_unrealized: string;
  stop_loss?: string | null;
  take_profit_1?: string | null;
  take_profit_2?: string | null;
  status: string;
  opened_at: string;
}

export interface SpotTradeView {
  trade_id: string;
  asset: string;
  side: string;
  amount: string;
  price: string;
  status: string;
  tx_hash?: string | null;
  timestamp_utc: string;
}

export interface SpotView {
  open_positions: SpotPositionView[];
  history: SpotTradeView[];
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  win_rate_pct: number;
  trade_count: number;
}

export interface PerpPositionView {
  position_id: string;
  asset: string;
  side: string;
  size: string;
  entry_price: string;
  current_price: string;
  leverage: number;
  pnl_unrealized: string;
  liquidation_price?: string | null;
  funding_rate?: string | null;
  status: string;
  opened_at: string;
}

export interface PerpTradeView {
  trade_id: string;
  asset: string;
  side: string;
  direction: string;
  size: string;
  price: string;
  leverage: number;
  status: string;
  tx_hash?: string | null;
  timestamp_utc: string;
}

export interface PerpView {
  open_positions: PerpPositionView[];
  history: PerpTradeView[];
  realized_pnl_usd: string;
  unrealized_pnl_usd: string;
  win_rate_pct: number;
  trade_count: number;
}

export interface PnlPoint {
  timestamp_utc: string;
  total_equity_usd: string;
  drawdown_pct: string;
}

export interface GlobalView {
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
}

export interface AgentMobileSettings {
  mode: string;
  markets_enabled: string;
  execution_mode: string;
  network: string;
  test_scaling_pct: number;
  operating_hours_utc: string;
  capital_per_trade_pct: number;
  max_open_positions: number;
  max_total_exposure_pct: number;
  daily_loss_limit_pct: number;
  drawdown_cap_pct: number;
  min_pool_liquidity_usd: number;
  max_slippage_pct: number;
  cooldown_minutes: number;
  spot_confidence_threshold: number;
  spot_volatility_trigger_pct: number;
  spot_relative_volume_threshold: number;
  spot_atr_stop_multiplier: number;
  spot_trailing_distance_pct: number;
  spot_partial_take_profit_pct: number;
  spot_time_stop_hours: number;
  perp_direction_mode: string;
  perp_default_leverage: number;
  perp_dynamic_leverage_enabled: boolean;
  perp_value_area_pct: number;
  perp_atr_stop_multiplier: number;
  perp_time_stop_hours: number;
}

export interface AgentSettingsResponse {
  settings: AgentMobileSettings;
  source: string;
  persisted: boolean;
}

export interface CredentialCheck {
  name: string;
  configured: boolean;
  status: string;
}

export interface CredentialValidationResponse {
  checks: CredentialCheck[];
  lock_expires_at: string;
  lock_ttl_seconds: number;
}

export interface MobileWalletView {
  networks: Array<{
    network: string;
    address: string | null;
    configured: boolean;
    role: string;
    balance_status: string;
    balances: Array<{
      asset: string;
      balance: string;
      decimals: number;
      source: string;
    }>;
  }>;
}

function requireBackend(): string {
  if (!BACKEND_URL) throw new Error('Backend URL is not configured');
  if (!READ_TOKEN) throw new Error('Read token is not configured');
  return BACKEND_URL;
}

function authHeaders(token = READ_TOKEN): Record<string, string> {
  if (!token) throw new Error('API token is not configured');
  return { Authorization: `Bearer ${token}`, Accept: 'application/json' };
}

async function request<T>(
  path: string,
  options: { method?: 'GET' | 'PUT' | 'POST'; body?: unknown; token?: string } = {},
): Promise<T> {
  const method = options.method ?? 'GET';
  const url = `${requireBackend()}${path}`;
  const headers = {
    ...authHeaders(options.token),
    ...(options.body ? { 'Content-Type': 'application/json' } : {}),
  };

  if (Capacitor.isNativePlatform()) {
    const response = await CapacitorHttp.request({
      method,
      url,
      headers,
      data: options.body,
      connectTimeout: 12_000,
      readTimeout: 30_000,
    });
    if (response.status < 200 || response.status >= 300) {
      throw new Error(`Agent API: ${response.status}`);
    }
    return response.data as T;
  }

  const response = await fetch(url, {
    method,
    headers,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (!response.ok) throw new Error(`Agent API: ${response.status}`);
  return await response.json() as T;
}

export function fetchAgentStatus(): Promise<AgentStatus> {
  return request<AgentStatus>('/api/v1/agent/status');
}

export function fetchEligibleTokens(): Promise<EligibleTokensResponse> {
  return request<EligibleTokensResponse>('/api/v1/agent/eligible-tokens');
}

export function fetchAgentWatchlist(): Promise<AgentWatchlistResponse> {
  return request<AgentWatchlistResponse>('/api/v1/agent/watchlist');
}

export function updateAgentWatchlist(tokens: string[], adminToken: string): Promise<AgentWatchlistResponse> {
  return request<AgentWatchlistResponse>('/api/v1/agent/watchlist', {
    method: 'PUT',
    body: { tokens },
    token: adminToken,
  });
}

export function fetchSpotView(): Promise<SpotView> {
  return request<SpotView>('/api/v1/views/spot');
}

export function fetchPerpView(): Promise<PerpView> {
  return request<PerpView>('/api/v1/views/perp');
}

export function fetchGlobalView(): Promise<GlobalView> {
  return request<GlobalView>('/api/v1/views/global');
}

export function fetchAgentSettings(): Promise<AgentSettingsResponse> {
  return request<AgentSettingsResponse>('/api/v1/mobile/agent/settings');
}

export function saveAgentSettings(settings: AgentMobileSettings, adminToken: string): Promise<AgentSettingsResponse> {
  return request<AgentSettingsResponse>('/api/v1/mobile/agent/settings', {
    method: 'PUT',
    body: settings,
    token: adminToken,
  });
}

export function validateOnboarding(adminToken: string): Promise<CredentialValidationResponse> {
  return request<CredentialValidationResponse>('/api/v1/mobile/agent/onboarding/validate', {
    method: 'POST',
    token: adminToken,
  });
}

export function fetchMobileWallet(): Promise<MobileWalletView> {
  return request<MobileWalletView>('/api/v1/mobile/agent/wallet');
}

export function setKillSwitch(state: KillSwitchState, adminToken: string): Promise<AgentStatus> {
  return request<AgentStatus>('/api/v1/agent/kill-switch', {
    method: 'PUT',
    body: { state },
    token: adminToken,
  });
}
