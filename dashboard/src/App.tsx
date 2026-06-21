import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  addExecutionWallet,
  fetchAgentDecisions,
  fetchAgentStatus,
  fetchAssetBreakdown,
  fetchDataCoverage,
  fetchEquityCurve,
  fetchExecutionStatus,
  fetchExecutionWallets,
  fetchGlobal,
  fetchHeartbeat,
  fetchLive,
  fetchLogs,
  fetchMarkets,
  fetchNotificationPrefs,
  fetchOperationalStats,
  fetchPerp,
  fetchReady,
  fetchSettings,
  fetchSpot,
  fetchTradeDetail,
  saveNotificationPrefs,
  saveSettings,
  setKillSwitch,
  setExecutionNetwork,
  setExecutionWallet,
  setPerpExecutionProvider,
  setRpcEndpoint,
  setSpotExecutionProvider,
  validateOnboarding,
  type DashboardSession,
} from './api';
import type {
  AgentDecisionResponse,
  AgentSettings,
  NotificationPreferences,
  NotificationPreferencesResponse,
  AgentStatus,
  AssetBreakdownResponse,
  CredentialCheck,
  DataCoverageItem,
  DataCoverageResponse,
  EquityCurveResponse,
  ExecutionStatus,
  ExecutionWalletsResponse,
  GlobalView,
  HealthPayload,
  KillSwitchState,
  LogEntry,
  MarketAsset,
  OperationalStats,
  PerpView,
  SettingsResponse,
  SpotView,
  TradeDetail,
} from './types';

type Tab = 'overview' | 'spot' | 'perp' | 'global' | 'analytics' | 'health' | 'wallet' | 'logs' | 'settings' | 'onboarding' | 'markets' | 'export';
type LoadState<T> = { data: T | null; loading: boolean; error: string | null };

const tabs: { id: Tab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'spot', label: 'Spot' },
  { id: 'perp', label: 'Perp' },
  { id: 'global', label: 'Global' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'health', label: 'Health' },
  { id: 'wallet', label: 'Wallet' },
  { id: 'logs', label: 'Logs' },
  { id: 'settings', label: 'Settings' },
  { id: 'onboarding', label: 'Onboarding' },
  { id: 'markets', label: 'Markets' },
  { id: 'export', label: 'Export' },
];

const settingFields = [
  'mode',
  'markets_enabled',
  'execution_mode',
  'network',
  'capital_per_trade_pct',
  'max_open_positions',
  'max_total_exposure_pct',
  'daily_loss_limit_pct',
  'drawdown_cap_pct',
  'spot_confidence_threshold',
  'spot_trailing_distance_pct',
  'perp_default_leverage',
  'perp_dynamic_leverage_enabled',
];

const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8001';
const LEGACY_BACKEND_URL = 'http://127.0.0.1:8000';
const AUTO_REFRESH_MS = 45_000;

function emptyState<T>(data: T | null = null): LoadState<T> {
  return { data, loading: false, error: null };
}

async function loadDetail<T>(setter: (value: LoadState<T>) => void, task: () => Promise<T>) {
  setter({ data: null, loading: true, error: null });
  try {
    setter({ data: await task(), loading: false, error: null });
  } catch (error) {
    setter({ data: null, loading: false, error: error instanceof Error ? error.message : 'Request failed' });
  }
}

function normalizedStoredBackendUrl() {
  const stored = localStorage.getItem('cs.dashboard.baseUrl');
  if (!stored || stored === LEGACY_BACKEND_URL) return DEFAULT_BACKEND_URL;
  return stored;
}

