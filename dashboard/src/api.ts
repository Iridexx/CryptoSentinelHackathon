import type {
  AgentSettings,
  AgentStatus,
  CredentialValidationResponse,
  DataCoverageResponse,
  ExecutionProviderSelectionResponse,
  ExecutionStatus,
  ExecutionWalletsResponse,
  GlobalView,
  HealthPayload,
  KillSwitchState,
  LogResponse,
  MarketListResponse,
  SettingsResponse,
  SpotView,
} from './types';

export type DashboardSession = {
  baseUrl: string;
  readToken: string;
  adminToken: string;
};

type TokenKind = 'read' | 'admin' | 'none';

async function requestJson<T>(
  session: DashboardSession,
  path: string,
  tokenKind: TokenKind = 'read',
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const token = tokenKind === 'admin' ? session.adminToken : tokenKind === 'read' ? session.readToken : '';
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const url = `${session.baseUrl.replace(/\/$/, '')}${path}`;
  const response = await fetch(url, { ...options, headers });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status} ${response.statusText}${body ? ` - ${body.slice(0, 180)}` : ''}`);
  }
  return (await response.json()) as T;
}

export function fetchSpot(session: DashboardSession) {
  return requestJson<SpotView>(session, '/api/v1/views/spot');
}

export function fetchGlobal(session: DashboardSession) {
  return requestJson<GlobalView>(session, '/api/v1/views/global');
}

export function fetchAgentStatus(session: DashboardSession) {
  return requestJson<AgentStatus>(session, '/api/v1/agent/status');
}

export function fetchReady(session: DashboardSession) {
  return requestJson<HealthPayload>(session, '/health/ready');
}

export function fetchLive(session: DashboardSession) {
  return requestJson<HealthPayload>(session, '/health/live', 'none');
}

export function fetchHeartbeat(session: DashboardSession) {
  return requestJson<HealthPayload>(session, '/health/heartbeat');
}

export function fetchExecutionStatus(session: DashboardSession) {
  return requestJson<ExecutionStatus>(session, '/api/v1/execution/status');
}

export function fetchExecutionWallets(session: DashboardSession) {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/wallets');
}

export function setSpotExecutionProvider(session: DashboardSession, provider: string) {
  return requestJson<ExecutionProviderSelectionResponse>(session, '/api/v1/execution/provider', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ provider }),
  });
}

export function setPerpExecutionProvider(session: DashboardSession, provider: string) {
  return requestJson<ExecutionProviderSelectionResponse>(session, '/api/v1/execution/perp-provider', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ provider }),
  });
}

export function setRpcEndpoint(session: DashboardSession, index: number) {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/rpc-endpoint', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ index }),
  });
}

export function setExecutionNetwork(session: DashboardSession, network: 'testnet' | 'mainnet') {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/network', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ network }),
  });
}

export function setExecutionWallet(session: DashboardSession, address: string) {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/wallet', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ address }),
  });
}

export function addExecutionWallet(session: DashboardSession, address: string) {
  return requestJson<ExecutionWalletsResponse>(session, '/api/v1/execution/wallets', 'admin', {
    method: 'POST',
    body: JSON.stringify({ address }),
  });
}

export function fetchDataCoverage(session: DashboardSession) {
  return requestJson<DataCoverageResponse>(session, '/api/v1/agent/data-coverage');
}

export function setKillSwitch(session: DashboardSession, state: KillSwitchState) {
  return requestJson<AgentStatus>(session, '/api/v1/agent/kill-switch', 'admin', {
    method: 'PUT',
    body: JSON.stringify({ state }),
  });
}

export function fetchLogs(session: DashboardSession, params: { level?: string; search?: string; limit?: number }) {
  const search = new URLSearchParams();
  search.set('limit', String(params.limit ?? 200));
  if (params.level) search.set('level', params.level);
  if (params.search) search.set('search', params.search);
  return requestJson<LogResponse>(session, `/api/v1/observability/logs?${search.toString()}`, 'admin');
}

export function fetchSettings(session: DashboardSession) {
  return requestJson<SettingsResponse>(session, '/api/v1/mobile/agent/settings');
}

export function saveSettings(session: DashboardSession, settings: AgentSettings) {
  return requestJson<SettingsResponse>(session, '/api/v1/mobile/agent/settings', 'admin', {
    method: 'PUT',
    body: JSON.stringify(settings),
  });
}

export function validateOnboarding(session: DashboardSession) {
  return requestJson<CredentialValidationResponse>(session, '/api/v1/mobile/agent/onboarding/validate', 'admin', {
    method: 'POST',
  });
}

export function fetchMarkets(session: DashboardSession, limit = 50) {
  return requestJson<MarketListResponse>(session, `/api/v1/market-data/markets?currency=usd&limit=${limit}&page=1`);
}
