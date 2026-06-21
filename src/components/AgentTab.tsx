import { useCallback, useEffect, useMemo, useState, type FC } from 'react';
import {
  fetchAgentSettings,
  fetchAgentStatus,
  fetchAgentDecisions,
  fetchAssetBreakdown,
  fetchEquityCurve,
  fetchGlobalView,
  fetchMobileWallet,
  fetchPerpView,
  fetchSpotView,
  fetchTradeDetail,
  saveAgentSettings,
  setKillSwitch,
  validateOnboarding,
  type AgentDecisionResponse,
  type AgentMobileSettings,
  type AgentStatus,
  type AssetBreakdownResponse,
  type CredentialValidationResponse,
  type EquityCurveResponse,
  type GlobalView,
  type KillSwitchState,
  type MobileWalletView,
  type PerpView,
  type SpotView,
  type TradeDetail,
} from '../services/agentApi';
import { hapticLight } from '../utils/haptics';

type AgentPane = 'spot' | 'perp' | 'global' | 'coins' | 'setup';

const fmtUsd = (value: string | number | null | undefined) => {
  const n = Number(value ?? 0);
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const fmtPrice = (value: string | number | null | undefined): string => {
  const n = Number(value);
  if (!Number.isFinite(n) || value == null || value === '') return '$--';
  if (n === 0) return '$0';
  if (n >= 1000) return `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  if (n >= 1)    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  const sig = parseFloat(n.toPrecision(8));
  return `$${sig.toString()}`;
};

const fmtPct = (value: string | number | null | undefined) => {
  const n = Number(value ?? 0);
  return `${n.toFixed(2)}%`;
};

const defaultSettings: AgentMobileSettings = {
  mode: 'conservative',
  markets_enabled: 'both',
  execution_mode: 'dry_run',
  network: 'testnet',
  test_scaling_pct: 10,
  operating_hours_utc: '00:00-23:59',
  capital_per_trade_pct: 6,
  max_open_positions: 3,
  max_total_exposure_pct: 30,
  daily_loss_limit_pct: -8,
  drawdown_cap_pct: -15,
  min_pool_liquidity_usd: 50000,
  max_slippage_pct: 1,
  cooldown_minutes: 30,
  spot_confidence_threshold: 0.7,
  spot_volatility_trigger_pct: 3,
  spot_relative_volume_threshold: 1.8,
  spot_atr_stop_multiplier: 1.5,
  spot_trailing_distance_pct: 2,
  spot_partial_take_profit_pct: 50,
  spot_time_stop_hours: 6,
  perp_direction_mode: 'long_short',
  perp_default_leverage: 2,
  perp_dynamic_leverage_enabled: true,
  perp_value_area_pct: 68,
  perp_atr_stop_multiplier: 0.5,
  perp_time_stop_hours: 8,
};

const AGENT_REFRESH_MS = 45_000;

const EmptyState: FC<{ title: string; detail: string }> = ({ title, detail }) => (
  <div className="rounded-xl border border-dashed border-dark-600 bg-dark-800/60 px-4 py-8 text-center">
    <p className="text-sm font-semibold text-white">{title}</p>
    <p className="mt-1 text-xs text-gray-500 leading-relaxed">{detail}</p>
  </div>
);

const Stat: FC<{ label: string; value: string; tone?: 'good' | 'bad' | 'neutral' }> = ({ label, value, tone = 'neutral' }) => (
  <div className="rounded-lg bg-dark-800 px-3 py-2 min-w-0">
    <p className="text-[11px] uppercase text-gray-500 truncate">{label}</p>
    <p className={`text-sm font-bold tabular-nums truncate ${
      tone === 'good' ? 'text-accent-green' : tone === 'bad' ? 'text-accent-red' : 'text-white'
    }`}>{value}</p>
  </div>
);

const MiniSparkline: FC<{ values: number[] }> = ({ values }) => {
  if (values.length === 0) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = Math.max(max - min, 1);
  const points = values
    .map((value, index) => {
      const x = (index / Math.max(values.length - 1, 1)) * 100;
      const y = 42 - ((value - min) / range) * 40;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
  return (
    <svg className="h-16 w-full" viewBox="0 0 100 44" role="img" aria-label="Equity curve">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2.5" className="text-accent-blue" />
    </svg>
  );
};

const SegmentButton: FC<{ id: AgentPane; active: boolean; label: string; onClick: (id: AgentPane) => void }> = ({
  id, active, label, onClick,
}) => (
  <button
    onClick={() => { hapticLight(); onClick(id); }}
    className={`flex-1 rounded-lg px-2 py-2 text-xs font-semibold transition-colors ${
      active ? 'bg-accent-blue text-white' : 'bg-dark-800 text-gray-400'
    }`}
  >
    {label}
  </button>
);

const TokenToggle: FC<{
  symbol: string;
  selected: boolean;
  disabled: boolean;
  onToggle: (symbol: string) => void;
}> = ({ symbol, selected, disabled, onToggle }) => (
  <button
    type="button"
    disabled={disabled}
    onClick={() => { hapticLight(); onToggle(symbol); }}
    className={`flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-45 ${
      selected
        ? 'border-accent-yellow/50 bg-accent-yellow/10 text-accent-yellow'
        : 'border-dark-700 bg-dark-800 text-gray-300'
    }`}
  >
    <span className="min-w-0 truncate text-sm font-semibold">{symbol}</span>
    <span className={`h-2.5 w-2.5 flex-shrink-0 rounded-full ${selected ? 'bg-accent-yellow' : 'bg-gray-600'}`} />
  </button>
);

const NumberInput: FC<{
  label: string;
  value: number;
  step?: number;
  onChange: (value: number) => void;
}> = ({ label, value, step = 1, onChange }) => (
  <label className="block">
    <span className="text-xs text-gray-500">{label}</span>
    <input
      type="number"
      step={step}
      value={value}
      onChange={(event) => onChange(Number(event.target.value))}
      className="mt-1 w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
    />
  </label>
);

const SelectInput: FC<{
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  onChange: (value: string) => void;
}> = ({ label, value, options, onChange }) => (
  <label className="block">
    <span className="text-xs text-gray-500">{label}</span>
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="mt-1 w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
    >
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </label>
);

const MOBILE_PAGE = 8;

type SpotHistoryRow = NonNullable<SpotView['history']>[number];
type PerpHistoryRow = NonNullable<PerpView['history']>[number];

const TradeHistoryList: FC<{
  trades: SpotHistoryRow[] | PerpHistoryRow[];
  market: 'spot' | 'perp';
  onTrade: (id: string) => void;
}> = ({ trades, market, onTrade }) => {
  const [search, setSearch] = useState('');
  const [filterSide, setFilterSide] = useState('all');
  const [filterDir, setFilterDir] = useState('all');
  const [page, setPage] = useState(0);

  const sides = useMemo(() => ['all', ...Array.from(new Set(trades.map((t) => t.side)))], [trades]);
  const dirs = useMemo(
    () => (market === 'perp' ? ['all', ...Array.from(new Set((trades as PerpHistoryRow[]).map((t) => t.direction)))] : []),
    [trades, market],
  );

  const filtered = useMemo(() => {
    return (trades as (SpotHistoryRow & PerpHistoryRow)[]).filter((t) => {
      if (search && !t.asset.toLowerCase().includes(search.toLowerCase())) return false;
      if (filterSide !== 'all' && t.side !== filterSide) return false;
      if (market === 'perp' && filterDir !== 'all' && t.direction !== filterDir) return false;
      return true;
    });
  }, [trades, search, filterSide, filterDir, market]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / MOBILE_PAGE));
  const pg = Math.min(page, totalPages - 1);
  const pageItems = filtered.slice(pg * MOBILE_PAGE, (pg + 1) * MOBILE_PAGE);
  const resetPage = () => setPage(0);

  if (trades.length === 0) return null;

  return (
    <div className="space-y-2">
      {/* filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          value={search}
          onChange={(e) => { setSearch(e.target.value); resetPage(); }}
          placeholder="Asset…"
          className="w-24 flex-shrink-0 rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white outline-none"
        />
        <select
          value={filterSide}
          onChange={(e) => { setFilterSide(e.target.value); resetPage(); }}
          className="flex-1 min-w-0 rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white outline-none"
        >
          {sides.map((s) => <option key={s} value={s}>{s === 'all' ? 'All sides' : s}</option>)}
        </select>
        {market === 'perp' && (
          <select
            value={filterDir}
            onChange={(e) => { setFilterDir(e.target.value); resetPage(); }}
            className="flex-1 min-w-0 rounded-lg border border-dark-600 bg-dark-800 px-3 py-1.5 text-sm text-white outline-none"
          >
            {dirs.map((d) => <option key={d} value={d}>{d === 'all' ? 'Open+Close' : d}</option>)}
          </select>
        )}
      </div>

      {/* trade cards */}
      {pageItems.map((t) => {
        const pnl = Number(t.pnl_usd ?? 0);
        const isGood = pnl >= 0;
        const isClose = market === 'perp' ? t.direction === 'close' : t.side === 'sell';
        const label = market === 'perp'
          ? `${t.asset} ${t.side} ${t.leverage ? t.leverage + 'x' : ''} · ${t.direction}`
          : `${t.asset} ${t.side}`;
        return (
          <button
            key={t.trade_id}
            onClick={() => onTrade(t.trade_id)}
            className={`h-auto w-full rounded-xl border-0 px-4 py-3 text-left text-sm ${isClose ? 'bg-dark-700' : 'bg-dark-800'}`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-white">{label}</span>
              <span className={`font-bold ${isGood ? 'text-accent-green' : 'text-accent-red'}`}>
                {t.pnl_pct ?? '--'}%
              </span>
            </div>
            <div className="mt-2 grid grid-cols-3 gap-1 text-sm text-gray-400">
              <span>In {fmtPrice(t.entry_price ?? t.price)}</span>
              <span>Out {fmtPrice(t.current_or_exit_price ?? t.price)}</span>
              <span className={`text-right font-bold ${isGood ? 'text-accent-green' : 'text-accent-red'}`}>
                {isGood ? '+' : ''}{fmtUsd(t.pnl_usd ?? 0)}
              </span>
            </div>
            <div className="mt-1.5 flex items-center justify-between text-xs text-gray-500">
              <span className="uppercase tracking-wide">{t.status}</span>
              <span>
                {new Date(t.timestamp_utc).toLocaleString('it-IT', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
              </span>
            </div>
          </button>
        );
      })}

      {/* pager */}
      <div className="flex items-center justify-between text-sm text-gray-500 pt-1">
        <button
          onClick={() => setPage((p) => Math.max(0, p - 1))}
          disabled={pg === 0}
          className="px-4 py-1.5 rounded-lg bg-dark-800 border border-dark-600 disabled:opacity-30 text-sm"
        >‹ Prev</button>
        <span>{pg + 1}/{totalPages} ({filtered.length} trade)</span>
        <button
          onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
          disabled={pg >= totalPages - 1}
          className="px-4 py-1.5 rounded-lg bg-dark-800 border border-dark-600 disabled:opacity-30 text-sm"
        >Next ›</button>
      </div>
    </div>
  );
};

const SpotPane: FC<{ data: SpotView | null; onTrade: (tradeId: string) => void }> = ({ data, onTrade }) => {
  const hasPositions = (data?.open_positions.length ?? 0) > 0;
  const hasHistory = (data?.history.length ?? 0) > 0;
  const hasActivity = hasPositions || hasHistory || Number(data?.realized_pnl_usd ?? 0) !== 0 || Number(data?.unrealized_pnl_usd ?? 0) !== 0;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Spot PnL" value={fmtUsd(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0))} tone={Number(data?.unrealized_pnl_usd ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="Win rate" value={fmtPct(data?.win_rate_pct ?? 0)} />
        <Stat label="Open" value={String(data?.open_positions.length ?? 0)} />
        <Stat label="Trades" value={String(data?.trade_count ?? 0)} />
      </div>
      {!hasActivity && (
        <EmptyState title="In attesa di segnali spot" detail="Nessuna posizione aperta e nessun trade registrato." />
      )}
      {hasPositions ? (
        <div className="space-y-2">
          {data!.open_positions.map((position) => (
            <div key={position.position_id} className="rounded-xl bg-dark-800 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-white">{position.asset}</p>
                <p className={Number(position.pnl_unrealized) >= 0 ? 'text-accent-green text-sm font-bold' : 'text-accent-red text-sm font-bold'}>
                  {fmtUsd(position.pnl_unrealized)} / {position.pnl_pct ?? '+0.00'}%
                </p>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Entry {fmtPrice(position.entry_price)}</span>
                <span>Now {fmtPrice(position.current_price)}</span>
                <span>{position.status}</span>
              </div>
            </div>
          ))}
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessuna posizione aperta" detail="Lo Spot e' pronto: le nuove entrate appariranno qui." />
      )}
      {hasHistory ? (
        <div className="space-y-2">
          <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Spot history</h3>
          <TradeHistoryList trades={data!.history} market="spot" onTrade={onTrade} />
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessun trade oggi" detail="Lo storico si popola quando l'agente prepara o chiude operazioni spot." />
      )}
    </div>
  );
};

const PerpPane: FC<{ data: PerpView | null; onTrade: (tradeId: string) => void }> = ({ data, onTrade }) => {
  const hasPositions = (data?.open_positions.length ?? 0) > 0;
  const hasHistory = (data?.history.length ?? 0) > 0;
  const hasActivity = hasPositions || hasHistory || Number(data?.realized_pnl_usd ?? 0) !== 0 || Number(data?.unrealized_pnl_usd ?? 0) !== 0;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Perp PnL" value={fmtUsd(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0))} tone={Number(data?.unrealized_pnl_usd ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="Win rate" value={fmtPct(data?.win_rate_pct ?? 0)} />
        <Stat label="Open" value={String(data?.open_positions.length ?? 0)} />
        <Stat label="Trades" value={String(data?.trade_count ?? 0)} />
      </div>
      {!hasActivity && (
        <EmptyState title="In attesa di segnali perp" detail="Nessuna posizione aperta e nessun trade registrato." />
      )}
      {hasPositions ? (
        <div className="space-y-2">
          {data!.open_positions.map((position) => (
            <div key={position.position_id} className="rounded-xl bg-dark-800 px-4 py-3">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-white">{position.asset} {position.side}</p>
                <span className="rounded-full bg-dark-700 px-2 py-1 text-xs text-accent-blue">{position.leverage}x</span>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-500">
                <span>PnL {fmtUsd(position.pnl_unrealized)} / {position.pnl_pct ?? '+0.00'}%</span>
                <span>Liq {position.liquidation_price ? fmtPrice(position.liquidation_price) : '-'}</span>
                <span>Funding {position.funding_rate ? fmtPct(Number(position.funding_rate) * 100) : '-'}</span>
                <span>{position.status}</span>
              </div>
            </div>
          ))}
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessuna posizione aperta" detail="Le posizioni perp long/short appariranno qui." />
      )}
      {hasHistory ? (
        <div className="space-y-2">
          <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Perp history</h3>
          <TradeHistoryList trades={data!.history} market="perp" onTrade={onTrade} />
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessun trade perp" detail="Lo storico perp si popola dopo le prime operazioni." />
      )}
    </div>
  );
};

const GlobalPane: FC<{
  data: GlobalView | null;
  status: AgentStatus | null;
  equity: EquityCurveResponse | null;
  decisions: AgentDecisionResponse | null;
  assetBreakdown: AssetBreakdownResponse | null;
}> = ({ data, status, equity, decisions, assetBreakdown }) => {
  const hasHistory = (data?.pnl_history.length ?? 0) > 0;
  const hasPortfolio = Number(data?.total_equity_usd ?? 0) > 0 || Number(data?.initial_equity_usd ?? 0) > 0;
  const hasTradesToday = Number(data?.trades_today ?? 0) > 0;
  const sortedAssets = [...(assetBreakdown?.items ?? [])].sort((a, b) => Number(b.pnl_usd) - Number(a.pnl_usd));
  const bestAssets = sortedAssets.slice(0, 3);
  const worstAssets = sortedAssets.slice(-3).reverse();

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Equity" value={fmtUsd(data?.total_equity_usd)} />
        <Stat label="Total PnL" value={fmtUsd(data?.pnl_total_usd)} tone={Number(data?.pnl_total_usd ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="Drawdown" value={fmtPct(data?.drawdown_pct)} tone={Number(data?.drawdown_pct ?? 0) < -10 ? 'bad' : 'neutral'} />
        <Stat label="Exposure" value={fmtPct(data?.exposure_pct)} />
        <Stat label="Trades UTC" value={String(data?.trades_today ?? 0)} />
        <Stat label="Kill switch" value={status?.kill_switch ?? data?.agent_status ?? 'idle'} />
      </div>
      {!hasPortfolio && !hasHistory && (
        <EmptyState title="In attesa dello stato globale" detail="Equity, drawdown ed esposizione saranno visibili al primo snapshot." />
      )}
      {!hasTradesToday && (
        <EmptyState title="Nessun trade oggi" detail="Il contatore UTC si aggiorna dopo il primo trade valido." />
      )}
      {hasHistory ? (
        <div className="rounded-xl bg-dark-800 px-4 py-3">
          <h3 className="text-xs font-semibold uppercase text-gray-500">Equity snapshots</h3>
          <MiniSparkline values={(equity?.items ?? data!.pnl_history).slice(-24).map((point) => Number('equity_usd' in point ? point.equity_usd : point.total_equity_usd))} />
        </div>
      ) : hasPortfolio && (
        <EmptyState title="Nessuno storico PnL" detail="La curva equity apparira' dopo i prossimi snapshot." />
      )}
      <div className="grid grid-cols-2 gap-2">
        <AssetRank title="Top asset" items={bestAssets} />
        <AssetRank title="Worst asset" items={worstAssets} />
      </div>
      <section className="space-y-2">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Ultime decisioni</h3>
        {(decisions?.items.length ?? 0) > 0 ? decisions!.items.slice(0, 3).map((item) => (
          <div key={item.decision_id} className="flex items-center justify-between rounded-lg bg-dark-800 px-3 py-2 text-xs">
            <span className="text-white">{item.action} {item.asset ?? '--'}</span>
            <span className="text-gray-500">{new Date(item.timestamp_utc).toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
        )) : (
          <EmptyState title="Nessuna decisione" detail="Le ultime valutazioni AI appariranno qui." />
        )}
      </section>
    </div>
  );
};

const AssetRank: FC<{ title: string; items: AssetBreakdownResponse['items'] }> = ({ title, items }) => (
  <section className="rounded-xl bg-dark-800 px-3 py-3">
    <h3 className="text-xs font-semibold uppercase text-gray-500">{title}</h3>
    <div className="mt-2 space-y-1.5">
      {items.length > 0 ? items.map((item) => (
        <div key={`${title}-${item.asset}`} className="flex items-center justify-between gap-2 text-xs">
          <span className="text-white">{item.asset}</span>
          <span className={Number(item.pnl_usd) >= 0 ? 'text-accent-green' : 'text-accent-red'}>{item.pnl_pct}%</span>
        </div>
      )) : <p className="text-xs text-gray-500">--</p>}
    </div>
  </section>
);

const CoinsPane: FC<{
  eligibleTokens: string[];
  selectedAiSymbols: Set<string>;
  adminToken: string;
  saving: boolean;
  error: string;
  onToggle: (symbol: string) => void;
}> = ({ eligibleTokens, selectedAiSymbols, adminToken, saving, error, onToggle }) => {
  const [query, setQuery] = useState('');
  const normalizedQuery = query.trim().toUpperCase();
  const selectedTokens = eligibleTokens.filter((symbol) => selectedAiSymbols.has(symbol.toUpperCase()));
  const filteredTokens = eligibleTokens.filter((symbol) => symbol.toUpperCase().includes(normalizedQuery));
  const disabled = !adminToken || saving;

  return (
    <div className="space-y-4">
      <section className="rounded-xl bg-dark-800 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-white">Agent coins</h3>
            <p className="mt-0.5 truncate text-xs text-gray-500">Tradabili {eligibleTokens.length} - attive {selectedTokens.length}</p>
          </div>
          <span className="rounded-full bg-accent-yellow/15 px-2 py-1 text-xs font-semibold text-accent-yellow">
            {selectedTokens.length}
          </span>
        </div>
        {!adminToken && <p className="mt-3 rounded-lg bg-dark-900 px-3 py-2 text-xs text-gray-500">Inserisci admin token in Setup per modificare.</p>}
        {error && <p className="mt-3 rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{error}</p>}
      </section>

      <section className="space-y-2">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Selezionate</h3>
        {selectedTokens.length > 0 ? (
          <div className="grid grid-cols-2 gap-2">
            {selectedTokens.map((symbol) => (
              <TokenToggle key={`selected-${symbol}`} symbol={symbol} selected disabled={disabled} onToggle={onToggle} />
            ))}
          </div>
        ) : (
          <EmptyState title="Nessuna coin attiva" detail="Seleziona una coin tradabile per passarla all'agente." />
        )}
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Tradabili</h3>
          {saving && <span className="text-xs text-accent-yellow">Saving</span>}
        </div>
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search token"
          className="w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
        />
        <div className="grid grid-cols-2 gap-2">
          {filteredTokens.map((symbol) => (
            <TokenToggle
              key={symbol}
              symbol={symbol}
              selected={selectedAiSymbols.has(symbol.toUpperCase())}
              disabled={disabled}
              onToggle={onToggle}
            />
          ))}
        </div>
        {filteredTokens.length === 0 && (
          <EmptyState title="Nessun token trovato" detail="La ricerca filtra solo l'universo eligible." />
        )}
      </section>
    </div>
  );
};

const SetupPane: FC<{
  settings: AgentMobileSettings;
  onSettings: (settings: AgentMobileSettings) => void;
  adminToken: string;
  onAdminToken: (value: string) => void;
  wallet: MobileWalletView | null;
  validation: CredentialValidationResponse | null;
  agentStatus: AgentStatus | null;
  saving: boolean;
  actionError: string;
  onSave: () => void;
  onValidate: () => void;
  onKill: (state: KillSwitchState) => void;
}> = ({
  settings,
  onSettings,
  adminToken,
  onAdminToken,
  wallet,
  validation,
  agentStatus,
  saving,
  actionError,
  onSave,
  onValidate,
  onKill,
}) => {
  const patch = (partial: Partial<AgentMobileSettings>) => onSettings({ ...settings, ...partial });
  const [copiedAddress, setCopiedAddress] = useState<string | null>(null);
  const copyAddress = async (address: string) => {
    try {
      await navigator.clipboard.writeText(address);
    } catch {
      const el = document.createElement('textarea');
      el.value = address;
      document.body.appendChild(el);
      el.select();
      document.execCommand('copy');
      document.body.removeChild(el);
    }
    setCopiedAddress(address);
    setTimeout(() => setCopiedAddress(null), 1600);
  };

  return (
    <div className="space-y-4">
      <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-3">
        <h3 className="text-sm font-semibold text-white">Admin session</h3>
        <input
          type="password"
          value={adminToken}
          onChange={(event) => onAdminToken(event.target.value)}
          placeholder="Admin token"
          autoComplete="off"
          className="w-full rounded-lg border border-dark-600 bg-dark-900 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
        />
      </section>

      <section className="rounded-xl border border-accent-red/20 bg-dark-800 px-4 py-4 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-white">Kill switch</h3>
            <p className="mt-0.5 text-xs text-gray-500 truncate">Soft stop blocca nuove entrate. Hard stop ferma tutto.</p>
          </div>
          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${
            agentStatus?.kill_switch === 'hard_stop'
              ? 'bg-accent-red/20 text-accent-red'
              : agentStatus?.kill_switch === 'soft_stop' || agentStatus?.kill_switch === 'degraded'
                ? 'bg-accent-yellow/20 text-accent-yellow'
                : 'bg-accent-green/15 text-accent-green'
          }`}>
            {agentStatus?.kill_switch ?? 'unknown'}
          </span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <button onClick={() => onKill('running')} disabled={!adminToken || saving} className="rounded-lg bg-dark-700 px-2 py-2.5 text-xs font-semibold text-gray-300 disabled:opacity-40">Run</button>
          <button onClick={() => onKill('soft_stop')} disabled={!adminToken || saving} className="rounded-lg bg-accent-yellow/20 px-2 py-2.5 text-xs font-semibold text-accent-yellow disabled:opacity-40">Soft</button>
          <button onClick={() => onKill('hard_stop')} disabled={!adminToken || saving} className="rounded-lg bg-accent-red/20 px-2 py-2.5 text-xs font-semibold text-accent-red disabled:opacity-40">Hard</button>
        </div>
        {!adminToken && <p className="text-xs text-gray-600">Richiede admin token di sessione.</p>}
      </section>

      <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-3">
        <h3 className="text-sm font-semibold text-white">Onboarding</h3>
        <button onClick={onValidate} disabled={!adminToken || saving} className="w-full rounded-lg bg-accent-blue px-3 py-2 text-sm font-semibold text-white disabled:opacity-40">
          {saving ? 'Checking...' : 'Validate'}
        </button>
        {validation && (
          <div className="grid grid-cols-2 gap-2">
            {validation.checks.map((check) => (
              <div key={check.name} className="rounded-lg bg-dark-900 px-3 py-2">
                <p className="text-xs font-semibold text-white">{check.name}</p>
                <p className={check.configured ? 'text-xs text-accent-green' : 'text-xs text-accent-red'}>{check.status}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-3">
        <h3 className="text-sm font-semibold text-white">Wallet</h3>
        {wallet?.networks.map((network) => (
          <div key={network.network} className="rounded-lg bg-dark-900 px-3 py-3 space-y-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-xs font-semibold text-white">{network.network}</p>
              <span className={network.configured ? 'text-xs text-accent-green' : 'text-xs text-gray-500'}>{network.configured ? 'ready' : 'missing'}</span>
            </div>
            <button
              type="button"
              disabled={!network.address}
              onClick={() => network.address && copyAddress(network.address)}
              className="w-full rounded-lg bg-dark-800 px-3 py-2 text-left disabled:opacity-50"
            >
              <span className="block text-[11px] uppercase text-gray-600">{network.role}</span>
              <span className="mt-1 block break-all font-mono text-xs leading-relaxed text-gray-300">
                {network.address ?? 'Wallet not configured'}
              </span>
              {network.address && (
                <span className="mt-1 block text-[11px] text-accent-blue">
                  {copiedAddress === network.address ? 'Copied' : 'Tap to copy'}
                </span>
              )}
            </button>
            {network.balances.length > 0 ? (
              <div className="space-y-1.5">
                {network.balances.map((balance) => (
                  <div key={`${network.network}-${balance.asset}`} className="flex items-center justify-between rounded-lg bg-dark-800 px-3 py-2">
                    <div>
                      <p className="text-sm font-semibold text-white">{balance.asset}</p>
                      <p className="text-[11px] text-gray-600">{balance.source}</p>
                    </div>
                    <p className="font-mono text-sm font-bold text-accent-green">{balance.balance}</p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-dark-700 px-3 py-2 text-xs text-gray-500">
                {network.balance_status === 'rpc_not_configured'
                  ? 'Balance RPC not configured.'
                  : network.balance_status === 'unavailable'
                    ? 'Balance unavailable.'
                    : 'No asset balance greater than 0.'}
              </p>
            )}
          </div>
        ))}
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">General</h3>
        <div className="grid grid-cols-2 gap-3">
          <SelectInput label="Mode" value={settings.mode} onChange={(mode) => patch({ mode })} options={[
            { value: 'conservative', label: 'Conservative' },
            { value: 'semi_autonomous', label: 'Semi-auto' },
            { value: 'full_autonomous', label: 'Full auto' },
          ]} />
          <SelectInput label="Market" value={settings.markets_enabled} onChange={(markets_enabled) => patch({ markets_enabled })} options={[
            { value: 'spot', label: 'Spot' },
            { value: 'perp', label: 'Perp' },
            { value: 'both', label: 'Both' },
          ]} />
          <SelectInput label="Execution" value={settings.execution_mode} onChange={(execution_mode) => patch({ execution_mode })} options={[
            { value: 'dry_run', label: 'Dry-run' },
            { value: 'live', label: 'Live' },
          ]} />
          <NumberInput label="Test scaling %" value={settings.test_scaling_pct} onChange={(test_scaling_pct) => patch({ test_scaling_pct })} />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Risk</h3>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Size %" value={settings.capital_per_trade_pct} onChange={(capital_per_trade_pct) => patch({ capital_per_trade_pct })} />
          <NumberInput label="Max positions" value={settings.max_open_positions} onChange={(max_open_positions) => patch({ max_open_positions })} />
          <NumberInput label="Exposure %" value={settings.max_total_exposure_pct} onChange={(max_total_exposure_pct) => patch({ max_total_exposure_pct })} />
          <NumberInput label="Daily loss %" value={settings.daily_loss_limit_pct} onChange={(daily_loss_limit_pct) => patch({ daily_loss_limit_pct })} />
          <NumberInput label="Slippage %" value={settings.max_slippage_pct} step={0.1} onChange={(max_slippage_pct) => patch({ max_slippage_pct })} />
          <NumberInput label="Cooldown min" value={settings.cooldown_minutes} onChange={(cooldown_minutes) => patch({ cooldown_minutes })} />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Spot</h3>
        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Confidence" value={settings.spot_confidence_threshold} step={0.01} onChange={(spot_confidence_threshold) => patch({ spot_confidence_threshold })} />
          <NumberInput label="Vol trigger %" value={settings.spot_volatility_trigger_pct} onChange={(spot_volatility_trigger_pct) => patch({ spot_volatility_trigger_pct })} />
          <NumberInput label="Rel volume" value={settings.spot_relative_volume_threshold} step={0.1} onChange={(spot_relative_volume_threshold) => patch({ spot_relative_volume_threshold })} />
          <NumberInput label="ATR stop" value={settings.spot_atr_stop_multiplier} step={0.1} onChange={(spot_atr_stop_multiplier) => patch({ spot_atr_stop_multiplier })} />
        </div>
      </section>

      <section className="space-y-3">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Perp</h3>
        <div className="grid grid-cols-2 gap-3">
          <SelectInput label="Direction" value={settings.perp_direction_mode} onChange={(perp_direction_mode) => patch({ perp_direction_mode })} options={[
            { value: 'long_only', label: 'Long' },
            { value: 'short_only', label: 'Short' },
            { value: 'long_short', label: 'Both' },
          ]} />
          <NumberInput label="Leverage" value={settings.perp_default_leverage} onChange={(perp_default_leverage) => patch({ perp_default_leverage })} />
          <NumberInput label="Value area %" value={settings.perp_value_area_pct} onChange={(perp_value_area_pct) => patch({ perp_value_area_pct })} />
          <NumberInput label="ATR stop" value={settings.perp_atr_stop_multiplier} step={0.1} onChange={(perp_atr_stop_multiplier) => patch({ perp_atr_stop_multiplier })} />
        </div>
      </section>

      <button onClick={onSave} disabled={!adminToken || saving} className="w-full rounded-lg bg-accent-blue px-3 py-3 text-sm font-semibold text-white disabled:opacity-40">
        {saving ? 'Saving...' : 'Save agent settings'}
      </button>
      {actionError && <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{actionError}</p>}
    </div>
  );
};

const TradeDetailScreen: FC<{ detail: TradeDetail; onBack: () => void }> = ({ detail, onBack }) => (
  <div className="space-y-4">
    <button onClick={onBack} className="rounded-lg bg-dark-800 px-3 py-2 text-sm font-semibold text-gray-300">
      Back
    </button>
    <section className="rounded-xl bg-dark-800 px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-bold text-white">{detail.asset}</h3>
          <p className="text-xs text-gray-500">{detail.market} / {detail.direction}</p>
        </div>
        <span className={detail.is_simulated ? 'rounded-full bg-accent-yellow/15 px-2 py-1 text-xs text-accent-yellow' : 'rounded-full bg-accent-green/15 px-2 py-1 text-xs text-accent-green'}>
          {detail.is_simulated ? 'dry-run' : 'live'}
        </span>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-2">
        <Stat label="PnL" value={`${detail.pnl_usd} / ${detail.pnl_pct}%`} tone={Number(detail.pnl_usd) >= 0 ? 'good' : 'bad'} />
        <Stat label="Exposure" value={fmtUsd(detail.exposure_usd)} />
        <Stat label="Entry" value={fmtPrice(detail.entry_price)} />
        <Stat label="Now/Exit" value={fmtPrice(detail.current_or_exit_price)} />
        <Stat label="Size" value={detail.size} />
        <Stat label="Leverage" value={detail.leverage ? `${detail.leverage.toFixed(2)}x` : '-'} />
      </div>
    </section>
    <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
      <h3 className="text-sm font-semibold text-white">Risk levels</h3>
      {[
        ['Stop loss', detail.stop_loss],
        ['Take profit 1', detail.take_profit_1],
        ['Take profit 2', detail.take_profit_2],
        ['Trailing stop', detail.trailing_stop],
      ].map(([label, value]) => (
        <div key={label} className="flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2 text-xs">
          <span className="text-gray-500">{label}</span>
          <span className="text-white">{value ? fmtUsd(value) : '-'}</span>
        </div>
      ))}
    </section>
    <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
      <h3 className="text-sm font-semibold text-white">Timeline</h3>
      <p className="text-xs text-gray-500">Open {new Date(detail.opened_at).toLocaleString('it-IT')}</p>
      <p className="text-xs text-gray-500">Close {detail.closed_at ? new Date(detail.closed_at).toLocaleString('it-IT') : '-'}</p>
      <p className="text-xs text-gray-500">Reason {detail.close_reason ?? '-'}</p>
    </section>
  </div>
);

interface AgentTabProps {
  adminToken: string;
  onAdminToken: (value: string) => void;
  eligibleTokens: string[];
  selectedAiSymbols: Set<string>;
  watchlistSaving: boolean;
  watchlistError: string;
  onToggleAiSymbol: (symbol: string) => void;
}

const AgentTab: FC<AgentTabProps> = ({
  adminToken,
  onAdminToken,
  eligibleTokens,
  selectedAiSymbols,
  watchlistSaving,
  watchlistError,
  onToggleAiSymbol,
}) => {
  const [pane, setPane] = useState<AgentPane>('spot');
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [spot, setSpot] = useState<SpotView | null>(null);
  const [perp, setPerp] = useState<PerpView | null>(null);
  const [global, setGlobal] = useState<GlobalView | null>(null);
  const [equity, setEquity] = useState<EquityCurveResponse | null>(null);
  const [decisions, setDecisions] = useState<AgentDecisionResponse | null>(null);
  const [assetBreakdown, setAssetBreakdown] = useState<AssetBreakdownResponse | null>(null);
  const [tradeDetail, setTradeDetail] = useState<TradeDetail | null>(null);
  const [settings, setSettings] = useState<AgentMobileSettings>(defaultSettings);
  const [wallet, setWallet] = useState<MobileWalletView | null>(null);
  const [validation, setValidation] = useState<CredentialValidationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [statusData, spotData, perpData, globalData, settingsData, walletData, equityData, decisionsData, breakdownData] = await Promise.all([
        fetchAgentStatus(),
        fetchSpotView(),
        fetchPerpView(),
        fetchGlobalView(),
        fetchAgentSettings(),
        fetchMobileWallet(),
        fetchEquityCurve(),
        fetchAgentDecisions(),
        fetchAssetBreakdown(),
      ]);
      setStatus(statusData);
      setSpot(spotData);
      setPerp(perpData);
      setGlobal(globalData);
      setSettings(settingsData.settings);
      setWallet(walletData);
      setEquity(equityData);
      setDecisions(decisionsData);
      setAssetBreakdown(breakdownData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load agent data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refresh();
    }, AGENT_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  const handleSave = async () => {
    setSaving(true);
    setActionError('');
    try {
      const response = await saveAgentSettings(settings, adminToken);
      setSettings(response.settings);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleValidate = async () => {
    setSaving(true);
    setActionError('');
    try {
      setValidation(await validateOnboarding(adminToken));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Validation failed');
    } finally {
      setSaving(false);
    }
  };

  const handleKill = async (state: KillSwitchState) => {
    setSaving(true);
    setActionError('');
    try {
      setStatus(await setKillSwitch(state, adminToken));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Kill switch failed');
    } finally {
      setSaving(false);
    }
  };

  const handleTradeDetail = async (tradeId: string) => {
    setSaving(true);
    setActionError('');
    try {
      setTradeDetail(await fetchTradeDetail(tradeId));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Unable to load trade detail');
    } finally {
      setSaving(false);
    }
  };

  const statusTone = useMemo(() => {
    if (status?.kill_switch === 'hard_stop') return 'text-accent-red';
    if (status?.kill_switch === 'soft_stop' || status?.kill_switch === 'degraded') return 'text-accent-yellow';
    return 'text-accent-green';
  }, [status]);

  return (
    <div className="space-y-4">
      {tradeDetail ? (
        <TradeDetailScreen detail={tradeDetail} onBack={() => setTradeDetail(null)} />
      ) : (
        <>
      <div className="rounded-xl bg-dark-800 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white">AI Agent</p>
            <p className="truncate text-xs text-gray-500">{status?.mode ?? settings.mode} - {status?.execution_mode ?? settings.execution_mode}</p>
          </div>
          <button onClick={refresh} disabled={loading} className="rounded-lg bg-dark-700 px-3 py-1.5 text-xs font-semibold text-gray-300 disabled:opacity-40">
            {loading ? 'Loading' : 'Refresh'}
          </button>
        </div>
        <div className="mt-3 flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2">
          <span className="text-xs text-gray-500">Runtime</span>
          <span className={`text-xs font-semibold ${statusTone}`}>{status?.kill_switch ?? 'loading'}</span>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-1.5">
        <SegmentButton id="spot" label="Spot" active={pane === 'spot'} onClick={setPane} />
        <SegmentButton id="perp" label="Perp" active={pane === 'perp'} onClick={setPane} />
        <SegmentButton id="global" label="Global" active={pane === 'global'} onClick={setPane} />
        <SegmentButton id="coins" label="Coins" active={pane === 'coins'} onClick={setPane} />
        <SegmentButton id="setup" label="Setup" active={pane === 'setup'} onClick={setPane} />
      </div>

      {error && <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{error}</p>}
      {watchlistError && pane !== 'coins' && (
        <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{watchlistError}</p>
      )}
      {pane === 'spot' && <SpotPane data={spot} onTrade={(tradeId) => void handleTradeDetail(tradeId)} />}
      {pane === 'perp' && <PerpPane data={perp} onTrade={(tradeId) => void handleTradeDetail(tradeId)} />}
      {pane === 'global' && <GlobalPane data={global} status={status} equity={equity} decisions={decisions} assetBreakdown={assetBreakdown} />}
      {pane === 'coins' && (
        <CoinsPane
          eligibleTokens={eligibleTokens}
          selectedAiSymbols={selectedAiSymbols}
          adminToken={adminToken}
          saving={watchlistSaving}
          error={watchlistError}
          onToggle={onToggleAiSymbol}
        />
      )}
      {pane === 'setup' && (
        <SetupPane
          settings={settings}
          onSettings={setSettings}
          adminToken={adminToken}
          onAdminToken={onAdminToken}
          wallet={wallet}
          validation={validation}
          agentStatus={status}
          saving={saving}
          actionError={actionError}
          onSave={handleSave}
          onValidate={handleValidate}
          onKill={handleKill}
        />
      )}
        </>
      )}
    </div>
  );
};

export default AgentTab;