export default function App() {
  const [tab, setTab] = useState<Tab>('overview');
  const [session, setSession] = useState<DashboardSession>(() => ({
    baseUrl: normalizedStoredBackendUrl(),
    readToken: localStorage.getItem('cs.dashboard.readToken') || '',
    adminToken: localStorage.getItem('cs.dashboard.adminToken') || '',
  }));
  const [spot, setSpot] = useState<LoadState<SpotView>>(emptyState());
  const [perp, setPerp] = useState<LoadState<PerpView>>(emptyState());
  const [global, setGlobal] = useState<LoadState<GlobalView>>(emptyState());
  const [equity, setEquity] = useState<LoadState<EquityCurveResponse>>(emptyState());
  const [decisions, setDecisions] = useState<LoadState<AgentDecisionResponse>>(emptyState());
  const [assetBreakdown, setAssetBreakdown] = useState<LoadState<AssetBreakdownResponse>>(emptyState());
  const [operationalStats, setOperationalStats] = useState<LoadState<OperationalStats>>(emptyState());
  const [agent, setAgent] = useState<LoadState<AgentStatus>>(emptyState());
  const [ready, setReady] = useState<LoadState<HealthPayload>>(emptyState());
  const [live, setLive] = useState<LoadState<HealthPayload>>(emptyState());
  const [heartbeat, setHeartbeat] = useState<LoadState<HealthPayload>>(emptyState());
  const [execution, setExecution] = useState<LoadState<ExecutionStatus>>(emptyState());
  const [wallets, setWallets] = useState<LoadState<ExecutionWalletsResponse>>(emptyState());
  const [coverage, setCoverage] = useState<LoadState<DataCoverageResponse>>(emptyState());
  const [logs, setLogs] = useState<LoadState<LogEntry[]>>(emptyState([]));
  const [settings, setSettings] = useState<LoadState<SettingsResponse>>(emptyState());
  const [settingsDraft, setSettingsDraft] = useState<AgentSettings>({});
  const [checks, setChecks] = useState<LoadState<CredentialCheck[]>>(emptyState([]));
  const [markets, setMarkets] = useState<LoadState<MarketAsset[]>>(emptyState([]));
  const [notice, setNotice] = useState('');
  const [walletDraft, setWalletDraft] = useState('');
  const [notifPrefs, setNotifPrefs] = useState<LoadState<NotificationPreferencesResponse>>(emptyState());

  const canRead = Boolean(session.readToken);
  const canAdmin = Boolean(session.adminToken);

  useEffect(() => {
    localStorage.setItem('cs.dashboard.baseUrl', session.baseUrl);
    localStorage.setItem('cs.dashboard.readToken', session.readToken);
    localStorage.setItem('cs.dashboard.adminToken', session.adminToken);
  }, [session.baseUrl, session.readToken, session.adminToken]);

  useEffect(() => {
    void refreshCore();
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void refreshCore(true);
    }, AUTO_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [session.baseUrl, session.readToken]);

  async function load<T>(setter: (value: LoadState<T>) => void, task: () => Promise<T>) {
    setter({ data: null, loading: true, error: null });
    try {
      const data = await task();
      setter({ data, loading: false, error: null });
      return data;
    } catch (error) {
      setter({ data: null, loading: false, error: error instanceof Error ? error.message : 'Request failed' });
      return null;
    }
  }

  async function silentLoad<T>(setter: (value: LoadState<T>) => void, task: () => Promise<T>) {
    try {
      setter({ data: await task(), loading: false, error: null });
    } catch { /* keep existing data on background refresh error */ }
  }

  async function refreshCore(silent = false) {
    function fetch<T>(setter: (v: LoadState<T>) => void, task: () => Promise<T>) {
      return silent ? silentLoad(setter, task) : load(setter, task);
    }
    await Promise.all([
      fetch(setLive, () => fetchLive(session)),
      canRead ? fetch(setSpot, () => fetchSpot(session)) : Promise.resolve(null),
      canRead ? fetch(setPerp, () => fetchPerp(session)) : Promise.resolve(null),
      canRead ? fetch(setGlobal, () => fetchGlobal(session)) : Promise.resolve(null),
      canRead ? fetch(setEquity, () => fetchEquityCurve(session, 'global', '24h')) : Promise.resolve(null),
      canRead ? fetch(setDecisions, () => fetchAgentDecisions(session)) : Promise.resolve(null),
      canRead ? fetch(setAssetBreakdown, () => fetchAssetBreakdown(session, 'spot')) : Promise.resolve(null),
      canRead ? fetch(setOperationalStats, () => fetchOperationalStats(session)) : Promise.resolve(null),
      canRead ? fetch(setAgent, () => fetchAgentStatus(session)) : Promise.resolve(null),
      canRead ? fetch(setReady, () => fetchReady(session)) : Promise.resolve(null),
      canRead ? fetch(setHeartbeat, () => fetchHeartbeat(session)) : Promise.resolve(null),
      canRead ? fetch(setExecution, () => fetchExecutionStatus(session)) : Promise.resolve(null),
      canRead ? fetch(setWallets, () => fetchExecutionWallets(session)) : Promise.resolve(null),
      canRead ? fetch(setCoverage, () => fetchDataCoverage(session)) : Promise.resolve(null),
    ]);
  }

  async function refreshLogs() {
    if (!canAdmin) {
      setLogs({ data: [], loading: false, error: 'Admin token required' });
      return;
    }
    setLogs({ data: [], loading: true, error: null });
    try {
      const response = await fetchLogs(session, { limit: 250 });
      setLogs({ data: response.entries, loading: false, error: null });
    } catch (error) {
      setLogs({ data: [], loading: false, error: error instanceof Error ? error.message : 'Request failed' });
    }
  }

  async function refreshSettings() {
    if (!canRead) return;
    const response = await load(setSettings, () => fetchSettings(session));
    if (response) setSettingsDraft(response.settings);
  }

  async function submitSettings() {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setSettings, () => saveSettings(session, settingsDraft));
    if (response) {
      setSettingsDraft(response.settings);
      setNotice('Settings saved');
    }
  }

  async function runOnboarding() {
    if (!canAdmin) {
      setChecks({ data: [], loading: false, error: 'Admin token required' });
      return;
    }
    const response = await load(setChecks, () => validateOnboarding(session).then((payload) => payload.checks));
    if (response) setNotice('Onboarding validation completed');
  }

  async function updateKillSwitch(state: KillSwitchState) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setAgent, () => setKillSwitch(session, state));
    if (response) setNotice(`Kill switch set to ${state}`);
  }

  async function refreshMarkets() {
    if (!canRead) return;
    const response = await load(setMarkets, () => fetchMarkets(session, 100).then((payload) => payload.items));
    if (response) setNotice('Market snapshot updated');
  }

  async function refreshNotifPrefs() {
    if (!canRead) return;
    await load(setNotifPrefs, () => fetchNotificationPrefs(session));
  }

  async function toggleNotifPref(key: keyof NotificationPreferences) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const current = notifPrefs.data?.preferences;
    if (!current) return;
    const updated: NotificationPreferences = { ...current, [key]: !current[key] };
    const response = await load(setNotifPrefs, () => saveNotificationPrefs(session, updated));
    if (response) setNotice(`Notification preference "${key}" updated`);
  }

  async function updateSpotProvider(provider: string) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    await setSpotExecutionProvider(session, provider);
    await load(setWallets, () => fetchExecutionWallets(session));
    await load(setExecution, () => fetchExecutionStatus(session));
    setNotice(`Spot provider set to ${provider}`);
  }

  async function updatePerpProvider(provider: string) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    await setPerpExecutionProvider(session, provider);
    await load(setWallets, () => fetchExecutionWallets(session));
    await load(setExecution, () => fetchExecutionStatus(session));
    setNotice(`Perp provider set to ${provider}`);
  }

  async function updateRpcEndpoint(index: number) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setWallets, () => setRpcEndpoint(session, index));
    if (response) setNotice(`RPC endpoint ${index + 1} selected`);
  }

  async function updateExecutionNetwork(network: 'testnet' | 'mainnet') {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setWallets, () => setExecutionNetwork(session, network));
    if (response) {
      await load(setExecution, () => fetchExecutionStatus(session));
      setNotice(`BSC ${network} selected`);
    }
  }

  async function updateExecutionWallet(address: string) {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const response = await load(setWallets, () => setExecutionWallet(session, address));
    if (response) {
      await load(setExecution, () => fetchExecutionStatus(session));
      setNotice('Wallet selected');
    }
  }

  async function submitWalletAddress() {
    if (!canAdmin) {
      setNotice('Admin token required');
      return;
    }
    const address = walletDraft.trim();
    if (!address) return;
    const response = await load(setWallets, () => addExecutionWallet(session, address));
    if (response) {
      setWalletDraft('');
      await load(setExecution, () => fetchExecutionStatus(session));
      setNotice('Wallet added');
    }
  }

  const exportPayload = useMemo(
    () => ({
      generated_at: new Date().toISOString(),
      scope: 'step8_dashboard_export',
      spot: spot.data,
      global: global.data,
      analytics: {
        equity_curve: equity.data,
        decisions: decisions.data,
        asset_breakdown: assetBreakdown.data,
        operational_stats: operationalStats.data,
      },
      agent: agent.data,
      health: {
        live: live.data,
        ready: ready.data,
        heartbeat: heartbeat.data,
        execution: execution.data,
        wallets: wallets.data,
        data_coverage: coverage.data,
      },
    }),
    [
      agent.data,
      assetBreakdown.data,
      coverage.data,
      decisions.data,
      equity.data,
      execution.data,
      global.data,
      heartbeat.data,
      live.data,
      operationalStats.data,
      ready.data,
      spot.data,
      wallets.data,
    ],
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">CS</span>
          <div>
            <strong>CryptoSentinel</strong>
            <small>Judge Dashboard</small>
          </div>
        </div>
        <nav>
          {tabs.map((item) => (
            <button key={item.id} className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)}>
              {item.label}
            </button>
          ))}
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <h1>{tabs.find((item) => item.id === tab)?.label}</h1>
            <p>Unified desktop control surface for Spot ranking, agent state, health and safety controls.</p>
          </div>
          <div className="session-panel">
            <input
              aria-label="Backend URL"
              value={session.baseUrl}
              onChange={(event) => setSession((current) => ({ ...current, baseUrl: event.target.value }))}
            />
            <input
              aria-label="Read token"
              type="password"
              placeholder="Read token"
              value={session.readToken}
              onChange={(event) => setSession((current) => ({ ...current, readToken: event.target.value }))}
            />
            <input
              aria-label="Admin token"
              type="password"
              placeholder="Admin token"
              value={session.adminToken}
              onChange={(event) => setSession((current) => ({ ...current, adminToken: event.target.value }))}
            />
            <button onClick={() => void refreshCore(true)}>Refresh</button>
          </div>
        </header>

        {notice && (
          <button className="notice" onClick={() => setNotice('')}>
            {notice}
          </button>
        )}

        {tab === 'overview' && (
          <div className="grid overview-grid">
            <GlobalPanel global={global} />
            <SpotPanel spot={spot} />
            <PerpPanel perp={perp} />
            <HealthPanel live={live} ready={ready} heartbeat={heartbeat} execution={execution} coverage={coverage} />
            <KillSwitchPanel agent={agent} onSet={(state) => void updateKillSwitch(state)} canAdmin={canAdmin} />
          </div>
        )}
        {tab === 'spot' && <SpotPanel spot={spot} expanded />}
        {tab === 'perp' && <PerpPanel perp={perp} expanded />}
        {tab === 'global' && <GlobalPanel global={global} expanded />}
        {tab === 'analytics' && (
          <AnalyticsPanel
            equity={equity}
            decisions={decisions}
            assetBreakdown={assetBreakdown}
            operationalStats={operationalStats}
            onTradeDetail={(tradeId) => fetchTradeDetail(session, tradeId)}
          />
        )}
        {tab === 'health' && (
          <HealthPanel live={live} ready={ready} heartbeat={heartbeat} execution={execution} coverage={coverage} expanded />
        )}
        {tab === 'wallet' && (
          <WalletPanel
            wallets={wallets}
            spot={spot}
            canAdmin={canAdmin}
            onSpotProvider={(provider) => void updateSpotProvider(provider)}
            onPerpProvider={(provider) => void updatePerpProvider(provider)}
            onRpcEndpoint={(index) => void updateRpcEndpoint(index)}
            onNetwork={(network) => void updateExecutionNetwork(network)}
            walletDraft={walletDraft}
            onWalletDraft={setWalletDraft}
            onWallet={(address) => void updateExecutionWallet(address)}
            onAddWallet={() => void submitWalletAddress()}
          />
        )}
        {tab === 'logs' && <LogsPanel logs={logs} onRefresh={() => void refreshLogs()} canAdmin={canAdmin} />}
        {tab === 'settings' && (
          <div className="grid">
            <SettingsPanel
              settings={settings}
              draft={settingsDraft}
              setDraft={setSettingsDraft}
              onLoad={() => void refreshSettings()}
              onSave={() => void submitSettings()}
            />
            <NotificationPrefsPanel
              notifPrefs={notifPrefs}
              canAdmin={canAdmin}
              onLoad={() => void refreshNotifPrefs()}
              onToggle={(key) => void toggleNotifPref(key)}
            />
          </div>
        )}
        {tab === 'onboarding' && (
          <OnboardingPanel checks={checks} onValidate={() => void runOnboarding()} canAdmin={canAdmin} />
        )}
        {tab === 'markets' && (
          <MarketsPanel markets={markets} onRefresh={() => void refreshMarkets()} canRead={canRead} />
        )}
        {tab === 'export' && <ExportPanel payload={exportPayload} />}
      </main>
    </div>
  );
}

function Panel({
  title,
  children,
  action,
  className = '',
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-head">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function GlobalPanel({ global, expanded = false }: { global: LoadState<GlobalView>; expanded?: boolean }) {
  const data = global.data;
  return (
    <Panel title="Global Agent" className={expanded ? 'wide' : ''}>
      <StateBlock state={global} empty="Waiting for global agent data" />
      {data && (
        <>
          <div className="metric-grid">
            <Metric label="Equity" value={money(data.total_equity_usd)} />
            <Metric label="PnL" value={money(data.pnl_total_usd)} tone={Number(data.pnl_total_usd) >= 0 ? 'good' : 'bad'} />
            <Metric label="Aperto" value={money(data.unrealized_pnl_usd)} tone={Number(data.unrealized_pnl_usd) >= 0 ? 'good' : 'bad'} />
            <Metric label="Daily" value={money(data.daily_pnl_usd)} />
            <Metric label="Trades" value={String(data.trades_today)} />
            <Metric label="Drawdown" value={`${data.drawdown_pct}%`} tone="warn" />
            <Metric label="Exposure" value={`${data.exposure_pct}%`} />
            {expanded && (
              <Metric
                label="Sharpe"
                value={data.sharpe_status === 'ready' && data.sharpe_ratio ? data.sharpe_ratio : 'insufficient data'}
              />
            )}
          </div>
          {data.pnl_history.length === 0 ? (
            <Empty title="No PnL history" detail="Global tracking is ready and waiting for confirmed activity." />
          ) : (
            <Sparkline points={data.pnl_history.map((point) => Number(point.total_equity_usd))} />
          )}
        </>
      )}
    </Panel>
  );
}

function SpotPanel({ spot, expanded = false }: { spot: LoadState<SpotView>; expanded?: boolean }) {
  const data = spot.data;
  const [openTrade, setOpenTrade] = useState<string | null>(null);
  return (
    <Panel title="Spot Ranking View" className={expanded ? 'wide' : ''}>
      <StateBlock state={spot} empty="No Spot data loaded" />
      {data && (
        <>
          <div className="metric-grid">
            <Metric label="Realized" value={money(data.realized_pnl_usd)} />
            <Metric label="Unrealized" value={money(data.unrealized_pnl_usd)} />
            <Metric label="Win rate" value={`${data.win_rate_pct.toFixed(2)}%`} />
            <Metric label="Trades" value={String(data.trade_count)} />
          </div>
          {data.open_positions.length === 0 ? (
            <Empty title="No open Spot positions" detail="The agent has no active Spot exposure." />
          ) : (
            <Table
              columns={['Asset', 'Size', 'Entry', 'Current', 'Invested', 'Value', 'PnL', 'Status']}
              rows={data.open_positions.map((item) => {
                const invested = Number(item.entry_price) * Number(item.size);
                const value = invested + Number(item.pnl_unrealized);
                const pnl = Number(item.pnl_unrealized);
                return [
                  item.asset,
                  item.size,
                  fmtPrice(item.entry_price),
                  fmtPrice(item.current_price),
                  money(String(invested)),
                  <span className={value >= invested ? 'ok-text' : 'error-text'}>{money(String(value))}</span>,
                  <span className={pnl >= 0 ? 'ok-text' : 'error-text'}>{money(item.pnl_unrealized)}</span>,
                  item.status,
                ];
              })}
            />
          )}
          {expanded &&
            (data.history.length === 0 ? (
              <Empty title="No Spot trades today" detail="Trade history will appear after the first confirmed Spot order." />
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Side</th>
                      <th>Amount</th>
                      <th>Entry</th>
                      <th>Now/Exit</th>
                      <th>PnL</th>
                      <th>Status</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.history.map((item) => (
                      <tr key={item.trade_id} onClick={() => setOpenTrade(openTrade === item.trade_id ? null : item.trade_id)}>
                        <td>{item.asset}</td>
                        <td>{item.side}</td>
                        <td>{item.amount}</td>
                        <td>{fmtPrice(item.entry_price ?? item.price)}</td>
                        <td>{fmtPrice(item.current_or_exit_price ?? item.price)}</td>
                        <td className={Number(item.pnl_usd ?? 0) >= 0 ? 'ok-text' : 'error-text'}>
                          {item.pnl_usd ?? '+0.00'} / {item.pnl_pct ?? '+0.00'}%
                        </td>
                        <td>{item.status}</td>
                        <td>{shortDate(item.timestamp_utc)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {openTrade && <TradeDetailInline tradeId={openTrade} />}
              </div>
            ))}
        </>
      )}
    </Panel>
  );
}

function PerpPanel({ perp, expanded = false }: { perp: LoadState<PerpView>; expanded?: boolean }) {
  const data = perp.data;
  const [openTrade, setOpenTrade] = useState<string | null>(null);
  return (
    <Panel title="Perp Futures View" className={expanded ? 'wide' : ''}>
      <StateBlock state={perp} empty="No Perp data loaded" />
      {data && (
        <>
          <div className="metric-grid">
            <Metric label="Realized" value={money(data.realized_pnl_usd)} />
            <Metric label="Unrealized" value={money(data.unrealized_pnl_usd)} />
            <Metric label="Win rate" value={`${data.win_rate_pct.toFixed(2)}%`} />
            <Metric label="Trades" value={String(data.trade_count)} />
          </div>
          {data.open_positions.length === 0 ? (
            <Empty title="No open Perp positions" detail="The agent has no active Perp exposure." />
          ) : (
            <Table
              columns={['Asset', 'Side', 'Leverage', 'Entry', 'Now', 'Invested', 'Value', 'PnL', '%', 'Status']}
              rows={data.open_positions.map((item) => {
                const invested = Number(item.entry_price) * Number(item.size);
                const value = invested + Number(item.pnl_unrealized);
                const pnl = Number(item.pnl_unrealized);
                const pct = item.pnl_pct ?? '0.00';
                return [
                  item.asset,
                  item.side,
                  item.leverage ? `${item.leverage}x` : '-',
                  fmtPrice(item.entry_price),
                  fmtPrice(item.current_price),
                  money(String(invested)),
                  <span className={value >= invested ? 'ok-text' : 'error-text'}>{money(String(value))}</span>,
                  <span className={pnl >= 0 ? 'ok-text' : 'error-text'}>{money(item.pnl_unrealized)}</span>,
                  <span className={pnl >= 0 ? 'ok-text' : 'error-text'}>{pct}%</span>,
                  item.status,
                ];
              })}
            />
          )}
          {expanded &&
            (data.history.length === 0 ? (
              <Empty title="No Perp trades today" detail="Trade history will appear after the first confirmed Perp order." />
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Asset</th>
                      <th>Side</th>
                      <th>Leverage</th>
                      <th>Entry</th>
                      <th>Now/Exit</th>
                      <th>PnL</th>
                      <th>Status</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.history.map((item) => (
                      <tr key={item.trade_id} onClick={() => setOpenTrade(openTrade === item.trade_id ? null : item.trade_id)}>
                        <td>{item.asset}</td>
                        <td>{item.side}</td>
                        <td>{item.leverage ? `${item.leverage}x` : '-'}</td>
                        <td>{fmtPrice(item.entry_price ?? item.price)}</td>
                        <td>{fmtPrice(item.current_or_exit_price ?? item.price)}</td>
                        <td className={Number(item.pnl_usd ?? 0) >= 0 ? 'ok-text' : 'error-text'}>
                          {item.pnl_usd ?? '+0.00'} / {item.pnl_pct ?? '+0.00'}%
                        </td>
                        <td>{item.status}</td>
                        <td>{shortDate(item.timestamp_utc)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {openTrade && <TradeDetailInline tradeId={openTrade} />}
              </div>
            ))}
        </>
      )}
    </Panel>
  );
}

function AnalyticsPanel({
  equity,
  decisions,
  assetBreakdown,
  operationalStats,
  onTradeDetail,
}: {
  equity: LoadState<EquityCurveResponse>;
  decisions: LoadState<AgentDecisionResponse>;
  assetBreakdown: LoadState<AssetBreakdownResponse>;
  operationalStats: LoadState<OperationalStats>;
  onTradeDetail: (tradeId: string) => Promise<TradeDetail>;
}) {
  const [detail, setDetail] = useState<LoadState<TradeDetail>>(emptyState());
  const [filterSearch, setFilterSearch] = useState('');
  const [filterAsset, setFilterAsset] = useState('');
  const [filterMarket, setFilterMarket] = useState('');
  const [filterAction, setFilterAction] = useState('');
  const [filterExecution, setFilterExecution] = useState('');

  async function openDetail(tradeId?: string | null) {
    if (!tradeId) return;
    await loadDetail(setDetail, () => onTradeDetail(tradeId));
  }

  const allItems = decisions.data?.items ?? [];

  const uniqueAssets = useMemo(() => [...new Set(allItems.map(i => i.asset ?? '').filter(Boolean))].sort(), [allItems]);
  const uniqueMarkets = useMemo(() => [...new Set(allItems.map(i => i.market))].sort(), [allItems]);
  const uniqueActions = useMemo(() => [...new Set(allItems.map(i => i.action))].sort(), [allItems]);
  const uniqueExecutions = useMemo(() => [...new Set(allItems.map(i => i.execution_result ?? '').filter(Boolean))].sort(), [allItems]);

  const filtered = useMemo(() => {
    const q = filterSearch.toLowerCase();
    return allItems.filter(item => {
      if (filterAsset && (item.asset ?? '') !== filterAsset) return false;
      if (filterMarket && item.market !== filterMarket) return false;
      if (filterAction && item.action !== filterAction) return false;
      if (filterExecution && (item.execution_result ?? '') !== filterExecution) return false;
      if (q) {
        return (
          (item.asset ?? '').toLowerCase().includes(q) ||
          item.market.toLowerCase().includes(q) ||
          item.action.toLowerCase().includes(q) ||
          (item.execution_result ?? '').toLowerCase().includes(q) ||
          (item.reasoning ?? '').toLowerCase().includes(q)
        );
      }
      return true;
    });
  }, [allItems, filterSearch, filterAsset, filterMarket, filterAction, filterExecution]);

  const hasActiveFilter = filterSearch || filterAsset || filterMarket || filterAction || filterExecution;

  return (
    <div>
    <div className="grid overview-grid">
      <Panel title="Equity Curve" className="wide">
        <StateBlock state={equity} empty="No equity curve data" />
        {equity.data && equity.data.items.length > 0 ? (
          <>
            <Sparkline points={equity.data.items.map((point) => Number(point.equity_usd))} />
            <Table
              columns={['Time', 'Equity', 'PnL', 'ROI', 'Drawdown']}
              rows={equity.data.items.slice(-12).map((item) => [
                shortDate(item.timestamp_utc),
                money(item.equity_usd),
                item.pnl_usd,
                `${item.pnl_pct}%`,
                `${item.drawdown_pct}%`,
              ])}
            />
          </>
        ) : equity.data ? (
          <Empty title="No equity snapshots" detail="New clean dry-run snapshots will appear here." />
        ) : null}
      </Panel>

      <Panel title="Operational Stats">
        <StateBlock state={operationalStats} empty="No operational stats loaded" />
        {operationalStats.data && (
          <div className="metric-grid two">
            <Metric label="Uptime" value={`${operationalStats.data.uptime_pct}%`} />
            <Metric label="Degraded" value={String(operationalStats.data.degraded_count)} />
            <Metric label="Kill switch" value={operationalStats.data.last_kill_switch ?? 'none'} />
          </div>
        )}
      </Panel>

      <Panel title="Asset Breakdown" className="wide">
        <StateBlock state={assetBreakdown} empty="No asset breakdown data" />
        {assetBreakdown.data && assetBreakdown.data.items.length > 0 ? (
          <Table
            columns={['Asset', 'Trades', 'Win rate', 'PnL', 'ROI', 'Allocation']}
            rows={assetBreakdown.data.items.map((item) => [
              item.asset,
              String(item.trade_count),
              `${item.win_rate_pct}%`,
              item.pnl_usd,
              `${item.pnl_pct}%`,
              `${item.allocation_pct}%`,
            ])}
          />
        ) : assetBreakdown.data ? (
          <Empty title="No asset activity" detail="Breakdown starts after the first non-archived trade or position." />
        ) : null}
      </Panel>
    </div>

    <Panel title="Decision Log" className="wide">
        <StateBlock state={decisions} empty="No agent decisions loaded" />
        {decisions.data && (
          <>
            <div className="decision-filters">
              <input
                type="search"
                placeholder="Cerca…"
                value={filterSearch}
                onChange={e => setFilterSearch(e.target.value)}
              />
              <select value={filterAsset} onChange={e => setFilterAsset(e.target.value)}>
                <option value="">Tutti gli asset</option>
                {uniqueAssets.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
              <select value={filterMarket} onChange={e => setFilterMarket(e.target.value)}>
                <option value="">Tutti i mercati</option>
                {uniqueMarkets.map(m => <option key={m} value={m}>{m}</option>)}
              </select>
              <select value={filterAction} onChange={e => setFilterAction(e.target.value)}>
                <option value="">Tutte le azioni</option>
                {uniqueActions.map(a => <option key={a} value={a}>{a}</option>)}
              </select>
              <select value={filterExecution} onChange={e => setFilterExecution(e.target.value)}>
                <option value="">Tutti i risultati</option>
                {uniqueExecutions.map(e => <option key={e} value={e}>{e}</option>)}
              </select>
              {hasActiveFilter && (
                <button onClick={() => { setFilterSearch(''); setFilterAsset(''); setFilterMarket(''); setFilterAction(''); setFilterExecution(''); }}>
                  Reset
                </button>
              )}
              <span className="muted">{filtered.length} / {allItems.length}</span>
            </div>
            {filtered.length > 0 ? (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>Asset</th>
                      <th>Market</th>
                      <th>Quality</th>
                      <th>Action</th>
                      <th>Execution</th>
                      <th>Reasoning</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((item) => (
                      <tr key={item.decision_id} onClick={() => void openDetail(item.trade_id)}>
                        <td>{shortDate(item.timestamp_utc)}</td>
                        <td>{item.asset ?? '--'}</td>
                        <td>{item.market}</td>
                        <td>{item.signal_quality}</td>
                        <td>{item.action}</td>
                        <td>{item.execution_result ?? '--'}</td>
                        <td className="reasoning-cell">{item.reasoning ?? '--'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty title="Nessun risultato" detail={hasActiveFilter ? 'Nessuna decisione corrisponde ai filtri selezionati.' : 'Agent reasoning will appear after the first evaluation.'} />
            )}
          </>
        )}
        {detail.data && <TradeDetailCard detail={detail.data} />}
        {detail.error && <p className="error-text">{detail.error}</p>}
      </Panel>
    </div>
  );
}

function TradeDetailInline({ tradeId }: { tradeId: string }) {
  return <div className="trade-inline">Selected trade: <strong>{tradeId}</strong>. Open the Analytics decision row for full detail.</div>;
}

function TradeDetailCard({ detail }: { detail: TradeDetail }) {
  return (
    <div className="trade-detail">
      <div className="subhead">
        <h3>{detail.asset} {detail.market}</h3>
        <span>{detail.is_simulated ? 'simulated' : 'live'}</span>
      </div>
      <div className="metric-grid">
        <Metric label="Direction" value={detail.direction} />
        <Metric label="Entry" value={fmtPrice(detail.entry_price)} />
        <Metric label="Now/Exit" value={fmtPrice(detail.current_or_exit_price)} />
        <Metric label="PnL" value={`${detail.pnl_usd} / ${detail.pnl_pct}%`} tone={Number(detail.pnl_usd) >= 0 ? 'good' : 'bad'} />
        <Metric label="Exposure" value={money(detail.exposure_usd)} />
        <Metric label="Size" value={detail.size} />
      </div>
      <pre className="json-dump">{JSON.stringify(detail, null, 2)}</pre>
    </div>
  );
}

function HealthPanel({
  live,
  ready,
  heartbeat,
  execution,
  coverage,
  expanded = false,
}: {
  live: LoadState<HealthPayload>;
  ready: LoadState<HealthPayload>;
  heartbeat: LoadState<HealthPayload>;
  execution: LoadState<ExecutionStatus>;
  coverage: LoadState<DataCoverageResponse>;
  expanded?: boolean;
}) {
  const coverageItems = coverage.data?.items || [];
  const readyCount = coverageItems.filter((item) => item.status === 'ready').length;
  return (
    <Panel title="System Health" className={expanded ? 'wide' : ''}>
      <div className="status-list">
        <StatusRow label="Live" state={live} />
        <StatusRow label="Ready" state={ready} />
        <StatusRow label="Heartbeat" state={heartbeat} />
        <StatusRow label="Execution" state={execution} />
        <div className="status-row">
          <span>Data Coverage</span>
          <strong className={readyCount > 0 ? 'ok-text' : 'warn-text'}>
            {coverage.loading ? 'loading' : `${readyCount}/${coverageItems.length || 0} ready`}
          </strong>
        </div>
      </div>
      {expanded && (
        <>
          <DataCoveragePanel coverage={coverage} />
          <pre className="json-dump">
            {JSON.stringify({ live: live.data, ready: ready.data, heartbeat: heartbeat.data, execution: execution.data }, null, 2)}
          </pre>
        </>
      )}
    </Panel>
  );
}

function DataCoveragePanel({ coverage }: { coverage: LoadState<DataCoverageResponse> }) {
  const [marketFilter, setMarketFilter] = useState<'spot' | 'perp'>('spot');
  const [query, setQuery] = useState('');
  const rows = coverage.data?.items || [];
  const marketRows = rows.filter((item) => item.market === marketFilter);
  const normalizedQuery = query.trim().toLowerCase();
  const filteredRows = normalizedQuery
    ? marketRows.filter((item) =>
        `${item.asset} ${item.symbol} ${item.status} ${item.source}`.toLowerCase().includes(normalizedQuery),
      )
    : marketRows;
  const spotCount = rows.filter((item) => item.market === 'spot').length;
  const perpCount = rows.filter((item) => item.market === 'perp').length;
  return (
    <div className="coverage-block">
      <div className="subhead">
        <h3>Data Coverage</h3>
        <span>{coverage.data ? `Generated ${shortDate(coverage.data.generated_at)}` : 'Cache snapshot'}</span>
      </div>
      <StateBlock state={{ ...coverage, data: rows }} empty="No coverage data loaded" />
      {rows.length > 0 && (
        <>
          <div className="coverage-toolbar">
            <div className="segmented" role="tablist" aria-label="Data coverage market">
              <button className={marketFilter === 'spot' ? 'selected' : ''} onClick={() => setMarketFilter('spot')}>
                Spot <span>{spotCount}</span>
              </button>
              <button className={marketFilter === 'perp' ? 'selected' : ''} onClick={() => setMarketFilter('perp')}>
                Perp <span>{perpCount}</span>
              </button>
            </div>
            <input
              aria-label="Search token"
              placeholder="Search token"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          {filteredRows.length === 0 ? (
            <Empty title="No matching assets" detail="Adjust the search or switch market." />
          ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Asset</th>
                <th>Market</th>
                <th>Candles</th>
                <th>Status</th>
                <th>First</th>
                <th>Last</th>
                <th>Updated</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {filteredRows.map((item) => (
                <CoverageRow key={`${item.market}-${item.asset}`} item={item} />
              ))}
            </tbody>
          </table>
        </div>
          )}
        </>
      )}
    </div>
  );
}

function CoverageRow({ item }: { item: DataCoverageItem }) {
  return (
    <tr>
      <td>{item.asset}</td>
      <td>{item.market}</td>
      <td>{item.available_candles}/{item.required_candles}</td>
      <td><span className={`coverage-status ${item.status}`}>{item.status}</span></td>
      <td>{item.first_candle_at ? shortDate(item.first_candle_at) : '--'}</td>
      <td>{item.last_candle_at ? shortDate(item.last_candle_at) : '--'}</td>
      <td>{formatAge(item.age_seconds)}</td>
      <td>{item.source}</td>
    </tr>
  );
}

function WalletPanel({
  wallets,
  spot,
  canAdmin,
  onSpotProvider,
  onPerpProvider,
  onRpcEndpoint,
  onNetwork,
  walletDraft,
  onWalletDraft,
  onWallet,
  onAddWallet,
}: {
  wallets: LoadState<ExecutionWalletsResponse>;
  spot: LoadState<SpotView>;
  canAdmin: boolean;
  onSpotProvider: (provider: string) => void;
  onPerpProvider: (provider: string) => void;
  onRpcEndpoint: (index: number) => void;
  onNetwork: (network: 'testnet' | 'mainnet') => void;
  walletDraft: string;
  onWalletDraft: (value: string) => void;
  onWallet: (address: string) => void;
  onAddWallet: () => void;
}) {
  const [expandedCoin, setExpandedCoin] = useState<string | null>(null);
  const [txSearch, setTxSearch] = useState('');
  const [txType, setTxType] = useState<'all' | 'buy' | 'sell'>('all');
  const [modal, setModal] = useState<{ mode: 'send' | 'receive'; asset: string } | null>(null);

  const data = wallets.data;
  const spotData = spot.data;
  const activeWallet = data?.available_wallets?.find((w) => w.active) ?? data?.available_wallets?.[0];

  function toggleCoin(asset: string) {
    setExpandedCoin((prev) => (prev === asset ? null : asset));
    setTxSearch('');
    setTxType('all');
  }

  function coinColor(asset: string) {
    const palette = ['#7fa66a', '#6a9ab0', '#b07a6a', '#b0a06a', '#8a6ab0', '#6ab09a', '#a06a8a'];
    return palette[asset.charCodeAt(0) % palette.length];
  }

  function assetTrades(asset: string) {
    if (!spotData) return [];
    return spotData.history.filter(
      (t) =>
        t.asset === asset &&
        (txType === 'all' || t.side === txType) &&
        (txSearch === '' ||
          t.trade_id.toLowerCase().includes(txSearch.toLowerCase()) ||
          t.status.toLowerCase().includes(txSearch.toLowerCase())),
    );
  }

  return (
    <Panel title="Wallet" className="wide">
      <StateBlock state={wallets} empty="Nessun snapshot wallet caricato" />

      {/* ── HOLDINGS ─────────────────────────────────────────────── */}
      {data && (
        <div className="holdings-section">
          <div className="subhead">
            <h3>Portfolio Holdings</h3>
            <span>
              {spotData ? `${spotData.open_positions.length} posizioni aperte` : 'caricamento…'}
            </span>
          </div>

          {/* BNB card */}
          {activeWallet?.balance_bnb && (
            <div className={`coin-card${expandedCoin === 'BNB' ? ' expanded' : ''}`}>
              <button className="coin-header" onClick={() => toggleCoin('BNB')}>
                <span className="coin-avatar" style={{ background: '#f0b90b', color: '#10130f' }}>B</span>
                <div className="coin-meta">
                  <strong>BNB</strong>
                  <span>BNB Smart Chain · gas token</span>
                </div>
                <div className="coin-stat-group">
                  <strong>{parseFloat(activeWallet.balance_bnb).toFixed(4)} BNB</strong>
                  <span>{activeWallet.balance_status}</span>
                </div>
                <div className="coin-stat-group">
                  <strong className="muted">—</strong>
                  <span>PnL</span>
                </div>
                <div className="coin-stat-group">
                  <strong className="muted">—</strong>
                  <span>Entry / Now</span>
                </div>
                <div className="coin-actions" onClick={(e) => e.stopPropagation()}>
                  <button onClick={() => setModal({ mode: 'receive', asset: 'BNB' })}>↓ Ricevi</button>
                  <button onClick={() => setModal({ mode: 'send', asset: 'BNB' })}>↑ Invia</button>
                </div>
                <span className="coin-chevron">{expandedCoin === 'BNB' ? '▲' : '▼'}</span>
              </button>
              {expandedCoin === 'BNB' && (
                <div className="coin-detail">
                  <div className="wallet-detail-info">
                    <div><span>Indirizzo</span><code>{activeWallet.address}</code></div>
                    <div><span>Network</span><strong>{data.network} · Chain {data.chain_id}</strong></div>
                    <div><span>Bilancio</span><strong>{activeWallet.balance_bnb} BNB</strong></div>
                  </div>
                  <p className="hint" style={{ padding: '0 14px 14px' }}>Le transazioni BNB on-chain non sono tracciate in questo sistema.</p>
                </div>
              )}
            </div>
          )}

          {/* Spot position cards */}
          {spotData?.open_positions.map((pos) => {
            const pnl = parseFloat(pos.pnl_unrealized);
            const isPos = pnl >= 0;
            const entry = parseFloat(pos.entry_price);
            const current = parseFloat(pos.current_price);
            const size = parseFloat(pos.size);
            const invested = entry * size;
            const value = current * size;
            const isExp = expandedCoin === pos.asset;
            const trades = isExp ? assetTrades(pos.asset) : [];
            return (
              <div key={pos.position_id} className={`coin-card${isExp ? ' expanded' : ''}`}>
                <button className="coin-header" onClick={() => toggleCoin(pos.asset)}>
                  <span className="coin-avatar" style={{ background: coinColor(pos.asset) }}>
                    {pos.asset[0]}
                  </span>
                  <div className="coin-meta">
                    <strong>{pos.asset}/USDT</strong>
                    <span>Spot · {pos.status}</span>
                  </div>
                  <div className="coin-stat-group">
                    <strong>{size.toFixed(6)}</strong>
                    <span>Quantità</span>
                  </div>
                  <div className="coin-stat-group">
                    <strong>${invested.toLocaleString('en-US', { maximumFractionDigits: 2 })}</strong>
                    <span>Investito → ${value.toLocaleString('en-US', { maximumFractionDigits: 2 })}</span>
                  </div>
                  <div className="coin-stat-group">
                    <strong>${entry.toLocaleString()} → ${current.toLocaleString()}</strong>
                    <span>Entry → Now</span>
                  </div>
                  <div className={`coin-pnl-badge${isPos ? ' pos' : ' neg'}`}>
                    <strong>{isPos ? '+' : ''}{pnl.toFixed(2)} $</strong>
                    <span>{pos.pnl_pct ?? '—'}</span>
                  </div>
                  <div className="coin-actions" onClick={(e) => e.stopPropagation()}>
                    <button onClick={() => setModal({ mode: 'receive', asset: pos.asset })}>↓ Ricevi</button>
                    <button onClick={() => setModal({ mode: 'send', asset: pos.asset })}>↑ Invia</button>
                  </div>
                  <span className="coin-chevron">{isExp ? '▲' : '▼'}</span>
                </button>

                {isExp && (
                  <div className="coin-detail">
                    {/* position summary bar */}
                    <div className="wallet-detail-info">
                      <div><span>SL</span><strong>{pos.stop_loss ? `$${parseFloat(pos.stop_loss).toLocaleString()}` : '—'}</strong></div>
                      <div><span>TP1</span><strong>{pos.take_profit_1 ? `$${parseFloat(pos.take_profit_1).toLocaleString()}` : '—'}</strong></div>
                      <div><span>TP2</span><strong>{pos.take_profit_2 ? `$${parseFloat(pos.take_profit_2).toLocaleString()}` : '—'}</strong></div>
                      <div><span>Aperta il</span><strong>{new Date(pos.opened_at).toLocaleString('it-IT')}</strong></div>
                    </div>

                    {/* filter bar */}
                    <div className="tx-filter-bar">
                      <input
                        placeholder="Cerca per ID o stato…"
                        value={txSearch}
                        onChange={(e) => setTxSearch(e.target.value)}
                      />
                      <select value={txType} onChange={(e) => setTxType(e.target.value as 'all' | 'buy' | 'sell')}>
                        <option value="all">Tutti i tipi</option>
                        <option value="buy">Acquisto</option>
                        <option value="sell">Vendita / Chiusura</option>
                      </select>
                      {(txSearch || txType !== 'all') && (
                        <button onClick={() => { setTxSearch(''); setTxType('all'); }}>Reset</button>
                      )}
                      <span className="muted">{trades.length} transazioni</span>
                    </div>

                    {trades.length === 0 ? (
                      <p className="muted" style={{ padding: '0 14px 14px' }}>Nessuna transazione trovata per {pos.asset}.</p>
                    ) : (
                      <div className="table-wrap" style={{ margin: '0 14px 14px' }}>
                        <table>
                          <thead>
                            <tr>
                              <th>Data / Ora</th>
                              <th>Tipo</th>
                              <th>Quantità</th>
                              <th>Prezzo</th>
                              <th>Totale</th>
                              <th>PnL</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {trades.map((t) => {
                              const qty = parseFloat(t.amount ?? '0');
                              const px = parseFloat(t.price ?? '0');
                              const total = qty * px;
                              const tPnl = t.pnl_usd && t.pnl_usd !== '+0.00' ? parseFloat(t.pnl_usd) : null;
                              return (
                                <tr key={t.trade_id}>
                                  <td>{new Date(t.timestamp_utc).toLocaleString('it-IT')}</td>
                                  <td>
                                    <span className={t.side === 'buy' ? 'ok-text' : 'error-text'}>
                                      {t.side.toUpperCase()}
                                    </span>
                                  </td>
                                  <td>{qty.toFixed(6)}</td>
                                  <td>${px.toLocaleString('en-US', { maximumFractionDigits: 4 })}</td>
                                  <td>${total.toFixed(2)}</td>
                                  <td className={tPnl == null ? '' : tPnl >= 0 ? 'ok-text' : 'error-text'}>
                                    {tPnl == null ? '—' : `${tPnl >= 0 ? '+' : ''}${tPnl.toFixed(2)} $`}
                                  </td>
                                  <td>{t.status}</td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {spotData?.open_positions.length === 0 && !activeWallet?.balance_bnb && (
            <Empty title="Nessun asset" detail="Nessuna posizione spot aperta e nessun bilancio BNB disponibile." />
          )}
        </div>
      )}

      {/* ── CONFIGURAZIONE ───────────────────────────────────────── */}
      {data && (
        <>
          <div className="subhead" style={{ marginTop: 24 }}>
            <h3>Configurazione Esecuzione</h3>
          </div>
          <div className="provider-row">
            <label>
              <span>BSC chain</span>
              <select
                value={data.bsc_network || (data.chain_id === 56 ? 'mainnet' : 'testnet')}
                disabled={!canAdmin}
                onChange={(event) => onNetwork(event.target.value as 'testnet' | 'mainnet')}
              >
                <option value="testnet">Testnet</option>
                <option value="mainnet">Mainnet</option>
              </select>
            </label>
            <label>
              <span>Spot provider</span>
              <select value={data.spot_active_provider} disabled={!canAdmin} onChange={(event) => onSpotProvider(event.target.value)}>
                <option value="twak">TWAK</option>
                <option value="pancakeswap">PancakeSwap</option>
              </select>
            </label>
            <label>
              <span>Perp provider</span>
              <select value={data.perp_active_provider} disabled={!canAdmin} onChange={(event) => onPerpProvider(event.target.value)}>
                <option value="bnb_sdk">BNB SDK</option>
              </select>
            </label>
            <div className="network-chip">
              <span>{data.network}</span>
              <strong>Chain {data.chain_id}</strong>
            </div>
          </div>

          <div className="wallet-select-row">
            <label>
              <span>Wallet attivo</span>
              <select value={data.active_wallet_address || ''} disabled={!canAdmin} onChange={(event) => onWallet(event.target.value)}>
                {(data.available_wallets || []).map((w) => (
                  <option key={w.address} value={w.address}>{shortAddress(w.address)}</option>
                ))}
              </select>
            </label>
            <input
              aria-label="Nuovo indirizzo wallet"
              placeholder="Aggiungi indirizzo wallet"
              value={walletDraft}
              disabled={!canAdmin}
              onChange={(event) => onWalletDraft(event.target.value)}
            />
            <button onClick={onAddWallet} disabled={!canAdmin || !walletDraft.trim()}>Aggiungi</button>
          </div>
          {!canAdmin && <p className="hint">Token admin richiesto per modifiche provider e RPC.</p>}

          <div className="wallet-grid">
            {data.wallets.map((w) => (
              <button
                className="wallet-item"
                key={`${w.market}-${w.provider}`}
                onClick={() => w.address && void navigator.clipboard.writeText(w.address)}
                title={w.address ? 'Copia indirizzo' : 'Indirizzo non configurato'}
              >
                <span className="wallet-title">
                  <strong>{w.provider}</strong>
                  {w.active && <em>active</em>}
                </span>
                <span>{w.market.toUpperCase()} / {w.network}</span>
                <code>{w.address || 'non configurato'}</code>
                <span className={w.configured ? 'ok-text' : 'warn-text'}>
                  {w.configured ? 'configurato' : 'mancante'} / {w.balance_bnb ?? '--'} BNB
                </span>
              </button>
            ))}
          </div>

          <div className="subhead" style={{ marginTop: 20 }}>
            <h3>RPC Endpoints</h3>
          </div>
          <div className="rpc-list">
            {data.rpc_endpoints.map((ep) => (
              <div className="rpc-item" key={ep.index}>
                <div>
                  <strong>{ep.index + 1}. {ep.label}</strong>
                  <span>{ep.status} / {ep.latency_ms == null ? '--' : `${ep.latency_ms}ms`}</span>
                </div>
                {ep.active ? <span className="pill ok">active</span> : (
                  <button onClick={() => onRpcEndpoint(ep.index)} disabled={!canAdmin}>Usa</button>
                )}
              </div>
            ))}
          </div>
        </>
      )}

      {/* ── SEND / RECEIVE MODAL ─────────────────────────────────── */}
      {modal && (
        <div className="modal-overlay" onClick={() => setModal(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <strong>{modal.mode === 'send' ? '↑ Invia' : '↓ Ricevi'} {modal.asset}</strong>
              <button className="modal-close" onClick={() => setModal(null)}>✕</button>
            </div>
            {modal.mode === 'receive' ? (
              <div className="modal-body">
                <p className="muted">Invia {modal.asset} a questo indirizzo wallet:</p>
                <code className="address-display">{activeWallet?.address ?? 'Nessun wallet attivo'}</code>
                {activeWallet?.address && (
                  <div className="modal-actions">
                    <button
                      className="primary"
                      onClick={() => { void navigator.clipboard.writeText(activeWallet.address); setModal(null); }}
                    >
                      Copia indirizzo
                    </button>
                    <button onClick={() => setModal(null)}>Chiudi</button>
                  </div>
                )}
              </div>
            ) : (
              <div className="modal-body">
                <p className="muted">I trasferimenti vengono eseguiti via CLI o provider di esecuzione configurato.</p>
                <div className="send-info-grid">
                  <div><span>Asset</span><strong>{modal.asset}</strong></div>
                  <div><span>Wallet attivo</span><code>{activeWallet ? shortAddress(activeWallet.address) : '—'}</code></div>
                  <div><span>Network</span><strong>{data?.network ?? '—'} · Chain {data?.chain_id}</strong></div>
                  <div><span>Spot provider</span><strong>{data?.spot_active_provider ?? '—'}</strong></div>
                </div>
                <p className="hint">Usa il CLI <code>twak send</code> o la scheda Settings per eseguire trasferimenti manuali.</p>
                <div className="modal-actions">
                  <button onClick={() => setModal(null)}>Chiudi</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}

function KillSwitchPanel({
  agent,
  onSet,
  canAdmin,
}: {
  agent: LoadState<AgentStatus>;
  onSet: (state: KillSwitchState) => void;
  canAdmin: boolean;
}) {
  const current = agent.data?.kill_switch || 'unknown';
  return (
    <Panel title="Kill Switch" className="safety-panel">
      <div className={`switch-state ${current}`}>{String(current).replace('_', ' ')}</div>
      <div className="button-row">
        <button onClick={() => onSet('running')} disabled={!canAdmin}>Run</button>
        <button onClick={() => onSet('soft_stop')} disabled={!canAdmin}>Soft</button>
        <button className="danger" onClick={() => onSet('hard_stop')} disabled={!canAdmin}>Hard</button>
      </div>
      {!canAdmin && <p className="hint">Admin token required for safety controls.</p>}
    </Panel>
  );
}

function LogsPanel({ logs, onRefresh, canAdmin }: { logs: LoadState<LogEntry[]>; onRefresh: () => void; canAdmin: boolean }) {
  return (
    <Panel title="Log Viewer" action={<button onClick={onRefresh}>Load logs</button>} className="wide">
      {!canAdmin && <Empty title="Admin token required" detail="Logs are admin-only and redacted by the backend." />}
      <StateBlock state={logs} empty="No logs loaded" />
      {logs.data && logs.data.length > 0 && (
        <div className="log-list">
          {logs.data.map((entry, index) => (
            <div className="log-line" key={`${entry.timestamp || 'line'}-${index}`}>
              <span>{entry.timestamp ? shortDate(entry.timestamp) : '--'}</span>
              <strong>{entry.level || 'LOG'}</strong>
              <em>{entry.logger || 'backend'}</em>
              <p>{entry.message}</p>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function SettingsPanel({
  settings,
  draft,
  setDraft,
  onLoad,
  onSave,
}: {
  settings: LoadState<SettingsResponse>;
  draft: AgentSettings;
  setDraft: (value: AgentSettings) => void;
  onLoad: () => void;
  onSave: () => void;
}) {
  return (
    <Panel title="Agent Settings" action={<button onClick={onLoad}>Load</button>} className="wide">
      <StateBlock state={settings} empty="Load settings to edit the agent profile" />
      <div className="settings-grid">
        {settingFields.map((field) => (
          <label key={field}>
            <span>{field.replaceAll('_', ' ')}</span>
            <input
              value={String(draft[field] ?? '')}
              onChange={(event) => setDraft({ ...draft, [field]: coerceSetting(event.target.value, draft[field]) })}
            />
          </label>
        ))}
      </div>
      <button className="primary" onClick={onSave}>Save settings</button>
    </Panel>
  );
}

function OnboardingPanel({
  checks,
  onValidate,
  canAdmin,
}: {
  checks: LoadState<CredentialCheck[]>;
  onValidate: () => void;
  canAdmin: boolean;
}) {
  return (
    <Panel title="Onboarding" action={<button onClick={onValidate}>Validate</button>} className="wide">
      {!canAdmin && <Empty title="Admin token required" detail="Validation locks and checks runtime credentials without exposing values." />}
      <StateBlock state={checks} empty="No onboarding validation yet" />
      {checks.data && checks.data.length > 0 && (
        <div className="check-grid">
          {checks.data.map((check) => (
            <div className="check-item" key={check.name}>
              <strong>{check.name}</strong>
              <span className={check.configured ? 'pill ok' : 'pill warn'}>{check.status}</span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function MarketsPanel({
  markets,
  onRefresh,
  canRead,
}: {
  markets: LoadState<MarketAsset[]>;
  onRefresh: () => void;
  canRead: boolean;
}) {
  return (
    <Panel title="Price Monitor" action={<button onClick={onRefresh}>Load 100</button>} className="wide">
      {!canRead && <Empty title="Read token required" detail="Market monitoring uses the backend market-data provider." />}
      <StateBlock state={markets} empty="No price snapshot loaded" />
      {markets.data && markets.data.length > 0 && (
        <Table
          columns={['Asset', 'Symbol', 'Price', '24h', 'Volume']}
          rows={markets.data.map((item) => [
            item.name,
            item.symbol,
            item.current_price == null ? '--' : fmtPrice(item.current_price),
            item.price_change_percentage_24h == null ? '--' : `${item.price_change_percentage_24h.toFixed(2)}%`,
            item.total_volume == null ? '--' : compact(item.total_volume),
          ])}
        />
      )}
    </Panel>
  );
}

const NOTIF_PREF_LABELS: Record<keyof NotificationPreferences, string> = {
  spot_trades: 'Spot Trades',
  perp_trades: 'Perp Trades',
  risk_alerts: 'Risk Alerts',
  daily_summary: 'Daily Summary',
  critical: 'Critical Events',
};

function NotificationPrefsPanel({
  notifPrefs,
  canAdmin,
  onLoad,
  onToggle,
}: {
  notifPrefs: LoadState<NotificationPreferencesResponse>;
  canAdmin: boolean;
  onLoad: () => void;
  onToggle: (key: keyof NotificationPreferences) => void;
}) {
  const prefs = notifPrefs.data?.preferences ?? null;
  const source = notifPrefs.data?.source ?? null;
  return (
    <Panel title="Notification Preferences" action={<button onClick={onLoad}>Load</button>}>
      {!canAdmin && <p className="muted">Admin token required to change preferences.</p>}
      <StateBlock state={notifPrefs} empty="Load to see notification preferences" />
      {source && <p className="muted" style={{ marginBottom: '0.5rem' }}>Source: <strong>{source}</strong></p>}
      {prefs && (
        <div>
          {(Object.keys(NOTIF_PREF_LABELS) as Array<keyof NotificationPreferences>).map((key) => (
            <div key={key} className="status-row">
              <span>{NOTIF_PREF_LABELS[key]}</span>
              <button
                className={prefs[key] ? 'ok-text' : 'muted'}
                onClick={() => canAdmin && onToggle(key)}
                disabled={!canAdmin}
                style={{ cursor: canAdmin ? 'pointer' : 'default', background: 'none', border: 'none', fontWeight: 600 }}
              >
                {prefs[key] ? 'ON' : 'OFF'}
              </button>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

function ExportPanel({ payload }: { payload: unknown }) {
  const serialized = JSON.stringify(payload, null, 2);
  return (
    <Panel title="Strategy Export" className="wide">
      <div className="button-row">
        <button onClick={() => void navigator.clipboard.writeText(serialized)}>Copy JSON</button>
      </div>
      <pre className="json-dump">{serialized}</pre>
    </Panel>
  );
}

function StateBlock<T>({ state, empty }: { state: LoadState<T>; empty: string }) {
  if (state.loading) return <p className="muted">Loading...</p>;
  if (state.error) return <p className="error-text">{state.error}</p>;
  if (!state.data || (Array.isArray(state.data) && state.data.length === 0)) return <p className="muted">{empty}</p>;
  return null;
}

function StatusRow<T>({ label, state }: { label: string; state: LoadState<T> }) {
  const ok = !state.error && Boolean(state.data);
  return (
    <div className="status-row">
      <span>{label}</span>
      <strong className={ok ? 'ok-text' : 'warn-text'}>{state.loading ? 'loading' : ok ? 'ok' : 'check'}</strong>
    </div>
  );
}

function Metric({ label, value, tone = '' }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`metric ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      <span>{detail}</span>
    </div>
  );
}

function Table({ columns, rows }: { columns: string[]; rows: ReactNode[][] }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={index}>{row.map((cell, cellIndex) => <td key={`${index}-${cellIndex}`}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Sparkline({ points }: { points: number[] }) {
  const width = 420;
  const height = 120;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = Math.max(max - min, 1);
  const path = points
    .map((point, index) => {
      const x = (index / Math.max(points.length - 1, 1)) * width;
      const y = height - ((point - min) / range) * height;
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`;
    })
    .join(' ');
  return (
    <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Equity line">
      <path d={path} />
    </svg>
  );
}

function money(value: string | number) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return String(value);
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numeric);
}

function fmtPrice(value: string | number | null | undefined): string {
  const n = Number(value);
  if (!Number.isFinite(n) || value == null || value === '') return '$--';
  if (n === 0) return '$0';
  if (n >= 1000) return `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  if (n >= 1)    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  // Sub-$1: keep up to 8 significant digits, strip trailing zeros
  const sig = parseFloat(n.toPrecision(8));
  return `$${sig.toString()}`;
}

function compact(value: number) {
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(value);
}

function shortDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date);
}

function formatAge(value?: number | null) {
  if (value == null) return '--';
  if (value < 60) return `${Math.round(value)}s ago`;
  if (value < 3600) return `${Math.round(value / 60)}m ago`;
  return `${Math.round(value / 3600)}h ago`;
}

function shortAddress(value: string) {
  if (value.length <= 14) return value;
  return `${value.slice(0, 6)}...${value.slice(-6)}`;
}

function coerceSetting(value: string, previous: unknown) {
  if (typeof previous === 'boolean') return value === 'true';
  if (typeof previous === 'number') {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : previous;
  }
  return value;
}
