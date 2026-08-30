import { useCallback, useEffect, useMemo, useRef, useState, type FC } from 'react';
import {
  fetchAgentSettings,
  fetchAgentStatus,
  fetchAgentDecisions,
  fetchAssetBreakdown,
  fetchEquityCurve,
  type ClaudeUsageView,
  fetchClaudeUsage,
  fetchAsterWallet,
  testAsterConnection,
  fetchExecutionWallets,
  fetchGlobalView,
  fetchPerpView,
  fetchSpotView,
  fetchTradeDetail,
  saveAgentSettings,
  setKillSwitch,
  riskCloseAll,
  adjustEquity,
  validateOnboarding,
  fetchAgentWatchlist,
  fetchSpotWatchlist,
  updateSpotWatchlist,
  fetchPerpWatchlist,
  updatePerpWatchlist,
  type AgentDecisionResponse,
  type AgentMarketWatchlistResponse,
  type VenueAvailability,
  type WatchlistRanking,
  type AgentMobileSettings,
  type AgentStatus,
  type AssetBreakdownResponse,
  type CredentialValidationResponse,
  type EquityCurveResponse,
  type EquityRange,
  type AsterConnectionReport,
  type AsterWalletView,
  type ExecutionWalletsResponse,
  type GlobalView,
  type KillSwitchState,
  type PerpView,
  type SpotView,
  type TradeDetail,
  verifyAdminToken,
  fetchReserve,
  fetchReserveHistory,
  fetchReserveTransactions,
  fetchReserveSettings,
  saveReserveSettings,
  reserveTransfer,
  reserveDeploy,
  reserveRebalance,
  type ReserveView,
  type ReserveHistoryResponse,
  type ReserveTransactionsResponse,
  type ReserveSettings,
} from '../services/agentApi';
import { hapticLight } from '../utils/haptics';

type AgentPane = 'spot' | 'perp' | 'global' | 'coins' | 'wallet' | 'setup' | 'bank';

const MICRO_PRICE_FULL_THRESHOLD = 0.000001;

const fmtUsd = (value: string | number | null | undefined) => {
  const n = Number(value ?? 0);
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};

const fmtMicroPrice = (value: number, maxDecimals = 18): string => {
  const sign = value < 0 ? '-' : '';
  const fixed = Math.abs(value).toFixed(maxDecimals).replace(/0+$/, '').replace(/\.$/, '');
  return fixed === '0' ? '$0' : `${sign}$${fixed}`;
};

const fmtSubDollarPrice = (value: number): string => {
  const decimals = Math.abs(value) < MICRO_PRICE_FULL_THRESHOLD ? 18 : 8;
  return fmtMicroPrice(value, decimals);
};

const fmtPrice = (value: string | number | null | undefined): string => {
  const n = Number(value);
  if (!Number.isFinite(n) || value == null || value === '') return '$--';
  if (n === 0) return '$0';
  if (n >= 1000) return `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
  if (n >= 1)    return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
  return fmtSubDollarPrice(n);
};

const fmtPriceFull = (value: string | number | null | undefined): string => {
  if (value == null || value === '') return '-';
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  if (n === 0) return '$0';
  if (Math.abs(n) < 1) return fmtSubDollarPrice(n);
  const s = String(value);
  const dotIdx = s.indexOf('.');
  const intStr = Math.trunc(Math.abs(n)).toLocaleString('en-US');
  const sign = n < 0 ? '-' : '';
  if (dotIdx === -1) return `${sign}$${intStr}`;
  const decStr = s.slice(dotIdx + 1).slice(0, 8).replace(/0+$/, '');
  return decStr ? `${sign}$${intStr}.${decStr}` : `${sign}$${intStr}`;
};

const fmtPct = (value: string | number | null | undefined) => {
  const n = Number(value ?? 0);
  return `${n.toFixed(2)}%`;
};

const riskGuardrailText: Record<string, { title: string; detail: string }> = {
  drawdown_cap_guard: {
    title: 'Trading bloccato: drawdown cap',
    detail: 'Il drawdown ha superato la soglia impostata. Le nuove entrate spot e perp sono sospese.',
  },
  daily_loss_limit_guard: {
    title: 'Trading bloccato: perdita giornaliera',
    detail: 'La perdita giornaliera ha raggiunto il limite. Le nuove entrate sono sospese fino al reset UTC.',
  },
  portfolio_floor_guard: {
    title: 'Trading bloccato: equity minima',
    detail: 'Il capitale è sotto il floor di sicurezza. Le nuove entrate sono sospese.',
  },
};

const defaultSettings: AgentMobileSettings = {
  mode: 'conservative',
  markets_enabled: 'both',
  execution_mode: 'dry_run',
  network: 'testnet',
  test_scaling_pct: 10,
  operating_hours_utc: '00:00-23:59',
  drawdown_alert_enabled: true,
  daily_loss_limit_pct: -8,
  drawdown_cap_pct: -15,
  min_pool_liquidity_usd: 50000,
  market_reversal_filter_enabled: true,
  spot_market_reversal_filter_enabled: true,
  perp_market_reversal_filter_enabled: true,
  spot_market_regime_filter_enabled: true,
  spot_breakeven_enabled: true,
  perp_breakeven_enabled: true,
  spot_trailing_enabled: true,
  perp_trailing_enabled: true,
  spot_trailing_only_after_tp1: true,
  spot_time_stop_enabled: false,
  perp_time_stop_enabled: false,
  perp_trend_shock_enabled: true,
  perp_trend_shock_adx_threshold: 25,
  perp_trend_shock_natr_percentile: 90,
  perp_trend_shock_volume_threshold: 2.0,
  perp_trend_shock_recovery_confirmations: 3,
  perp_smart_sl_enabled: true,
  perp_smart_sl_l1_frac: 0.333,
  perp_smart_sl_l2_frac: 0.666,
  perp_smart_sl_split_l1: 0.25,
  perp_smart_sl_split_l2: 0.55,
  perp_smart_sl_split_l3: 0.20,
  perp_smart_sl_rebuy_mode: 'above_entry',
  perp_smart_sl_rebuy_above_entry_pct: 100,
  perp_smart_sl_split_l1_r2: 0.75,
  perp_smart_sl_split_l2_r2: 0.20,
  perp_smart_sl_split_l3_r2: 0.05,
  perp_smart_sl_delta_l1: 0.08,
  perp_smart_sl_delta_l2: 0.16,
  perp_smart_sl_confirmation_candles: 2,
  perp_smart_sl_max_reentries: 1,
  perp_smart_sl_tp_adjust_after_rebuy: true,
  perp_smart_sl_tp_recovery_delta_pct: 7,
  spot_breakeven_mode: 'atr' as const,
  perp_breakeven_mode: 'atr' as const,
  spot_sl_mode: 'atr' as const,
  perp_sl_mode: 'atr' as const,
  spot_structural_stop_lookback_candles: 20,
  spot_structural_stop_buffer_pct: 1.10,
  perp_structural_stop_lookback_candles: 20,
  perp_structural_stop_buffer_pct: 1.10,
  spot_capital_per_trade_pct: 6,
  spot_per_trade_pct: 1.5,
  spot_max_open_positions: 3,
  spot_max_exposure_pct: 30,
  spot_cooldown_minutes: 30,
  spot_max_slippage_pct: 1,
  spot_max_stop_distance_filter_enabled: true,
  spot_max_stop_distance_pct: 4.0,
  perp_capital_per_trade_pct: 4,
  perp_per_trade_pct: 1.5,
  perp_max_open_positions: 5,
  perp_max_exposure_pct: 20,
  perp_cooldown_minutes: 15,
  perp_max_slippage_pct: 0.5,
  perp_fixed_margin_enabled: false,
  perp_fixed_margin_usd: 50,
  capital_per_trade_pct: 6,
  per_trade_pct: 1.5,
  max_open_positions: 3,
  max_total_exposure_pct: 30,
  max_slippage_pct: 1,
  cooldown_minutes: 30,
  spot_confidence_threshold: 0.7,
  spot_volatility_trigger_pct: 3,
  spot_relative_volume_threshold: 1.8,
  spot_atr_stop_multiplier: 1.5,
  spot_tp1_atr_multiplier: 2.5,
  spot_tp2_atr_multiplier: 4.5,
  spot_breakeven_trigger_atr: 1.5,
  spot_trailing_atr_multiplier: 1.5,
  spot_trailing_distance_pct: 2,
  spot_partial_take_profit_pct: 50,
  spot_tp1_close_pct: 60,
  spot_time_stop_hours: 6,
  perp_direction_mode: 'long_short',
  perp_min_leverage: 4,
  perp_max_leverage: 40,
  perp_value_area_pct: 68,
  perp_atr_stop_multiplier: 0.8,
  perp_trailing_mode: 'largo' as const,
  perp_trailing_pnl_pct: 0,
  perp_protection_mode: 'trailing' as const,
  perp_profit_lock_steps: [[0.45, 0.25], [0.7, 0.5], [0.9, 0.70]] as Array<[number, number]>,
  perp_breakeven_min_profit_usd: 0,
  perp_tp1_close_pct: 70,
  perp_time_stop_hours: 8,
  perp_fee_mode: 'taker' as const,
  spot_fee_mode: 'all' as const,
  post_close_candles: 10,
};

const AGENT_REFRESH_MS = 45_000;
// Refresh leggero (solo posizioni/PnL). 15s evita accavallamenti quando provider esterni rallentano.
const AGENT_FAST_REFRESH_MS = 15_000;
const TRADE_DETAIL_CACHE_TTL_MS = 10 * 60_000;
const TRADE_DETAIL_BASE_TIMEOUT_MS = 20_000;
const TRADE_DETAIL_ENRICH_TIMEOUT_MS = 25_000;
const TRADE_DETAIL_CACHE_MAX = 80;
// Matches the mobile history page size: open positions are always added on top.
const TRADE_DETAIL_PREFETCH_LIMIT = 8;
const TRADE_DETAIL_PREFETCH_CONCURRENCY = 2;
const TRADE_DETAIL_PREFETCH_RETRY_MS = 60_000;

const tradeDetailCache = new Map<string, { detail: TradeDetail; updatedAt: number }>();
const tradeDetailInflight = new Map<string, Promise<TradeDetail>>();
const tradeDetailPrefetchRetryAt = new Map<string, number>();

const hasBaseTradeChart = (detail: TradeDetail): boolean =>
  (detail.chart?.candles?.length ?? 0) > 1;

const needsPostCloseCandles = (detail: TradeDetail): boolean =>
  Boolean(detail.chart && !detail.chart.live && detail.chart.closed_at);

const hasCompleteTradeChart = (detail: TradeDetail): boolean => {
  if (!hasBaseTradeChart(detail)) return false;
  if (!detail.chart?.stop_reference) return false;
  if (!needsPostCloseCandles(detail)) return true;
  return (detail.chart?.post_close_candles?.length ?? 0) > 0;
};

const getCachedTradeDetail = (tradeId: string): TradeDetail | null => {
  const cached = tradeDetailCache.get(tradeId);
  if (!cached) return null;
  if (hasCompleteTradeChart(cached.detail)) return cached.detail;
  if (Date.now() - cached.updatedAt > TRADE_DETAIL_CACHE_TTL_MS) {
    tradeDetailCache.delete(tradeId);
    return null;
  }
  return cached.detail;
};

const hasCompleteCachedTradeDetail = (tradeId: string): boolean => {
  const cached = getCachedTradeDetail(tradeId);
  return cached != null && hasCompleteTradeChart(cached);
};

const isTradeDetailInflight = (tradeId: string): boolean =>
  tradeDetailInflight.has(`${tradeId}:base`) || tradeDetailInflight.has(`${tradeId}:chart`);

const shouldPrefetchTradeDetail = (tradeId: string): boolean => {
  if (hasCompleteCachedTradeDetail(tradeId) || isTradeDetailInflight(tradeId)) return false;
  return Date.now() >= (tradeDetailPrefetchRetryAt.get(tradeId) ?? 0);
};

const cacheTradeDetail = (tradeId: string, detail: TradeDetail) => {
  const existing = tradeDetailCache.get(tradeId)?.detail;
  if (existing && hasCompleteTradeChart(existing) && !hasCompleteTradeChart(detail)) {
    return;
  }
  if (existing && hasBaseTradeChart(existing) && !hasBaseTradeChart(detail)) {
    return;
  }
  if (tradeDetailCache.has(tradeId)) tradeDetailCache.delete(tradeId);
  tradeDetailCache.set(tradeId, { detail, updatedAt: Date.now() });
  if (hasCompleteTradeChart(detail)) {
    tradeDetailPrefetchRetryAt.delete(tradeId);
  }
  while (tradeDetailCache.size > TRADE_DETAIL_CACHE_MAX) {
    const oldest = tradeDetailCache.keys().next().value;
    if (!oldest) break;
    tradeDetailCache.delete(oldest);
  }
};

const fetchTradeDetailDeduped = (
  tradeId: string,
  options: { enrichChart?: boolean; timeoutMs?: number } = {},
): Promise<TradeDetail> => {
  const key = `${tradeId}:${options.enrichChart ? 'chart' : 'base'}`;
  const existing = tradeDetailInflight.get(key);
  if (existing) return existing;
  const request = fetchTradeDetail(tradeId, options)
    .then((detail) => {
      cacheTradeDetail(tradeId, detail);
      return detail;
    })
    .finally(() => {
      tradeDetailInflight.delete(key);
    });
  tradeDetailInflight.set(key, request);
  return request;
};

const EmptyState: FC<{ title: string; detail: string }> = ({ title, detail }) => (
  <div className="rounded-xl border border-dashed border-dark-600 bg-dark-800/60 px-4 py-8 text-center">
    <p className="text-sm font-semibold text-white">{title}</p>
    <p className="mt-1 text-xs text-gray-500 leading-relaxed">{detail}</p>
  </div>
);

const RiskGuardrailBanner: FC<{ guardrail: GlobalView['risk_guardrail'] }> = ({ guardrail }) => {
  if (!guardrail?.blocked) return null;
  const copy = guardrail.reason ? riskGuardrailText[guardrail.reason] : undefined;
  return (
    <div className="rounded-xl border border-accent-red/30 bg-accent-red/10 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-accent-red">{copy?.title ?? guardrail.title}</p>
          <p className="mt-1 text-xs leading-5 text-gray-300">{copy?.detail ?? guardrail.detail}</p>
        </div>
        <span className="rounded-full bg-accent-red/15 px-2 py-1 text-[11px] font-semibold text-accent-red">
          {guardrail.reason?.replace(/_/g, ' ') ?? 'blocked'}
        </span>
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">Drawdown <b className="text-white">{fmtPct(guardrail.drawdown_pct)}</b></span>
        <span className="rounded-lg bg-dark-900/70 px-3 py-2 text-gray-400">Cap <b className="text-white">{fmtPct(Math.abs(guardrail.drawdown_cap_pct))}</b></span>
      </div>
    </div>
  );
};

const Stat: FC<{ label: string; value: string; tone?: 'good' | 'bad' | 'neutral' }> = ({ label, value, tone = 'neutral' }) => (
  <div className="rounded-lg bg-dark-800 px-3 py-2 min-w-0">
    <p className="text-[11px] uppercase text-gray-500 truncate">{label}</p>
    <p className={`text-sm font-bold tabular-nums truncate ${
      tone === 'good' ? 'text-accent-green' : tone === 'bad' ? 'text-accent-red' : 'text-white'
    }`}>{value}</p>
  </div>
);

const EQUITY_RANGES: { id: EquityRange; label: string }[] = [
  { id: '24h', label: '24h' },
  { id: '7d', label: '7g' },
  { id: 'all', label: 'Tutto' },
];

const PNL_COLOR = '#F0B90B'; // oro (PnL cumulato)
const BTC_COLOR = '#3B82F6'; // blu (benchmark BTC)

const fmtSignedPct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`;

const EquityChart: FC<{
  equity: EquityCurveResponse | null;
  range: EquityRange;
  onRange: (r: EquityRange) => void;
  view?: 'trading' | 'portfolio';
  onView?: (v: 'trading' | 'portfolio') => void;
}> = ({ equity, range, onRange, view = 'trading', onView }) => {
  const items = equity?.items ?? [];
  const n = items.length;

  const hasPortfolio = items.some((i) => i.portfolio_pnl_pct != null);
  const showPortfolio = view === 'portfolio' && hasPortfolio;
  const pnl = items.map((i) =>
    Number(showPortfolio ? (i.portfolio_pnl_pct ?? i.pnl_pct) : i.pnl_pct),
  );
  const btc = items.map((i) => (i.btc_pct != null ? Number(i.btc_pct) : null));
  const hasBtc = (equity?.benchmark_available ?? false) && btc.some((v) => v != null);

  const lastPnl = n > 0 ? pnl[n - 1] : 0;
  const lastBtc = hasBtc ? (btc[n - 1] ?? 0) : null;

  // Dominio Y: include sempre lo 0% (breakeven) e un po' di margine.
  const pool = [...pnl, ...(hasBtc ? (btc.filter((v) => v != null) as number[]) : []), 0];
  let lo = Math.min(...pool);
  let hi = Math.max(...pool);
  if (!Number.isFinite(lo) || !Number.isFinite(hi)) { lo = -1; hi = 1; }
  if (lo === hi) { lo -= 1; hi += 1; }
  const padY = (hi - lo) * 0.12;
  lo -= padY; hi += padY;

  const W = 320, H = 170, padL = 40, padR = 14, padT = 10, padB = 22;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;
  const xAt = (idx: number) => (n <= 1 ? padL + plotW / 2 : padL + (idx / (n - 1)) * plotW);
  const yAt = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * plotH;
  const y0 = yAt(0);

  const polyline = (vals: (number | null)[]) =>
    vals
      .map((v, i) => (v == null ? null : `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`))
      .filter(Boolean)
      .join(' ');

  const pnlLine = polyline(pnl);
  const btcLine = hasBtc ? polyline(btc) : '';
  const areaPath =
    n > 0
      ? `M ${xAt(0).toFixed(1)},${y0.toFixed(1)} ` +
        pnl.map((v, i) => `L ${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`).join(' ') +
        ` L ${xAt(n - 1).toFixed(1)},${y0.toFixed(1)} Z`
      : '';

  const gridVals = [hi, (hi + lo) / 2, lo];

  const fmtX = (iso: string) => {
    const d = new Date(iso);
    return range === '24h'
      ? d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' });
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        {hasPortfolio && onView ? (
          <button
            onClick={() => { hapticLight(); onView(showPortfolio ? 'trading' : 'portfolio'); }}
            className="text-xs font-semibold uppercase text-gray-500"
          >
            {showPortfolio ? 'Portafoglio totale ▾' : 'Solo trading ▾'}
          </button>
        ) : (
          <h3 className="text-xs font-semibold uppercase text-gray-500">PnL cumulato</h3>
        )}
        <div className="flex gap-1">
          {EQUITY_RANGES.map((r) => (
            <button
              key={r.id}
              onClick={() => { hapticLight(); onRange(r.id); }}
              className={`rounded-md px-2 py-1 text-[11px] font-semibold transition-colors ${
                range === r.id ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400'
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-6">
        <div>
          <div className={`text-2xl font-bold ${lastPnl >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
            {fmtSignedPct(lastPnl)}
          </div>
          <div className="text-[11px] text-gray-400">
            <span style={{ color: PNL_COLOR }}>●</span> {showPortfolio ? 'PnL portafoglio' : 'PnL trading'}
          </div>
        </div>
        {hasBtc && lastBtc != null && (
          <div>
            <div className={`text-2xl font-bold ${lastBtc >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
              {fmtSignedPct(lastBtc)}
            </div>
            <div className="text-[11px] text-gray-400">
              <span style={{ color: BTC_COLOR }}>●</span> BTC trend
            </div>
          </div>
        )}
      </div>

      {n === 0 ? (
        <div className="py-6 text-center text-xs text-gray-500">Nessun dato nel periodo selezionato</div>
      ) : (
        <>
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 'auto' }} role="img" aria-label="Curva PnL cumulato">
            <defs>
              <linearGradient id="pnlFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={PNL_COLOR} stopOpacity="0.28" />
                <stop offset="100%" stopColor={PNL_COLOR} stopOpacity="0" />
              </linearGradient>
            </defs>

            {/* griglia + label Y */}
            {gridVals.map((v, i) => (
              <g key={i}>
                <line x1={padL} y1={yAt(v)} x2={W - padR} y2={yAt(v)} stroke="#ffffff" strokeOpacity="0.06" strokeWidth="1" />
                <text x={padL - 4} y={yAt(v) + 3} textAnchor="end" fontSize="9" fill="#6b7280">
                  {v.toFixed(2)}%
                </text>
              </g>
            ))}

            {/* baseline 0% (breakeven) */}
            <line x1={padL} y1={y0} x2={W - padR} y2={y0} stroke="#9ca3af" strokeOpacity="0.5" strokeWidth="1" strokeDasharray="3 3" />

            {/* area sotto PnL */}
            {areaPath && <path d={areaPath} fill="url(#pnlFill)" />}

            {/* linea BTC */}
            {btcLine && <polyline points={btcLine} fill="none" stroke={BTC_COLOR} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />}

            {/* linea PnL */}
            {pnlLine && <polyline points={pnlLine} fill="none" stroke={PNL_COLOR} strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />}

            {/* dot finali */}
            {hasBtc && lastBtc != null && <circle cx={xAt(n - 1)} cy={yAt(lastBtc)} r="3" fill={BTC_COLOR} />}
            {n > 0 && <circle cx={xAt(n - 1)} cy={yAt(lastPnl)} r="3.5" fill={PNL_COLOR} stroke="#0b0e14" strokeWidth="1" />}
          </svg>

          <div className="flex justify-between px-1 text-[10px] text-gray-500">
            <span>{fmtX(items[0].timestamp_utc)}</span>
            <span>{fmtX(items[n - 1].timestamp_utc)}</span>
          </div>
        </>
      )}
    </div>
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
  availability?: VenueAvailability;
  rank?: number | null;
}> = ({ symbol, selected, disabled, onToggle, availability, rank }) => {
  const status = availability?.status;
  const blocked = status === 'unavailable' && !selected;
  const tone = selected
    ? 'border-accent-yellow/50 bg-accent-yellow/10 text-accent-yellow'
    : blocked
      ? 'border-dark-700 bg-dark-800 text-gray-500 opacity-60'
      : 'border-dark-700 bg-dark-800 text-gray-300';
  return (
    <button
      type="button"
      disabled={disabled || blocked}
      onClick={() => { hapticLight(); onToggle(symbol); }}
      title={availability?.reason}
      className={`flex flex-col gap-0.5 rounded-lg border px-3 py-2 text-left transition-colors disabled:opacity-45 ${tone}`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-baseline gap-1.5">
          {rank != null && <span className="flex-shrink-0 text-[10px] text-gray-500">#{rank}</span>}
          <span className={`min-w-0 truncate text-sm font-semibold ${status === 'unavailable' ? 'line-through' : ''}`}>{symbol}</span>
        </span>
        <span className={`h-2.5 w-2.5 flex-shrink-0 rounded-full ${selected ? 'bg-accent-yellow' : 'bg-gray-600'}`} />
      </span>
      {availability && (
        <span className={`text-[10px] ${status === 'available' ? 'text-accent-green' : status === 'unavailable' ? 'text-accent-red' : 'text-gray-500'}`}>
          {status === 'available' ? `✓ ${availability.venue}` : status === 'unavailable' ? `✗ ${availability.venue}` : `? ${availability.venue}`}
        </span>
      )}
    </button>
  );
};

const HelpTip: FC<{ text: string }> = ({ text }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const onHelp = (e: Event) => { if ((e as CustomEvent).detail !== ref.current) close(); };
    document.addEventListener('click', close);
    document.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    document.addEventListener('helptip:open', onHelp);
    return () => {
      document.removeEventListener('click', close);
      document.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
      document.removeEventListener('helptip:open', onHelp);
    };
  }, [open]);
  return (
    <span ref={ref} className="relative ml-1 inline-flex">
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          document.dispatchEvent(new CustomEvent('helptip:open', { detail: ref.current }));
          setOpen((v) => !v);
        }}
        className="flex h-4 w-4 items-center justify-center rounded-full bg-dark-600 text-[10px] font-bold text-gray-400 hover:bg-dark-500 hover:text-white"
      >?</button>
      {open && (
        <div
          onClick={(e) => e.stopPropagation()}
          className="absolute left-1/2 bottom-6 z-50 w-64 -translate-x-1/2 rounded-lg border border-dark-600 bg-dark-900 px-3 py-2.5 text-xs text-gray-300 shadow-xl whitespace-pre-line"
        >{text}</div>
      )}
    </span>
  );
};

const Collapsible: FC<{ title: string; count: number; children: React.ReactNode }> = ({ title, count, children }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-dark-700">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left"
      >
        <span className="text-sm font-semibold text-white">{title}</span>
        <span className="flex items-center gap-2">
          <span className="rounded-full bg-dark-700 px-2 py-0.5 text-xs text-gray-400">{count}</span>
          <span className={`text-xs text-gray-500 transition-transform ${open ? 'rotate-90' : ''}`}>▶</span>
        </span>
      </button>
      {open && <div className="space-y-3 border-t border-dark-700 px-3 py-3">{children}</div>}
    </div>
  );
};

const NumberInput: FC<{
  label: string;
  value: number;
  step?: number;
  help?: string;
  showHelp?: boolean;
  onChange: (value: number) => void;
}> = ({ label, value, step = 1, help, showHelp, onChange }) => {
  const [raw, setRaw] = useState(String(value));
  useEffect(() => { setRaw(String(value)); }, [value]);
  return (
    <label className="block">
      <span className="text-xs text-gray-500">{label}{showHelp && help && <HelpTip text={help} />}</span>
      <input
        type="number"
        step={step}
        value={raw}
        onChange={(e) => {
          const s = e.target.value;
          setRaw(s);
          const n = parseFloat(s);
          if (!Number.isNaN(n)) onChange(n);
        }}
        onBlur={() => setRaw(String(value))}
        className="mt-1 w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
      />
    </label>
  );
};

const SelectInput: FC<{
  label: string;
  value: string;
  options: Array<{ value: string; label: string }>;
  help?: string;
  showHelp?: boolean;
  onChange: (value: string) => void;
}> = ({ label, value, options, help, showHelp, onChange }) => (
  <label className="block">
    <span className="text-xs text-gray-500">{label}{showHelp && help && <HelpTip text={help} />}</span>
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="mt-1 w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
    >
      {options.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
    </select>
  </label>
);

const ToggleInput: FC<{
  label: string;
  checked: boolean;
  help?: string;
  showHelp?: boolean;
  onChange: (checked: boolean) => void;
}> = ({ label, checked, help, showHelp, onChange }) => (
  <label className="flex items-center justify-between gap-3 rounded-lg border border-dark-700 bg-dark-800 px-3 py-2">
    <span className="min-w-0 text-sm font-semibold text-white">{label}{showHelp && help && <HelpTip text={help} />}</span>
    <input
      type="checkbox"
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
      className="h-5 w-5 accent-accent-blue"
    />
  </label>
);

const MOBILE_PAGE = 8;

type SpotHistoryRow = NonNullable<SpotView['history']>[number];
type PerpHistoryRow = NonNullable<PerpView['history']>[number];

function shortPositionId(value?: string | null): string {
  if (!value) return '';
  return value.replace(/^pos_/, '').slice(0, 8);
}

const CLOSE_REASON_LABELS: Record<string, { label: string; className: string }> = {
  stop_loss: { label: 'Stop Loss', className: 'text-accent-red' },
  breakeven: { label: 'Breakeven', className: 'text-gray-300' },
  take_profit_1: { label: 'Take Profit 1', className: 'text-accent-green' },
  take_profit_2: { label: 'Take Profit 2', className: 'text-accent-green' },
  trailing_stop: { label: 'Trailing Stop', className: 'text-accent-green' },
  time_stop: { label: 'Time Stop', className: 'text-gray-300' },
  smart_sl_sell_l1: { label: 'Smart SL Sell L1', className: 'text-amber-400' },
  smart_sl_sell_l2: { label: 'Smart SL Sell L2', className: 'text-amber-400' },
  smart_sl_rebuy_l1: { label: 'Smart SL Rebuy L1', className: 'text-sky-400' },
  smart_sl_rebuy_l2: { label: 'Smart SL Rebuy L2', className: 'text-sky-400' },
  smart_sl_rebuy_all: { label: 'Smart SL Rebuy All', className: 'text-sky-400' },
  profit_lock: { label: 'Profit Lock', className: 'text-accent-green' },
};

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
            <div className="text-[11px] text-gray-500 mb-1">
              {new Date(t.timestamp_utc).toLocaleString('it-IT', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
            </div>
            <div className="flex items-start gap-2">
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-white">{label}</div>
                {market === 'perp' && t.position_id && (
                  <div className="mt-1 text-[11px] font-semibold text-accent-blue">
                    Pos {shortPositionId(t.position_id)}
                  </div>
                )}
                <div className="mt-2 flex gap-3 text-sm text-gray-400">
                  <span>In {fmtPriceFull(t.entry_price ?? t.price)}</span>
                  <span>Out {fmtPriceFull(t.current_or_exit_price ?? t.price)}</span>
                </div>
              </div>
              <div className={`flex-shrink-0 text-right font-bold ${isGood ? 'text-accent-green' : 'text-accent-red'}`}>
                <div>{t.pnl_pct ?? '--'}%</div>
                <div>{isGood ? '+' : ''}{fmtUsd(t.pnl_usd ?? 0)}</div>
              </div>
            </div>
            <div className="mt-1.5 flex items-center text-xs text-gray-500">
              <span className="flex items-center gap-1.5">
                <span className="uppercase tracking-wide">{t.status}</span>
                {t.close_reason && CLOSE_REASON_LABELS[t.close_reason] && (
                  <span className={`rounded bg-dark-900 px-1.5 py-0.5 font-semibold ${CLOSE_REASON_LABELS[t.close_reason].className}`}>
                    {CLOSE_REASON_LABELS[t.close_reason].label}
                  </span>
                )}
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
  const riskOff = data?.market_risk_off ?? false;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Spot PnL" value={fmtUsd(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0))} tone={(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0)) >= 0 ? 'good' : 'bad'} />
        <Stat label="Win rate" value={fmtPct(data?.win_rate_pct ?? 0)} />
        <Stat label="Open" value={String(data?.open_positions.length ?? 0)} />
        <Stat label="Trade Tot" value={String(data?.trade_count ?? 0)} />
        <Stat label="Trade Day" value={String(data?.trade_count_today ?? 0)} />
        <Stat label="Vol Tot" value={fmtUsd(Number(data?.volume_total_usd ?? 0))} />
        <Stat label="Vol Day" value={fmtUsd(Number(data?.volume_today_usd ?? 0))} />
        <Stat label="Bot Day" value={String(data?.bot_active_days ?? 0)} />
      </div>
      {!hasActivity && (
        riskOff
          ? <EmptyState title="Mercato bloccato per condizioni sfavorevoli" detail="BTC in downtrend: nuovi acquisti spot sospesi finché non rientra sopra la media." />
          : <EmptyState title="In attesa di segnali spot" detail="Nessuna posizione aperta e nessun trade registrato." />
      )}
      {hasPositions ? (
        <div className="space-y-2">
          {data!.open_positions.map((position) => (
            <button
              key={position.position_id}
              type="button"
              onClick={() => position.open_trade_id && onTrade(position.open_trade_id)}
              disabled={!position.open_trade_id}
              className="block w-full rounded-xl bg-dark-800 px-4 py-3 text-left transition active:scale-[0.99] disabled:cursor-default"
            >
              <div className="text-[11px] text-gray-500 mb-1">
                {new Date(position.opened_at).toLocaleString('it-IT', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
              </div>
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-white">{position.asset}</p>
                <p className={Number(position.pnl_unrealized) >= 0 ? 'text-accent-green text-sm font-bold' : 'text-accent-red text-sm font-bold'}>
                  {fmtUsd(position.pnl_unrealized)} / {position.pnl_pct ?? '+0.00'}%
                </p>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Entry {fmtPriceFull(position.entry_price)}</span>
                <span>Now {fmtPriceFull(position.current_price)}</span>
                <span>{position.status}</span>
              </div>
              <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Mode: <span className={!position.fee_mode || position.fee_mode === 'none' ? 'text-gray-400' : 'text-accent-yellow'}>{position.fee_mode === 'none' ? 'nessuna' : position.fee_mode === 'all' ? 'swap+slip' : position.fee_mode ?? '-'}</span></span>
                <span>Swap {position.swap_fee_usd != null ? fmtUsd(position.swap_fee_usd) : '$0.00'}</span>
                <span>Slip. {position.slippage_usd != null ? fmtUsd(position.slippage_usd) : '$0.00'}</span>
              </div>
              <div className="mt-1.5 text-xs text-gray-500">
                <span>{position.open_trade_id ? 'Tocca per dettagli ›' : ''}</span>
              </div>
            </button>
          ))}
        </div>
      ) : hasActivity && (
        riskOff
          ? <EmptyState title="Mercato bloccato per condizioni sfavorevoli" detail="BTC in downtrend: nuovi acquisti spot sospesi finché non rientra sopra la media." />
          : <EmptyState title="Nessuna posizione aperta" detail="Lo Spot e' pronto: le nuove entrate appariranno qui." />
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
        <Stat label="Perp PnL" value={fmtUsd(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0))} tone={(Number(data?.realized_pnl_usd ?? 0) + Number(data?.unrealized_pnl_usd ?? 0)) >= 0 ? 'good' : 'bad'} />
        <Stat label="Win rate" value={fmtPct(data?.win_rate_pct ?? 0)} />
        <Stat label="Open" value={String(data?.open_positions.length ?? 0)} />
        <Stat label="Trade Tot" value={String(data?.trade_count ?? 0)} />
        <Stat label="Trade Day" value={String(data?.trade_count_today ?? 0)} />
        <Stat label="Vol Tot" value={fmtUsd(Number(data?.volume_total_usd ?? 0))} />
        <Stat label="Vol Day" value={fmtUsd(Number(data?.volume_today_usd ?? 0))} />
        <Stat label="Bot Day" value={String(data?.bot_active_days ?? 0)} />
      </div>
      {!hasActivity && (
        <EmptyState title="In attesa di segnali perp" detail="Nessuna posizione aperta e nessun trade registrato." />
      )}
      {hasPositions ? (
        <div className="space-y-2">
          {data!.open_positions.map((position) => (
            <button
              key={position.position_id}
              type="button"
              onClick={() => position.open_trade_id && onTrade(position.open_trade_id)}
              disabled={!position.open_trade_id}
              className="block w-full rounded-xl bg-dark-800 px-4 py-3 text-left transition active:scale-[0.99] disabled:cursor-default"
            >
              <div className="text-[11px] text-gray-500 mb-1">
                {new Date(position.opened_at).toLocaleString('it-IT', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}
              </div>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <p className="text-sm font-semibold text-white">{position.asset} {position.side}</p>
                  <span className="rounded-full bg-dark-700 px-2 py-1 text-xs text-accent-blue">{position.leverage}x</span>
                  {position.smart_sl_active && (
                    <span className={`rounded-full px-2 py-1 text-xs font-semibold ${position.smart_sl_levels_sold?.some(Boolean) ? 'bg-amber-900/40 text-amber-400' : 'bg-dark-700 text-gray-400'}`}>
                      SSL {position.smart_sl_levels_sold?.filter(Boolean).length ?? 0}/2
                    </span>
                  )}
                </div>
                <p className={Number(position.pnl_unrealized) >= 0 ? 'text-accent-green text-sm font-bold' : 'text-accent-red text-sm font-bold'}>
                  {fmtUsd(position.pnl_unrealized)} / {position.pnl_pct ?? '+0.00'}%
                </p>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Size {Number(position.size).toFixed(4)}</span>
                <span>Entry {fmtPriceFull(position.entry_price)}</span>
                <span>Now {fmtPriceFull(position.current_price)}</span>
              </div>
              <div className="mt-1 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Margin {position.margin_usd != null ? fmtUsd(position.margin_usd) : '$0.00'}</span>
                <span>Liq {position.liquidation_price ? fmtPrice(position.liquidation_price) : '-'}</span>
                <span>Funding {position.funding_rate ? fmtPct(Number(position.funding_rate) * 100) : '-'}</span>
              </div>
              <div className="mt-1.5 text-xs text-gray-500">
                <span>{position.open_trade_id ? 'Tocca per dettagli ›' : ''}</span>
              </div>
            </button>
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
  equityRange: EquityRange;
  onEquityRange: (r: EquityRange) => void;
  decisions: AgentDecisionResponse | null;
  assetBreakdown: AssetBreakdownResponse | null;
  claudeUsage: ClaudeUsageView | null;
}> = ({ data, status, equity, equityRange, onEquityRange, decisions, assetBreakdown, claudeUsage }) => {
  const [equityView, setEquityView] = useState<'trading' | 'portfolio'>('trading');
  const hasHistory = (data?.pnl_history.length ?? 0) > 0;
  const hasPortfolio = Number(data?.total_equity_usd ?? 0) > 0 || Number(data?.initial_equity_usd ?? 0) > 0;
  const hasTradesToday = Number(data?.trades_today ?? 0) > 0;
  const sortedAssets = [...(assetBreakdown?.items ?? [])].sort((a, b) => Number(b.pnl_usd) - Number(a.pnl_usd));
  const bestAssets = sortedAssets.slice(0, 3);
  const worstAssets = sortedAssets.slice(-3).reverse();

  return (
    <div className="space-y-3">
      <RiskGuardrailBanner guardrail={data?.risk_guardrail} />
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Equity" value={fmtUsd(data?.total_equity_usd)} />
        <Stat label="PnL tot." value={fmtUsd(data?.pnl_total_usd)} tone={Number(data?.pnl_total_usd ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="PnL aperto" value={fmtUsd(data?.unrealized_pnl_usd)} tone={Number(data?.unrealized_pnl_usd ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="PnL realizzato" value={fmtUsd(data?.realized_pnl_usd)} tone={Number(data?.realized_pnl_usd ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="PnL % Global" value={`${Number(data?.pnl_total_net_pct ?? 0) >= 0 ? '+' : ''}${Number(data?.pnl_total_net_pct ?? 0).toFixed(2)}%`} tone={Number(data?.pnl_total_net_pct ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="PnL % Day" value={`${Number(data?.daily_pnl_net_pct ?? 0) >= 0 ? '+' : ''}${Number(data?.daily_pnl_net_pct ?? 0).toFixed(2)}%`} tone={Number(data?.daily_pnl_net_pct ?? 0) >= 0 ? 'good' : 'bad'} />
        <Stat label="Drawdown" value={fmtPct(data?.drawdown_pct)} tone={Number(data?.drawdown_pct ?? 0) >= 10 ? 'bad' : 'neutral'} />
        <Stat label="Exposure" value={fmtPct(data?.exposure_pct)} />
        <Stat label="Trades UTC" value={String(data?.trades_today ?? 0)} />
        <Stat label="Kill switch" value={status?.kill_switch ?? data?.agent_status ?? 'idle'} />
        <Stat label="Vol Tot" value={fmtUsd(Number(data?.volume_total_usd ?? 0))} />
        <Stat label="Vol Day" value={fmtUsd(Number(data?.volume_today_usd ?? 0))} />
        <Stat label="Fee pagate" value={fmtUsd(data?.total_fees_usd ?? '0')} tone="bad" />
        <Stat
          label="API Claude"
          value={claudeUsage != null ? `$${claudeUsage.total_cost_usd.toFixed(2)} / $${claudeUsage.budget_usd.toFixed(2)}` : '--'}
          tone={claudeUsage == null ? 'neutral' : claudeUsage.budget_pct >= 90 ? 'bad' : claudeUsage.budget_pct >= 70 ? 'neutral' : 'good'}
        />
      </div>
      {(Number(data?.reserve_value_usd ?? 0) > 0.01 || Number(data?.reserve_cost_basis_usd ?? 0) > 0.01) && (
        <div className="rounded-xl border border-accent-yellow/20 bg-dark-800/40 px-3 py-3 space-y-2">
          <p className="text-[11px] font-semibold uppercase text-gray-500">🏦 Bank · Riserva di Valore</p>
          <div className="grid grid-cols-2 gap-2">
            <Stat label="Valore riserva" value={fmtUsd(data?.reserve_value_usd)} />
            <Stat label="P&L riserva" value={`${fmtUsd(data?.reserve_pnl_usd)} · ${fmtSignedPct(Number(data?.reserve_pnl_pct ?? 0))}`} tone={Number(data?.reserve_pnl_usd ?? 0) >= 0 ? 'good' : 'bad'} />
            <Stat label="Equity trading" value={fmtUsd(data?.tradable_equity_usd)} />
            <Stat label="Portafoglio totale" value={fmtUsd(data?.total_portfolio_equity_usd)} />
            <Stat label="PnL % totale" value={fmtSignedPct(Number(data?.total_portfolio_pnl_pct ?? 0))} tone={Number(data?.total_portfolio_pnl_pct ?? 0) >= 0 ? 'good' : 'bad'} />
            <Stat label="USDC riserva" value={fmtUsd(data?.reserve_cash_usd)} />
          </div>
          {data?.volatility_budget?.status === 'ready' && (
            <>
              <p className="text-[11px] font-semibold uppercase text-gray-500 pt-1">Volatility budget</p>
              <div className="grid grid-cols-2 gap-2">
                <Stat label="Max DD trading" value={`${(data.volatility_budget.trading_max_drawdown_pct ?? 0).toFixed(1)}%`} tone="bad" />
                <Stat label="Max DD totale" value={`${(data.volatility_budget.total_max_drawdown_pct ?? 0).toFixed(1)}%`} />
                <Stat label="Vol giornaliera" value={`${(data.volatility_budget.trading_daily_vol_pct ?? 0).toFixed(1)}%`} tone="bad" />
                <Stat label="Vol con riserva" value={`${(data.volatility_budget.total_daily_vol_pct ?? 0).toFixed(1)}%`} />
              </div>
            </>
          )}
        </div>
      )}
      {!hasPortfolio && !hasHistory && (
        <EmptyState title="In attesa dello stato globale" detail="Equity, drawdown ed esposizione saranno visibili al primo snapshot." />
      )}
      {!hasTradesToday && (
        <EmptyState title="Nessun trade oggi" detail="Il contatore UTC si aggiorna dopo il primo trade valido." />
      )}
      {hasHistory ? (
        <div className="rounded-xl bg-dark-800 px-4 py-3">
          <EquityChart equity={equity} range={equityRange} onRange={onEquityRange} view={equityView} onView={setEquityView} />
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

const WalletPane: FC<{
  execWallets: ExecutionWalletsResponse | null;
  spot: SpotView | null;
  perp: PerpView | null;
}> = ({ execWallets, spot, perp }) => {
  const [copied, setCopied] = useState<string | null>(null);

  const copyAddress = async (address: string) => {
    try { await navigator.clipboard.writeText(address); } catch {
      const el = document.createElement('textarea');
      el.value = address; document.body.appendChild(el); el.select();
      document.execCommand('copy'); document.body.removeChild(el);
    }
    setCopied(address);
    setTimeout(() => setCopied(null), 1600);
  };

  const totalSpotValue = (spot?.open_positions ?? []).reduce((sum, p) =>
    sum + Number(p.current_price) * Number(p.size), 0);
  const totalSpotPnl = (spot?.open_positions ?? []).reduce((sum, p) =>
    sum + Number(p.pnl_unrealized), 0);
  const totalPerpPnl = (perp?.open_positions ?? []).reduce((sum, p) =>
    sum + Number(p.pnl_unrealized), 0);
  const totalPnl = totalSpotPnl + totalPerpPnl;

  const activeWallet = execWallets?.available_wallets.find((w) => w.active)
    ?? execWallets?.available_wallets[0];

  const [aster, setAster] = useState<AsterWalletView | null>(null);
  useEffect(() => {
    let alive = true;
    fetchAsterWallet()
      .then((data) => { if (alive) setAster(data); })
      .catch(() => { if (alive) setAster(null); });
    return () => { alive = false; };
  }, []);

  return (
    <div className="space-y-4">

      {/* ── SUMMARY ── */}
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Spot" value={String(spot?.open_positions.length ?? 0)} />
        <Stat label="Perp" value={String(perp?.open_positions.length ?? 0)} />
        <Stat label="PnL aperto" value={fmtUsd(totalPnl)} tone={totalPnl >= 0 ? 'good' : 'bad'} />
      </div>

      {/* ── ASTER · venue Perp ── */}
      {aster?.configured && (
        <section className="space-y-2">
          <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">
            Aster · venue Perp{aster.subaccount_name ? ` · ${aster.subaccount_name}` : ''}
          </h3>
          <div className="rounded-xl bg-dark-800 px-4 py-3 space-y-2">
            <button
              onClick={() => aster.subaccount_address && copyAddress(aster.subaccount_address)}
              className="w-full text-left rounded-lg bg-dark-900 px-3 py-2"
            >
              <p className="text-[11px] text-gray-500">Sub-account · qui vanno versati i fondi</p>
              <p className="font-mono text-xs text-gray-300 break-all leading-relaxed">{aster.subaccount_address}</p>
              <p className="mt-0.5 text-[11px] text-accent-blue">
                {copied === aster.subaccount_address ? '✓ Copiato' : 'Tocca per copiare'}
              </p>
            </button>

            <div className="flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2">
              <div>
                <p className="text-sm font-semibold text-white">Saldo su Aster</p>
                <p className="text-[11px] text-gray-500">
                  wallet API {aster.api_wallet_address_short} · solo firma
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-white">
                  {aster.reachable ? `${aster.total_balance_usdt ?? '0.00'} USDT` : '—'}
                </p>
                <p className="text-[11px] text-gray-500">
                  {aster.open_positions != null ? `${aster.open_positions} posizioni` : ''}
                </p>
              </div>
            </div>

            {aster.reachable && aster.balances.length === 0 && (
              <p className="text-[11px] text-gray-500 px-1">
                Nessun asset: il sub-account non è ancora finanziato.
              </p>
            )}
            {aster.error && <p className="text-[11px] text-accent-red px-1">{aster.error}</p>}
          </div>
        </section>
      )}

      {/* ── WALLET ATTIVO ── */}
      <section className="space-y-2">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">
          Wallet attivo · {execWallets?.network ?? '—'} (chain {execWallets?.chain_id ?? '—'})
        </h3>
        {activeWallet ? (
          <div className="rounded-xl bg-dark-800 px-4 py-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="text-xs text-gray-500">{activeWallet.network}</p>
                <p className="text-xs text-gray-500">
                  Spot: {execWallets?.spot_active_provider} · Perp: {execWallets?.perp_active_provider}
                </p>
              </div>
              <span className="rounded-full bg-accent-green/15 px-2 py-0.5 text-xs font-semibold text-accent-green">attivo</span>
            </div>
            <button onClick={() => copyAddress(activeWallet.address)} className="w-full text-left rounded-lg bg-dark-900 px-3 py-2">
              <p className="font-mono text-xs text-gray-300 break-all leading-relaxed">{activeWallet.address}</p>
              <p className="mt-0.5 text-[11px] text-accent-blue">{copied === activeWallet.address ? '✓ Copiato' : 'Tocca per copiare'}</p>
            </button>
            {/* BNB balance */}
            <div className="flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2">
              <div>
                <p className="text-sm font-semibold text-white">BNB</p>
                <p className="text-[11px] text-gray-500">gas · {activeWallet.balance_status}</p>
              </div>
              <p className="font-mono text-sm font-bold text-accent-green">
                {activeWallet.balance_bnb ? `${parseFloat(activeWallet.balance_bnb).toFixed(6)} BNB` : '—'}
              </p>
            </div>
          </div>
        ) : (
          <EmptyState title="Wallet non configurato" detail="Aggiungi un indirizzo wallet dalla dashboard." />
        )}

        {/* altri wallet disponibili */}
        {(execWallets?.available_wallets.length ?? 0) > 1 && (
          <div className="space-y-1">
            <p className="px-1 text-[11px] text-gray-600 uppercase">Altri indirizzi</p>
            {execWallets!.available_wallets.filter((w) => !w.active).map((w) => (
              <button key={w.address} onClick={() => copyAddress(w.address)} className="w-full text-left rounded-lg bg-dark-800 px-3 py-2">
                <p className="font-mono text-xs text-gray-500 break-all">{w.address}</p>
                <p className="text-[11px] text-gray-600">{w.balance_bnb ? `${parseFloat(w.balance_bnb).toFixed(4)} BNB` : w.balance_status}</p>
              </button>
            ))}
          </div>
        )}
      </section>

      {/* ── POSIZIONI SPOT ── */}
      <section className="space-y-2">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">
          Posizioni spot aperte {spot?.open_positions.length ? `(${fmtUsd(totalSpotValue)} valore)` : ''}
        </h3>
        {(spot?.open_positions.length ?? 0) === 0
          ? <EmptyState title="Nessuna posizione spot" detail="Le posizioni aperte dall'agente appariranno qui." />
          : (spot?.open_positions ?? []).map((p) => {
              const pnl = Number(p.pnl_unrealized);
              const isGood = pnl >= 0;
              const entry = Number(p.entry_price);
              const now = Number(p.current_price);
              const size = Number(p.size);
              return (
                <div key={p.position_id} className="rounded-xl bg-dark-800 px-4 py-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-white">{p.asset}</p>
                      <p className="text-xs text-gray-500">Spot · {p.status}</p>
                    </div>
                    <div className={`text-right font-bold ${isGood ? 'text-accent-green' : 'text-accent-red'}`}>
                      <p>{isGood ? '+' : ''}{fmtUsd(pnl)}</p>
                      <p className="text-xs">{p.pnl_pct ?? '+0.00'}%</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-1 text-xs text-gray-400">
                    <span>Size {size.toFixed(6)}</span>
                    <span>Entry {fmtPrice(entry)}</span>
                    <span>Now {fmtPrice(now)}</span>
                  </div>
                  {(p.stop_loss || p.take_profit_1) && (
                    <div className="grid grid-cols-2 gap-1 text-xs text-gray-500">
                      {p.stop_loss && <span>SL {fmtPrice(p.stop_loss)}</span>}
                      {p.take_profit_1 && <span>TP1 {fmtPrice(p.take_profit_1)}</span>}
                      {p.take_profit_2 && <span>TP2 {fmtPrice(p.take_profit_2)}</span>}
                    </div>
                  )}
                  <div className="mt-1 grid grid-cols-2 gap-1 text-xs text-gray-500">
                    <span>Mode: <span className={!p.fee_mode || p.fee_mode === 'none' ? 'text-gray-400' : 'text-accent-yellow'}>{p.fee_mode === 'none' ? 'nessuna' : p.fee_mode === 'all' ? 'swap+slip' : p.fee_mode ?? '-'}</span></span>
                    <span>Swap fee {p.swap_fee_usd != null ? fmtUsd(p.swap_fee_usd) : '$0.00'}</span>
                    <span>Slip. {p.slippage_usd != null ? fmtUsd(p.slippage_usd) : '$0.00'}</span>
                  </div>
                </div>
              );
            })}
      </section>

      {/* ── POSIZIONI PERP ── */}
      <section className="space-y-2">
        <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">
          Posizioni perp aperte {perp?.open_positions.length ? `(PnL ${fmtUsd(totalPerpPnl)})` : ''}
        </h3>
        {(perp?.open_positions.length ?? 0) === 0
          ? <EmptyState title="Nessuna posizione perp" detail="Le posizioni long/short appariranno qui." />
          : (perp?.open_positions ?? []).map((p) => {
              const pnl = Number(p.pnl_unrealized);
              const isGood = pnl >= 0;
              return (
                <div key={p.position_id} className="rounded-xl bg-dark-800 px-4 py-3 space-y-2">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-white">{p.asset} <span className="text-accent-blue">{p.side}</span> {p.leverage}x</p>
                      <p className="text-xs text-gray-500">Perp · {p.status}</p>
                    </div>
                    <div className={`text-right font-bold ${isGood ? 'text-accent-green' : 'text-accent-red'}`}>
                      <p>{isGood ? '+' : ''}{fmtUsd(pnl)}</p>
                      <p className="text-xs">{p.pnl_pct ?? '+0.00'}%</p>
                    </div>
                  </div>
                  <div className="grid grid-cols-3 gap-1 text-xs text-gray-400">
                    <span>Size {Number(p.size).toFixed(4)}</span>
                    <span>Entry {fmtPriceFull(p.entry_price)}</span>
                    <span>Now {fmtPriceFull(p.current_price)}</span>
                  </div>
                  {(p.stop_loss || p.liquidation_price) && (
                    <div className="grid grid-cols-2 gap-1 text-xs text-gray-500">
                      {p.stop_loss && <span>SL {fmtPrice(p.stop_loss)}</span>}
                      {p.liquidation_price && <span className="text-accent-red">Liq {fmtPrice(p.liquidation_price)}</span>}
                    </div>
                  )}
                  <div className="mt-1 grid grid-cols-2 gap-1 text-xs text-gray-500">
                    <span>Margin {p.margin_usd != null ? fmtUsd(p.margin_usd) : '$0.00'}</span>
                    <span>Mode: <span className={!p.fee_mode || p.fee_mode === 'none' ? 'text-gray-400' : p.fee_mode === 'maker' ? 'text-accent-green' : 'text-accent-yellow'}>{p.fee_mode ?? '-'}</span></span>
                    <span>Fee {p.opening_fee_usd != null ? fmtUsd(p.opening_fee_usd) : '$0.00'}</span>
                    <span>Slip. {p.slippage_usd != null ? fmtUsd(p.slippage_usd) : '$0.00'}</span>
                    <span className={Number(p.funding_accrued_usd ?? 0) >= 0 ? 'text-accent-green' : 'text-accent-red'}>Fund. {p.funding_accrued_usd != null ? fmtUsd(p.funding_accrued_usd) : '$0.00'}</span>
                  </div>
                </div>
              );
            })}
      </section>

    </div>
  );
};

type CoinSubTab = 'master' | 'spot' | 'perp';

const CoinsPane: FC<{
  eligibleTokens: string[];
  selectedAiSymbols: Set<string>;
  adminToken: string;
  saving: boolean;
  error: string;
  onToggle: (symbol: string) => void;
}> = ({ eligibleTokens, selectedAiSymbols, adminToken, saving, error, onToggle }) => {
  const [subTab, setSubTab] = useState<CoinSubTab>('master');
  const [query, setQuery] = useState('');
  const [spotData, setSpotData] = useState<AgentMarketWatchlistResponse | null>(null);
  const [perpData, setPerpData] = useState<AgentMarketWatchlistResponse | null>(null);
  const [marketSaving, setMarketSaving] = useState(false);
  const [marketError, setMarketError] = useState('');
  const [ranking, setRanking] = useState<WatchlistRanking>({});

  useEffect(() => {
    void fetchAgentWatchlist().then((d) => setRanking(d.ranking ?? {})).catch(() => undefined);
  }, []);

  useEffect(() => {
    // Ricarica spot/perp quando cambia la master: rimuovendo un token dal master il
    // backend lo elimina (prune) anche da spot/perp, ma senza questo refresh i conteggi
    // client resterebbero fermi ai valori vecchi (es. spot 40 invece di 38).
    void fetchSpotWatchlist().then(setSpotData).catch(() => undefined);
    void fetchPerpWatchlist().then(setPerpData).catch(() => undefined);
  }, [selectedAiSymbols]);

  const normalizedQuery = query.trim().toUpperCase();
  const rankOf = (symbol: string): number | null => ranking[symbol.toUpperCase()]?.rank ?? null;
  const byMarketCap = (symbols: string[]): string[] =>
    [...symbols].sort((a, b) => {
      const ra = rankOf(a);
      const rb = rankOf(b);
      if (ra != null && rb != null) return ra - rb;
      if (ra != null) return -1;
      if (rb != null) return 1;
      return a.localeCompare(b);
    });

  // La master arriva dallo stato App-level (selectedAiSymbols), popolato da un solo fetch
  // al mount di App: se quella singola chiamata fallisce (cold start, timeout) il catch la
  // azzera senza retry, e spot/perp mostrerebbero "Master vuota" pur avendo l'agente 40 coin.
  // Fallback robusto: usa la master autorevole (master_tokens) che gli endpoint spot/perp —
  // ri-fetchati a ogni apertura della scheda — restituiscono già.
  const masterFromState = eligibleTokens.filter((s) => selectedAiSymbols.has(s.toUpperCase()));
  const masterFromApi = spotData?.master_tokens ?? perpData?.master_tokens ?? [];
  const masterTokens = byMarketCap(masterFromState.length > 0 ? masterFromState : masterFromApi);
  const filteredEligible = byMarketCap(eligibleTokens.filter((s) => s.toUpperCase().includes(normalizedQuery)));

  const spotSelected = useMemo(() => new Set((spotData?.selected_tokens ?? []).map((s) => s.toUpperCase())), [spotData]);
  const perpSelected = useMemo(() => new Set((perpData?.selected_tokens ?? []).map((s) => s.toUpperCase())), [perpData]);

  const handleMarketToggle = async (symbol: string, market: 'spot' | 'perp') => {
    if (!adminToken || marketSaving) return;
    setMarketSaving(true);
    setMarketError('');
    try {
      if (market === 'spot') {
        const current = new Set(spotData?.selected_tokens ?? []);
        if (current.has(symbol)) current.delete(symbol); else current.add(symbol);
        const result = await updateSpotWatchlist([...current], adminToken);
        setSpotData((prev) => ({ ...result, availability: result.availability ?? prev?.availability }));
      } else {
        const current = new Set(perpData?.selected_tokens ?? []);
        if (current.has(symbol)) current.delete(symbol); else current.add(symbol);
        const result = await updatePerpWatchlist([...current], adminToken);
        setPerpData((prev) => ({ ...result, availability: result.availability ?? prev?.availability }));
      }
    } catch (e) {
      const detail = e instanceof Error ? e.message : String(e);
      setMarketError(`Errore salvataggio watchlist — ${detail}`);
    } finally {
      setMarketSaving(false);
    }
  };

  const disabled = !adminToken || saving;
  const marketDisabled = !adminToken || marketSaving;

  return (
    <div className="space-y-4">
      <section className="rounded-xl bg-dark-800 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-white">Agent coins</h3>
            <p className="mt-0.5 truncate text-xs text-gray-500">
              {subTab === 'master' && `Eligible ${eligibleTokens.length} · Master ${masterTokens.length}`}
              {subTab === 'spot' && `Master ${masterTokens.length} · Spot ${spotData?.selected_count ?? 0}`}
              {subTab === 'perp' && `Master ${masterTokens.length} · Perp ${perpData?.selected_count ?? 0}`}
            </p>
          </div>
          <span className="rounded-full bg-accent-yellow/15 px-2 py-1 text-xs font-semibold text-accent-yellow">
            {subTab === 'master' ? masterTokens.length : subTab === 'spot' ? (spotData?.selected_count ?? 0) : (perpData?.selected_count ?? 0)}
          </span>
        </div>
        {!adminToken && <p className="mt-3 rounded-lg bg-dark-900 px-3 py-2 text-xs text-gray-500">Inserisci admin token in Setup per modificare.</p>}
        {(error || marketError) && <p className="mt-3 rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{marketError || error}</p>}
        <div className="mt-3 grid grid-cols-3 gap-1">
          {(['master', 'spot', 'perp'] as CoinSubTab[]).map((t) => (
            <button
              key={t}
              onClick={() => { setSubTab(t); setQuery(''); }}
              className={`rounded-lg py-1.5 text-xs font-semibold capitalize transition-colors ${subTab === t ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'}`}
            >
              {t}
            </button>
          ))}
        </div>
      </section>

      {subTab === 'master' && (
        <>
          <section className="space-y-2">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Selezionate</h3>
            {masterTokens.length > 0 ? (
              <div className="grid grid-cols-2 gap-2">
                {masterTokens.map((symbol) => (
                  <TokenToggle key={`sel-${symbol}`} symbol={symbol} selected disabled={disabled} onToggle={onToggle} rank={rankOf(symbol)} />
                ))}
              </div>
            ) : (
              <EmptyState title="Nessuna coin attiva" detail="Seleziona una coin tradabile per passarla all'agente." />
            )}
          </section>
          <section className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Eligible</h3>
              {saving && <span className="text-xs text-accent-yellow">Saving</span>}
            </div>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search token"
              className="w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
            />
            <div className="grid grid-cols-2 gap-2">
              {filteredEligible.map((symbol) => (
                <TokenToggle key={symbol} symbol={symbol} selected={selectedAiSymbols.has(symbol.toUpperCase())} disabled={disabled} onToggle={onToggle} rank={rankOf(symbol)} />
              ))}
            </div>
            {filteredEligible.length === 0 && <EmptyState title="Nessun token trovato" detail="La ricerca filtra solo l'universo eligible." />}
          </section>
        </>
      )}

      {(subTab === 'spot' || subTab === 'perp') && (() => {
        const isSpot = subTab === 'spot';
        const selected = isSpot ? spotSelected : perpSelected;
        const activeMasterTokens = masterTokens.filter((s) => s.toUpperCase().includes(normalizedQuery));
        const availabilityMap = (isSpot ? spotData : perpData)?.availability;
        const availabilityFor = (symbol: string): VenueAvailability => {
          const entry = availabilityMap?.[symbol.toUpperCase()];
          const value = isSpot ? entry?.spot : entry?.perp;
          return value ?? { venue: isSpot ? 'pancakeswap' : 'aster', status: 'unknown' };
        };
        const blockedCount = activeMasterTokens.filter(
          (s) => availabilityFor(s).status === 'unavailable' && !selected.has(s.toUpperCase()),
        ).length;
        return (
          <section className="space-y-2">
            <p className="px-1 text-xs text-gray-500">
              Seleziona le coin dalla master watchlist da assegnare al mercato <span className="font-semibold text-white">{subTab.toUpperCase()}</span>.
              {' '}Venue: <span className="font-semibold text-white">{isSpot ? 'PancakeSwap' : 'Aster'}</span>.
            </p>
            {blockedCount > 0 && (
              <p className="px-1 text-xs text-accent-red">
                {blockedCount} {blockedCount === 1 ? 'coin non è quotata' : 'coin non sono quotate'} su {isSpot ? 'PancakeSwap' : 'Aster'}: non selezionabili.
              </p>
            )}
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search token"
              className="w-full rounded-lg border border-dark-600 bg-dark-800 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
            />
            {marketSaving && <p className="text-xs text-accent-yellow">Saving…</p>}
            {masterTokens.length === 0 ? (
              <EmptyState title="Master watchlist vuota" detail="Aggiungi prima coin alla master watchlist." />
            ) : (
              <div className="grid grid-cols-2 gap-2">
                {activeMasterTokens.map((symbol) => (
                  <TokenToggle
                    key={symbol}
                    symbol={symbol}
                    selected={selected.has(symbol.toUpperCase())}
                    disabled={marketDisabled}
                    onToggle={(s) => void handleMarketToggle(s, subTab)}
                    availability={availabilityFor(symbol)}
                    rank={rankOf(symbol)}
                  />
                ))}
              </div>
            )}
            {activeMasterTokens.length === 0 && masterTokens.length > 0 && (
              <EmptyState title="Nessun token trovato" detail="La ricerca filtra la master watchlist." />
            )}
          </section>
        );
      })()}
    </div>
  );
};

type SetupTab = 'generale' | 'spot' | 'perp' | 'sistema' | 'bank';
const SETUP_TABS: Array<{ id: SetupTab; label: string }> = [
  { id: 'generale', label: 'Generale' },
  { id: 'spot', label: 'Spot' },
  { id: 'perp', label: 'Perp' },
  { id: 'bank', label: 'Bank' },
  { id: 'sistema', label: 'Sistema' },
];

const BankSettingsPane: FC<{ adminToken: string }> = ({ adminToken }) => {
  const [s, setS] = useState<ReserveSettings | null>(null);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    fetchReserveSettings().then((r) => setS(r.settings)).catch(() => setMsg('Caricamento impostazioni non riuscito'));
  }, []);

  if (!s) return <div className="py-6 text-center text-xs text-gray-500">{msg || 'Caricamento…'}</div>;

  const patch = (p: Partial<ReserveSettings>) => { setS({ ...s, ...p }); setDirty(true); };
  const setWeight = (symbol: string, weight_pct: number) => {
    patch({ target_weights: s.target_weights.map((w) => (w.symbol === symbol ? { ...w, weight_pct } : w)) });
  };
  const weightSum = s.target_weights.reduce((acc, w) => acc + Number(w.weight_pct || 0), 0);
  const weightsOk = Math.abs(weightSum - 100) < 0.5;

  const save = async () => {
    if (!adminToken || !weightsOk) return;
    setSaving(true); setMsg('');
    try {
      const r = await saveReserveSettings(s, adminToken);
      setS(r.settings); setDirty(false); setMsg('Salvato');
    } catch {
      setMsg('Salvataggio non riuscito');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <ToggleInput label="Riserva attiva" checked={s.enabled} onChange={(enabled) => patch({ enabled })} />
      <ToggleInput label="Ribilanciamento automatico" checked={s.auto_rebalance} onChange={(auto_rebalance) => patch({ auto_rebalance })} />
      <ToggleInput label="Sweep profitti automatico" checked={s.sweep_enabled} onChange={(sweep_enabled) => patch({ sweep_enabled })} />

      <section className="rounded-xl bg-dark-800 px-4 py-3 space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-semibold uppercase text-gray-500">Pesi target</h4>
          <span className={`text-[11px] font-semibold ${weightsOk ? 'text-accent-green' : 'text-accent-red'}`}>somma {weightSum.toFixed(0)}%</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {s.target_weights.map((w) => (
            <NumberInput key={w.symbol} label={`${w.symbol} %`} value={Number(w.weight_pct)} step={1} onChange={(v) => setWeight(w.symbol, v)} />
          ))}
        </div>
      </section>

      <section className="rounded-xl bg-dark-800 px-4 py-3 grid grid-cols-2 gap-2">
        <NumberInput label="Sweep %" value={s.sweep_pct} step={1} onChange={(sweep_pct) => patch({ sweep_pct })} />
        <NumberInput label="Sweep ogni (ore)" value={s.sweep_interval_hours} step={1} onChange={(sweep_interval_hours) => patch({ sweep_interval_hours })} />
        <NumberInput label="Deploy ogni (giorni)" value={s.deploy_interval_days} step={1} onChange={(deploy_interval_days) => patch({ deploy_interval_days })} />
        <NumberInput label="Deploy se cash ≥ $" value={s.deploy_min_cash_usd} step={5} onChange={(deploy_min_cash_usd) => patch({ deploy_min_cash_usd })} />
        <NumberInput label="Banda drift %" value={s.drift_band_pct} step={0.5} onChange={(drift_band_pct) => patch({ drift_band_pct })} />
        <NumberInput label="Transfer minimo $" value={s.min_transfer_usd} step={1} onChange={(min_transfer_usd) => patch({ min_transfer_usd })} />
        <NumberInput label="Cooldown prelievi (ore)" value={Math.round(s.withdrawal_cooldown_minutes / 60)} step={1} onChange={(v) => patch({ withdrawal_cooldown_minutes: Math.max(0, Math.round(v)) * 60 })} />
      </section>
      <ToggleInput
        label="Blocca prelievi durante blocco drawdown"
        checked={s.block_withdrawal_during_drawdown_guard}
        onChange={(block_withdrawal_during_drawdown_guard) => patch({ block_withdrawal_during_drawdown_guard })}
      />

      {msg && <p className={`text-xs ${msg === 'Salvato' ? 'text-accent-green' : 'text-accent-red'}`}>{msg}</p>}
      <button
        onClick={save}
        disabled={!adminToken || saving || !dirty || !weightsOk}
        className="w-full rounded-lg bg-accent-yellow px-3 py-2.5 text-sm font-bold text-dark-900 disabled:opacity-40"
      >
        {saving ? 'Salvataggio…' : 'Salva impostazioni Bank'}
      </button>
      {!adminToken && <p className="text-xs text-gray-600">Richiede admin token salvato.</p>}
    </div>
  );
};

const SetupPane: FC<{
  settings: AgentMobileSettings;
  onSettings: (settings: AgentMobileSettings) => void;
  adminToken: string;
  onAdminToken: (value: string) => void;
  validation: CredentialValidationResponse | null;
  agentStatus: AgentStatus | null;
  saving: boolean;
  actionError: string;
  dirty: boolean;
  onSave: () => void;
  onValidate: () => void;
  onKill: (state: KillSwitchState) => void;
  onCloseAll: () => void;
  onAdjustEquity: (amount: number) => void;
}> = ({
  settings,
  onSettings,
  adminToken,
  onAdminToken,
  validation,
  agentStatus,
  saving,
  actionError,
  dirty,
  onSave,
  onValidate,
  onKill,
  onCloseAll,
  onAdjustEquity,
}) => {
  const patch = (partial: Partial<AgentMobileSettings>) => onSettings({ ...settings, ...partial });
  const [showHelp, setShowHelp] = useState(() => {
    try { return localStorage.getItem('cs_show_help_tips') !== 'false'; } catch { return true; }
  });
  const toggleHelp = (v: boolean) => {
    setShowHelp(v);
    try { localStorage.setItem('cs_show_help_tips', String(v)); } catch { /* noop */ }
  };
  const h = showHelp;
  const [equityInput, setEquityInput] = useState('');
  const [asterState, setAsterState] = useState<'idle' | 'testing'>('idle');
  const [asterReport, setAsterReport] = useState<AsterConnectionReport | null>(null);
  const [asterError, setAsterError] = useState<string | null>(null);
  const handleAsterTest = async () => {
    if (!adminToken || asterState === 'testing') return;
    setAsterState('testing');
    setAsterError(null);
    try {
      setAsterReport(await testAsterConnection(adminToken));
    } catch (err: any) {
      setAsterReport(null);
      setAsterError(err?.message ?? 'Errore durante il test');
    } finally {
      setAsterState('idle');
    }
  };
  const equityValue = Number(equityInput);
  const equityValid = equityInput.trim() !== '' && Number.isFinite(equityValue) && equityValue !== 0;
  const [setupTab, setSetupTab] = useState<SetupTab>('generale');

  const [adminCheck, setAdminCheck] = useState<'idle' | 'checking' | 'valid' | 'invalid' | 'unreachable'>('idle');
  useEffect(() => {
    if (!adminToken) { setAdminCheck('idle'); return; }
    setAdminCheck('checking');
    let cancelled = false;
    const timer = window.setTimeout(async () => {
      try {
        const ok = await verifyAdminToken(adminToken);
        if (!cancelled) setAdminCheck(ok ? 'valid' : 'invalid');
      } catch {
        if (!cancelled) setAdminCheck('unreachable');
      }
    }, 600);
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [adminToken]);

  return (
    <div className="space-y-4">
      {/* Always visible: Emergency close */}
      <section className="rounded-xl border border-accent-red/30 bg-dark-800 px-4 py-4 space-y-3">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-white">Risk · Chiusura di emergenza</h3>
          <p className="mt-0.5 text-xs text-gray-500">Chiude tutte le posizioni spot e perp al prezzo di mercato e mette l'agente in pausa (hard stop). Riprende solo quando premi Riprendi.</p>
        </div>
        <button
          onClick={onCloseAll}
          disabled={!adminToken || saving}
          className="w-full rounded-lg bg-accent-red px-3 py-3 text-sm font-bold text-white disabled:opacity-40"
        >
          {saving ? 'Esecuzione...' : '⛔ Chiudi tutto & metti in pausa'}
        </button>
        <button
          onClick={() => onKill('running')}
          disabled={!adminToken || saving || agentStatus?.kill_switch === 'running'}
          className="w-full rounded-lg bg-accent-green/20 px-3 py-2.5 text-sm font-semibold text-accent-green disabled:opacity-40"
        >
          ▶ Riprendi agente
        </button>
        {!adminToken && <p className="text-xs text-gray-600">Richiede admin token salvato.</p>}
      </section>

      {/* Tab bar */}
      <div className="grid grid-cols-5 gap-1">
        {SETUP_TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setSetupTab(t.id)}
            className={`rounded-lg py-1.5 text-xs font-semibold transition-colors ${
              setupTab === t.id ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400 hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab: Bank */}
      {setupTab === 'bank' && <BankSettingsPane adminToken={adminToken} />}

      {/* Tab: Generale */}
      {setupTab === 'generale' && (
        <>
          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">General</h3>
            <div className="grid grid-cols-2 gap-3">
              <SelectInput label="Mode" showHelp={h} help={'Quanta libertà ha l\'agente:\n\nConservative — solo i segnali migliori\nSemi-auto — più operazioni, filtri più larghi\nFull auto — massima autonomia'} value={settings.mode} onChange={(mode) => patch({ mode })} options={[
                { value: 'conservative', label: 'Conservative' },
                { value: 'semi_autonomous', label: 'Semi-auto' },
                { value: 'full_autonomous', label: 'Full auto' },
              ]} />
              <SelectInput label="Market" showHelp={h} help={'Su quali mercati opera:\n\nSpot — compra la moneta vera, niente leva\nPerp — contratti con leva, guadagna anche al ribasso\nBoth — entrambi i mercati'} value={settings.markets_enabled} onChange={(markets_enabled) => patch({ markets_enabled })} options={[
                { value: 'spot', label: 'Spot' },
                { value: 'perp', label: 'Perp' },
                { value: 'both', label: 'Both' },
              ]} />
              <SelectInput label="Execution" showHelp={h} help={'Se le operazioni sono reali o simulate:\n\nDry run — simulate, nessun soldo vero in gioco\nLive — ordini veri sull\'exchange'} value={settings.execution_mode} onChange={(execution_mode) => patch({ execution_mode })} options={[
                { value: 'dry_run', label: 'Dry-run' },
                { value: 'live', label: 'Live' },
              ]} />
              <NumberInput label="Test scaling %" showHelp={h} help="Riduce la dimensione di ogni operazione a questa percentuale. Serve per provare la strategia con importi ridotti: a 10% ogni trade vale un decimo del normale." value={settings.test_scaling_pct} onChange={(test_scaling_pct) => patch({ test_scaling_pct })} />
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Filtri mercato</h3>
            <ToggleInput
              label="Filtro regime mercato Spot"
              showHelp={h} help={'Freno d\'emergenza: blocca i nuovi acquisti spot quando BTC (15m) è in crollo forte — sotto la EMA50 e a nuovi minimi. Riparte solo quando BTC richiude sopra la EMA50. Interviene solo nei ribassi seri, il resto del tempo lascia passare.'}
              checked={settings.spot_market_regime_filter_enabled}
              onChange={(spot_market_regime_filter_enabled) => patch({ spot_market_regime_filter_enabled })}
            />
            <ToggleInput
              label="Filtro inversione mercato Spot"
              showHelp={h} help="Blocca i nuovi acquisti spot finché BTC (15m) non conferma una salita: 2 candele verdi sopra la EMA10. Più selettivo — entra solo con BTC in ripresa confermata — ma riduce parecchio le operazioni, soprattutto quando BTC è laterale. Si somma al filtro regime (crolli): tenerli entrambi è quasi ridondante."
              checked={settings.spot_market_reversal_filter_enabled}
              onChange={(spot_market_reversal_filter_enabled) => patch({ spot_market_reversal_filter_enabled })}
            />
            <ToggleInput
              label="Filtro inversione mercato Perp"
              showHelp={h} help="Blocca le nuove entrate quando il mercato sta girando contro la direzione del segnale. Meno operazioni, ma evita di entrare proprio mentre il trend si ribalta."
              checked={settings.perp_market_reversal_filter_enabled}
              onChange={(perp_market_reversal_filter_enabled) => patch({ perp_market_reversal_filter_enabled })}
            />
          </section>

          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Risk globale</h3>
            <ToggleInput
              label="Allarme drawdown"
              showHelp={h} help="Manda una notifica quando la perdita dal massimo raggiunto supera la soglia. Non ferma nulla: avvisa e basta."
              checked={settings.drawdown_alert_enabled}
              onChange={(drawdown_alert_enabled) => patch({ drawdown_alert_enabled })}
            />
            <div className="grid grid-cols-2 gap-3">
              <NumberInput label="Daily loss %" showHelp={h} help="Perdita massima in una giornata, in percentuale sul capitale. Raggiunta la soglia l'agente smette di aprire nuove posizioni fino al giorno dopo. Si scrive negativa: −8 significa −8%." value={settings.daily_loss_limit_pct} onChange={(daily_loss_limit_pct) => patch({ daily_loss_limit_pct })} />
              <NumberInput label="Drawdown cap %" showHelp={h} help={'Perdita massima tollerata dal picco di capitale. Superata, l\'agente si ferma del tutto e non riapre finché non lo riavvii tu. Si scrive negativa: −15 significa −15%.'} value={settings.drawdown_cap_pct} onChange={(drawdown_cap_pct) => patch({ drawdown_cap_pct })} />
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Grafico trade</h3>
            <div className="grid grid-cols-2 gap-3">
              <NumberInput label="Candele post-chiusura (0=off)" showHelp={h} help={'Quante candele mostrare nel grafico dopo la chiusura di un trade, per vedere com\'è andata dopo l\'uscita. Zero le nasconde.'} value={settings.post_close_candles} step={1} onChange={(post_close_candles) => patch({ post_close_candles: Math.round(post_close_candles) })} />
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Min pool liquidity</h3>
            <NumberInput label="Min pool liquidity $" value={settings.min_pool_liquidity_usd} onChange={(min_pool_liquidity_usd) => patch({ min_pool_liquidity_usd })} />
          </section>
        </>
      )}

      {/* Tab: Spot */}
      {setupTab === 'spot' && (
        <>
          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Spot — risk</h3>
            <div className="grid grid-cols-2 gap-3">
              <NumberInput label="Size %" showHelp={h} help="Quanta parte del capitale impegnare in ogni singola operazione spot. Al 4% con 1000$ investi 40$ per trade." value={settings.spot_capital_per_trade_pct} onChange={(spot_capital_per_trade_pct) => patch({ spot_capital_per_trade_pct })} />
              <NumberInput label="Rischio %" showHelp={h} help="Quanto sei disposto a perdere su una singola operazione, in percentuale sul capitale. Da qui viene calcolata la dimensione della posizione: rischio più basso, posizione più piccola." value={settings.spot_per_trade_pct} step={0.1} onChange={(spot_per_trade_pct) => patch({ spot_per_trade_pct })} />
              <NumberInput label="Max posizioni" showHelp={h} help="Quante posizioni spot possono restare aperte insieme. Più alto significa più diversificazione ma anche più capitale immobilizzato." value={settings.spot_max_open_positions} onChange={(spot_max_open_positions) => patch({ spot_max_open_positions })} />
              <NumberInput label="Exposure %" showHelp={h} help="Tetto al capitale investito in tutte le posizioni spot sommate. Impedisce di ritrovarsi con tutto il capitale sul mercato nello stesso momento." value={settings.spot_max_exposure_pct} onChange={(spot_max_exposure_pct) => patch({ spot_max_exposure_pct })} />
              <NumberInput label="Slippage %" showHelp={h} help={'Scarto massimo accettato fra il prezzo previsto e quello di esecuzione. Oltre questa soglia l\'ordine viene annullato invece di essere eseguito a un prezzo peggiore.'} value={settings.spot_max_slippage_pct} step={0.1} onChange={(spot_max_slippage_pct) => patch({ spot_max_slippage_pct })} />
              <NumberInput label="Cooldown min" showHelp={h} help="Minuti di attesa prima di riaprire sullo stesso asset dopo una chiusura. Evita di rientrare subito sullo stesso movimento." value={settings.spot_cooldown_minutes} onChange={(spot_cooldown_minutes) => patch({ spot_cooldown_minutes })} />
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Spot — strategia</h3>
            <div className="grid grid-cols-2 gap-3">
              <NumberInput label="Confidence" showHelp={h} help="Quanto deve essere forte un segnale per essere accettato. Alzarlo riduce le operazioni ma tiene solo le più convincenti." value={settings.spot_confidence_threshold} step={0.01} onChange={(spot_confidence_threshold) => patch({ spot_confidence_threshold })} />
              <NumberInput label="Vol trigger %" showHelp={h} help={'Movimento minimo di prezzo perché una situazione venga considerata un\'occasione. Sotto questa soglia il mercato è troppo fermo per operare.'} value={settings.spot_volatility_trigger_pct} onChange={(spot_volatility_trigger_pct) => patch({ spot_volatility_trigger_pct })} />
              <NumberInput label="Rel volume" showHelp={h} help="Quante volte il volume deve superare la sua media per confermare il segnale. A 1.5 serve volume una volta e mezza il normale: filtra i movimenti senza partecipazione." value={settings.spot_relative_volume_threshold} step={0.1} onChange={(spot_relative_volume_threshold) => patch({ spot_relative_volume_threshold })} />
              <NumberInput label="ATR stop" showHelp={h} help={'Distanza dello stop loss dall\'ingresso, misurata in ATR (la volatilità media). Più alto significa stop più largo: meno stop presi per caso, ma perdite più grandi quando scatta.'} value={settings.spot_atr_stop_multiplier} step={0.1} onChange={(spot_atr_stop_multiplier) => patch({ spot_atr_stop_multiplier })} />
              <NumberInput label="TP1 (ATR)" showHelp={h} help={'Primo target: a quanti ATR dall\'ingresso chiudere la prima parte della posizione. Es. 2.5 = chiudi il 30% quando il guadagno raggiunge 2.5× la volatilità media.'} value={settings.spot_tp1_atr_multiplier} step={0.1} onChange={(spot_tp1_atr_multiplier) => patch({ spot_tp1_atr_multiplier })} />
              <NumberInput label="TP2 (ATR)" showHelp={h} help={'Secondo target: a quanti ATR dall\'ingresso chiudere il resto della posizione. Deve essere più alto di TP1 per lasciare correre i trade vincenti.'} value={settings.spot_tp2_atr_multiplier} step={0.1} onChange={(spot_tp2_atr_multiplier) => patch({ spot_tp2_atr_multiplier })} />
              <NumberInput label="Breakeven ATR" showHelp={h} help={'A quanti ATR di guadagno spostare lo stop al prezzo d\'ingresso (breakeven). Più alto = dai più respiro al trade prima di proteggere. Più basso = proteggi prima ma rischi uscite premature.'} value={settings.spot_breakeven_trigger_atr} step={0.1} onChange={(spot_breakeven_trigger_atr) => patch({ spot_breakeven_trigger_atr })} />
              <NumberInput label="Trailing ATR" showHelp={h} help={'Distanza del trailing stop dal prezzo massimo raggiunto, in ATR. Più basso = proteggi il profitto prima ma esci sui rimbalzi. Più alto = lasci correre ma restituisci di più.'} value={settings.spot_trailing_atr_multiplier} step={0.1} onChange={(spot_trailing_atr_multiplier) => patch({ spot_trailing_atr_multiplier })} />
              <NumberInput label="Buffer Min20 %" showHelp={h} help="Cuscinetto sotto il minimo delle ultime candele, quando lo stop è di tipo strutturale. Serve a non farsi prendere lo stop per un soffio." value={settings.spot_structural_stop_buffer_pct} step={0.1} onChange={(spot_structural_stop_buffer_pct) => patch({ spot_structural_stop_buffer_pct })} />
              <NumberInput label="Chiudi a TP1 %" showHelp={h} help="Quanta parte della posizione chiudere al primo obiettivo. Al 50% incassi metà e lasci correre il resto." value={settings.spot_tp1_close_pct} step={5} onChange={(spot_tp1_close_pct) => patch({ spot_tp1_close_pct })} />
              <NumberInput label="Time Stop ore" showHelp={h} help="Dopo quante ore chiudere una posizione che non è andata né a target né a stop. Libera capitale bloccato in operazioni che non si muovono." value={settings.spot_time_stop_hours} step={1} onChange={(spot_time_stop_hours) => patch({ spot_time_stop_hours: Math.round(spot_time_stop_hours) })} />
              <NumberInput label="Max stop dist %" showHelp={h} help={'Soglia del filtro volatilità: se lo stop dista dall\'ingresso più di questa percentuale, l\'operazione viene saltata. Taglia i token ad altissima volatilità (stop -5/-12%) che passano gli altri filtri ma cancellano decine di vincite. Più basso = più selettivo. Richiede il toggle "Filtro volatilità" attivo.'} value={settings.spot_max_stop_distance_pct} step={0.5} onChange={(spot_max_stop_distance_pct) => patch({ spot_max_stop_distance_pct })} />
              <SelectInput label="Fee mode (dry-run)" showHelp={h} help={'Quali costi simulare nel dry run:\n\nSwap fee + Slippage — realistico, 0.15%\nNessuna — strategia lorda, senza costi'} value={settings.spot_fee_mode} onChange={(v) => patch({ spot_fee_mode: v as 'all' | 'none' })} options={[
                { value: 'all', label: 'Swap fee + Slippage — 0.15%' },
                { value: 'none', label: 'Nessuna (strategia lorda)' },
              ]} />
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Spot — protezioni</h3>
            <ToggleInput
              label="Breakeven Spot"
              showHelp={h} help={'Sposta lo stop al prezzo d\'ingresso quando il trade è in guadagno, così l\'operazione non può più chiudere in perdita.'}
              checked={settings.spot_breakeven_enabled}
              onChange={(spot_breakeven_enabled) => patch({ spot_breakeven_enabled })}
            />
            <SelectInput
              label="Modalità breakeven Spot"
              showHelp={h} help={'Quando spostare lo stop a pareggio:\n\nATR — appena il guadagno raggiunge la soglia di volatilità\nSolo dopo TP1 — solo dopo aver incassato il primo obiettivo'}
              value={settings.spot_breakeven_mode}
              onChange={(v) => patch({ spot_breakeven_mode: v })}
              options={[
                { value: 'atr', label: 'ATR (attuale)' },
                { value: 'tp1', label: 'Solo dopo TP1' },
              ]}
            />
            <SelectInput
              label="Stop Loss Spot"
              showHelp={h} help={'Come calcolare lo stop loss:\n\nATR — distanza fissa basata sulla volatilità\nMinimo 20 candele — sotto il minimo recente, stop più largo e più aderente al grafico'}
              value={settings.spot_sl_mode}
              onChange={(v) => patch({ spot_sl_mode: v })}
              options={[
                { value: 'atr', label: 'ATR (attuale)' },
                { value: 'lowest', label: 'Minimo 20 candele' },
              ]}
            />
            <NumberInput label="Lookback candele SL" showHelp={h} help="Quante candele guardare indietro per trovare il minimo strutturale da usare come stop." value={settings.spot_structural_stop_lookback_candles} step={1} onChange={(spot_structural_stop_lookback_candles) => patch({ spot_structural_stop_lookback_candles: Math.round(spot_structural_stop_lookback_candles) })} />
            <ToggleInput
              label="Trailing Stop Spot"
              showHelp={h} help="Fa salire lo stop dietro al prezzo mentre il trade guadagna, per proteggere il profitto già maturato. Lo stop non scende mai."
              checked={settings.spot_trailing_enabled}
              onChange={(spot_trailing_enabled) => patch({ spot_trailing_enabled })}
            />
            <ToggleInput
              label="Trailing solo dopo TP1"
              showHelp={h} help={'Se attivo: il trailing parte SOLO dopo aver raggiunto il primo obiettivo (TP1). Prima il trade respira, protetto solo da stop e pareggio, e può correre fino al TP2 senza essere strozzato sui piccoli rimbalzi. Se disattivo: il trailing è attivo da subito (comportamento storico), più protettivo ma taglia prima le vincite.'}
              checked={settings.spot_trailing_only_after_tp1}
              onChange={(spot_trailing_only_after_tp1) => patch({ spot_trailing_only_after_tp1 })}
            />
            <ToggleInput
              label="Time Stop Spot"
              showHelp={h} help="Attiva la chiusura per tempo scaduto. Le ore si impostano nella sezione strategia."
              checked={settings.spot_time_stop_enabled}
              onChange={(spot_time_stop_enabled) => patch({ spot_time_stop_enabled })}
            />
            <ToggleInput
              label="Filtro volatilità Spot"
              showHelp={h} help={'Salta gli ingressi sui token troppo volatili, dove lo stop dista più della soglia "Max stop dist %". Blocca i micro-cap ad ATR mostruoso (perdite -5/-12%) che passano liquidità e anti-spike ma mangiano tutte le vincite. Agisce sul singolo trade, non blocca l\'intero token.'}
              checked={settings.spot_max_stop_distance_filter_enabled}
              onChange={(spot_max_stop_distance_filter_enabled) => patch({ spot_max_stop_distance_filter_enabled })}
            />
          </section>
        </>
      )}

      {/* Tab: Perp */}
      {setupTab === 'perp' && (
        <>
          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Perp — risk</h3>
            <div className="grid grid-cols-2 gap-3">
              <NumberInput label="Size % (margine)" showHelp={h} help="Quanto margine impegnare in ogni operazione, in percentuale sul capitale. Con la leva il valore controllato sul mercato è molto più grande del margine." value={settings.perp_capital_per_trade_pct} onChange={(perp_capital_per_trade_pct) => patch({ perp_capital_per_trade_pct })} />
              <NumberInput label="Rischio %" showHelp={h} help={'Quanto sei disposto a perdere su un singolo trade. Da qui si calcola la dimensione: la perdita allo stop resta questa cifra, qualunque sia la leva.'} value={settings.perp_per_trade_pct} step={0.1} onChange={(perp_per_trade_pct) => patch({ perp_per_trade_pct })} />
              <NumberInput label="Max posizioni" showHelp={h} help="Quante posizioni perp possono restare aperte insieme." value={settings.perp_max_open_positions} onChange={(perp_max_open_positions) => patch({ perp_max_open_positions })} />
              <NumberInput label="Exposure %" showHelp={h} help="Tetto al margine impegnato in tutte le posizioni perp sommate." value={settings.perp_max_exposure_pct} onChange={(perp_max_exposure_pct) => patch({ perp_max_exposure_pct })} />
              <NumberInput label="Slippage %" showHelp={h} help={'Scarto massimo accettato fra prezzo previsto ed effettivo. Oltre, l\'ordine viene annullato.'} value={settings.perp_max_slippage_pct} step={0.1} onChange={(perp_max_slippage_pct) => patch({ perp_max_slippage_pct })} />
              <NumberInput label="Cooldown min" showHelp={h} help="Minuti di attesa prima di riaprire sullo stesso asset dopo una chiusura." value={settings.perp_cooldown_minutes} onChange={(perp_cooldown_minutes) => patch({ perp_cooldown_minutes })} />
              <ToggleInput label="Margine fisso Perp" showHelp={h} help="Usa sempre lo stesso margine in dollari per ogni trade, invece di calcolarlo in percentuale sul capitale." checked={settings.perp_fixed_margin_enabled} onChange={(perp_fixed_margin_enabled) => patch({ perp_fixed_margin_enabled })} />
              <NumberInput label="Margine fisso $" showHelp={h} help={'Il margine fisso in dollari per ogni operazione, quando l\'opzione qui sopra è accesa.'} value={settings.perp_fixed_margin_usd} onChange={(perp_fixed_margin_usd) => patch({ perp_fixed_margin_usd })} />
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="px-1 text-xs font-semibold uppercase text-gray-500">Perp — strategia</h3>
            <div className="grid grid-cols-2 gap-3">
              <SelectInput label="Direction" showHelp={h} help={'In che direzione può operare:\n\nLong e short — sfrutta salite e discese\nSolo long — apre solo al rialzo\nSolo short — apre solo al ribasso'} value={settings.perp_direction_mode} onChange={(perp_direction_mode) => patch({ perp_direction_mode })} options={[
                { value: 'long_only', label: 'Long' },
                { value: 'short_only', label: 'Short' },
                { value: 'long_short', label: 'Both' },
              ]} />
              <NumberInput label="Leva min (alta vol.)" showHelp={h} help="Leva usata quando la volatilità è alta. Mercato agitato, leva bassa: si rischia meno su movimenti ampi." value={settings.perp_min_leverage} onChange={(perp_min_leverage) => patch({ perp_min_leverage })} />
              <NumberInput label="Leva max (bassa vol.)" showHelp={h} help="Leva usata quando la volatilità è bassa. Mercato calmo, leva alta: serve più leva per un guadagno sensato." value={settings.perp_max_leverage} onChange={(perp_max_leverage) => patch({ perp_max_leverage })} />
              <NumberInput label="Value area %" showHelp={h} help={'Quanta parte del volume definisce la zona di prezzo dove il mercato ha scambiato di più. Il segnale nasce ai bordi di questa zona.'} value={settings.perp_value_area_pct} onChange={(perp_value_area_pct) => patch({ perp_value_area_pct })} />
              <NumberInput label="ATR stop" showHelp={h} help={'Distanza dello stop dall\'ingresso in ATR, quando lo stop è di tipo ATR. Più alto, stop più largo.'} value={settings.perp_atr_stop_multiplier} step={0.1} onChange={(perp_atr_stop_multiplier) => patch({ perp_atr_stop_multiplier })} />
              <NumberInput label="Buffer Min/Max20 %" showHelp={h} help="Cuscinetto oltre il minimo (o massimo) recente, quando lo stop è strutturale. Evita di farsi prendere lo stop per un soffio." value={settings.perp_structural_stop_buffer_pct} step={0.1} onChange={(perp_structural_stop_buffer_pct) => patch({ perp_structural_stop_buffer_pct })} />
              <NumberInput label="Lookback candele SL" showHelp={h} help="Quante candele guardare indietro per trovare il minimo/massimo strutturale da usare come stop." value={settings.perp_structural_stop_lookback_candles} step={1} onChange={(perp_structural_stop_lookback_candles) => patch({ perp_structural_stop_lookback_candles: Math.round(perp_structural_stop_lookback_candles) })} />
              <SelectInput label="Protezione profitto (post-TP1)" showHelp={h} help={'Come proteggere il profitto dopo il primo incasso:\n\nOff — nessuna protezione\nTrailing ATR — lo stop insegue il prezzo\nProfit Lock — uscite parziali a scalini fra i due obiettivi'} value={settings.perp_protection_mode} onChange={(v) => patch({ perp_protection_mode: v as 'off' | 'trailing' | 'profit_lock' })} options={[
                { value: 'off', label: 'Off — solo breakeven' },
                { value: 'trailing', label: 'Trailing ATR' },
                { value: 'profit_lock', label: 'Profit Lock (ratchet)' },
              ]} />
              {settings.perp_protection_mode === 'trailing' && (
                <SelectInput label="Trailing ATR (adatta alla leva)" showHelp={h} help={'Quanto stretto insegue il trailing:\n\nLargo — lascia respirare, esce più tardi\nStretto — protegge prima, ma esce sui rimbalzi'} value={settings.perp_trailing_mode} onChange={(v) => patch({ perp_trailing_mode: v as 'largo' | 'stretto' })} options={[
                  { value: 'largo', label: 'Largo — lascia correre' },
                  { value: 'stretto', label: 'Stretto — blocca prima' },
                ]} />
              )}
              {settings.perp_protection_mode === 'trailing' && (
                <NumberInput label="Trailing dist. % (0=solo ATR)" showHelp={h} help={'Distanza fissa del trailing in percentuale. A zero il trailing usa solo l\'ATR.'} value={settings.perp_trailing_pnl_pct} step={0.1} onChange={(perp_trailing_pnl_pct) => patch({ perp_trailing_pnl_pct })} />
              )}
              <NumberInput label="Chiudi a TP1 %" showHelp={h} help="Quanta parte della posizione chiudere al primo obiettivo. Il resto prosegue verso il secondo, gestito dalla protezione scelta." value={settings.perp_tp1_close_pct} step={5} onChange={(perp_tp1_close_pct) => patch({ perp_tp1_close_pct })} />
              <NumberInput label="Time Stop ore" showHelp={h} help="Dopo quante ore chiudere una posizione ferma, che non ha raggiunto né obiettivo né stop." value={settings.perp_time_stop_hours} step={1} onChange={(perp_time_stop_hours) => patch({ perp_time_stop_hours: Math.round(perp_time_stop_hours) })} />
              <SelectInput label="Fee mode (dry-run)" showHelp={h} help={'Quali costi simulare nel dry run:\n\nTaker — ordini a mercato, 0.06%\nMaker — ordini limite, 0.02%\nNessuna — strategia lorda'} value={settings.perp_fee_mode} onChange={(v) => patch({ perp_fee_mode: v as 'taker' | 'maker' | 'none' })} options={[
                { value: 'taker', label: 'Taker (market) — 0.06%' },
                { value: 'maker', label: 'Maker (limit) — 0.02%' },
                { value: 'none', label: 'Nessuna (strategia lorda)' },
              ]} />
            </div>
            {settings.perp_protection_mode === 'profit_lock' && (
              <div className="space-y-2 rounded-lg border border-gray-700 p-3">
                <p className="text-xs font-semibold text-gray-400">Scalini Profit Lock — progresso verso TP2 → quota di profitto bloccata</p>
                {settings.perp_profit_lock_steps.map((stepPair, i) => (
                  <div key={i} className="grid grid-cols-2 gap-3">
                    <NumberInput label={`Soglia ${i + 1} (%)`} showHelp={h} help="A che punto del tratto fra primo e secondo obiettivo scatta questo scalino. Al 50% è a metà strada, al 95% quasi al traguardo." value={Math.round(stepPair[0] * 100)} step={5} onChange={(v) => {
                      const next = settings.perp_profit_lock_steps.map((s, j) => (j === i ? [Math.max(0, Math.min(100, v)) / 100, s[1]] : s)) as Array<[number, number]>;
                      patch({ perp_profit_lock_steps: next });
                    }} />
                    <NumberInput label={`Lock ${i + 1} (%)`} showHelp={h} help="Quanta parte del residuo risulta chiusa in totale a questo scalino. Le quote sono cumulative." value={Math.round(stepPair[1] * 100)} step={5} onChange={(v) => {
                      const next = settings.perp_profit_lock_steps.map((s, j) => (j === i ? [s[0], Math.max(0, Math.min(100, v)) / 100] : s)) as Array<[number, number]>;
                      patch({ perp_profit_lock_steps: next });
                    }} />
                  </div>
                ))}
                <p className="text-xs text-gray-500">Soglie e lock crescenti, lock &lt; soglia. Dopo il TP1 lo stop sale a gradini verso il TP2 e non scende mai (immune alle spike).</p>
              </div>
            )}
            <ToggleInput
              label="Breakeven Perp"
              showHelp={h} help={'Sposta lo stop al prezzo d\'ingresso quando il trade è in guadagno: da lì in poi l\'operazione non può più chiudere in perdita.'}
              checked={settings.perp_breakeven_enabled}
              onChange={(perp_breakeven_enabled) => patch({ perp_breakeven_enabled })}
            />
            <SelectInput
              label="Modalità breakeven Perp"
              showHelp={h} help={'Quando spostare lo stop a pareggio:\n\nATR — appena il guadagno raggiunge la soglia di volatilità\nSolo dopo TP1 — solo dopo il primo incasso'}
              value={settings.perp_breakeven_mode}
              onChange={(v) => patch({ perp_breakeven_mode: v })}
              options={[
                { value: 'atr', label: 'ATR (attuale)' },
                { value: 'tp1', label: 'Solo dopo TP1' },
              ]}
            />
            {settings.perp_breakeven_enabled && (
              <NumberInput
                label="BE profitto min $ (0=solo costi)"
                showHelp={h} help={'Guadagno minimo da lasciare sul tavolo quando lo stop va a pareggio. A zero copre solo i costi; alzandolo, il pareggio diventa un piccolo utile garantito.'}
                value={settings.perp_breakeven_min_profit_usd}
                step={0.05}
                onChange={(perp_breakeven_min_profit_usd) => patch({ perp_breakeven_min_profit_usd: Math.max(0, perp_breakeven_min_profit_usd) })}
              />
            )}
            <SelectInput
              label="Stop Loss Perp"
              showHelp={h} help={'Come calcolare lo stop loss:\n\nATR — distanza fissa sulla volatilità\nMin/Max 20 candele — sotto il minimo (o sopra il massimo) recente: più largo e più aderente al grafico'}
              value={settings.perp_sl_mode}
              onChange={(v) => patch({ perp_sl_mode: v })}
              options={[
                { value: 'atr', label: 'ATR (attuale)' },
                { value: 'lowest', label: 'Min/Max 20 candele' },
              ]}
            />
            <ToggleInput
              label="Time Stop Perp"
              showHelp={h} help="Attiva la chiusura per tempo scaduto. Le ore si impostano nella sezione strategia."
              checked={settings.perp_time_stop_enabled}
              onChange={(perp_time_stop_enabled) => patch({ perp_time_stop_enabled })}
            />
            <p className="px-1 text-xs text-gray-500">
              Leva modulata sulla volatilità ATR(72) in apertura: bassa volatilità → leva max, alta volatilità → leva min. Volatilità anomala (oltre il massimo storico) → leva forzata al minimo. Range 1–50.
            </p>
          </section>

          <Collapsible title="Soglie filtro shock BTC" count={4}>
            <ToggleInput
              label="Filtro shock BTC perp"
              showHelp={h} help={'Blocca le nuove aperture quando Bitcoin è in una fase anomala, perché in quei momenti tutto il mercato si muove insieme e i segnali sui singoli asset valgono meno. Serve almeno il verificarsi di due delle tre condizioni qui sotto.'}
              checked={settings.perp_trend_shock_enabled}
              onChange={(perp_trend_shock_enabled) => patch({ perp_trend_shock_enabled })}
            />
            {settings.perp_trend_shock_enabled && (
              <div className="grid grid-cols-2 gap-3">
                <NumberInput label="ADX threshold" showHelp={h} help="Quanto deve essere forte il trend di Bitcoin perché conti come segnale d'allarme. Sopra questa soglia vale un punto su tre." value={settings.perp_trend_shock_adx_threshold} onChange={(perp_trend_shock_adx_threshold) => patch({ perp_trend_shock_adx_threshold })} />
                <NumberInput label="NATR percentile" showHelp={h} help="Quanto in alto deve stare la volatilità di Bitcoin rispetto al suo passato. A 90 significa: più alta del 90% delle volte. Vale un punto." value={settings.perp_trend_shock_natr_percentile} onChange={(perp_trend_shock_natr_percentile) => patch({ perp_trend_shock_natr_percentile })} />
                <NumberInput label="Volume threshold" showHelp={h} help="Quante volte il volume di Bitcoin deve superare la sua media per contare come allarme. Vale un punto." value={settings.perp_trend_shock_volume_threshold} onChange={(perp_trend_shock_volume_threshold) => patch({ perp_trend_shock_volume_threshold })} />
                <NumberInput label="Recovery checks" showHelp={h} help="Quanti controlli consecutivi tranquilli servono prima di tornare a operare. Più alto, più prudente nel rientrare." value={settings.perp_trend_shock_recovery_confirmations} onChange={(perp_trend_shock_recovery_confirmations) => patch({ perp_trend_shock_recovery_confirmations })} />
              </div>
            )}
          </Collapsible>

          <Collapsible title="Parametri Smart Stop Loss" count={20}>
            <ToggleInput
              label="Smart Stop Loss Perp"
              showHelp={h} help={'Invece di subire lo stop in un colpo solo, vende a pezzi mentre il prezzo scende verso lo stop, per ridurre la perdita. Può poi ricomprare se il prezzo rimbalza.'}
              checked={settings.perp_smart_sl_enabled}
              onChange={(perp_smart_sl_enabled) => patch({ perp_smart_sl_enabled })}
            />
            {settings.perp_smart_sl_enabled && (
              <div className="grid grid-cols-2 gap-3">
                <NumberInput label="L1 frac" showHelp={h} help={'Dove sta il primo livello di vendita, come frazione della strada fra ingresso e stop. A 0.35 scatta al 35% del percorso verso lo stop.'} value={settings.perp_smart_sl_l1_frac} step={0.01} onChange={(perp_smart_sl_l1_frac) => patch({ perp_smart_sl_l1_frac })} />
                <NumberInput label="L2 frac" showHelp={h} help="Dove sta il secondo livello di vendita, sempre come frazione della strada verso lo stop." value={settings.perp_smart_sl_l2_frac} step={0.01} onChange={(perp_smart_sl_l2_frac) => patch({ perp_smart_sl_l2_frac })} />
                <NumberInput label="Split L1 %" showHelp={h} help="Quanta parte della posizione vendere al primo livello." value={settings.perp_smart_sl_split_l1} step={0.01} onChange={(perp_smart_sl_split_l1) => patch({ perp_smart_sl_split_l1 })} />
                <NumberInput label="Split L2 %" showHelp={h} help="Quanta parte vendere al secondo livello." value={settings.perp_smart_sl_split_l2} step={0.01} onChange={(perp_smart_sl_split_l2) => patch({ perp_smart_sl_split_l2 })} />
                <NumberInput label="Split L3 %" showHelp={h} help="Quanta parte lasciare in piedi fino allo stop vero e proprio. Le tre quote devono sommare a 1." value={settings.perp_smart_sl_split_l3} step={0.01} onChange={(perp_smart_sl_split_l3) => patch({ perp_smart_sl_split_l3 })} />
                <SelectInput label="Rebuy mode" showHelp={h} help={'Come ricomprare dopo aver venduto:\n\nSopra l\'ingresso — ricompra tutto quando il prezzo torna sopra il prezzo d\'entrata\nA livelli — ricompra a scaglioni sui rimbalzi'} value={settings.perp_smart_sl_rebuy_mode} onChange={(v) => patch({
                  perp_smart_sl_rebuy_mode: v,
                  ...(v === 'above_entry' ? { perp_smart_sl_confirmation_candles: 2, perp_smart_sl_max_reentries: 1 } : { perp_smart_sl_confirmation_candles: 3, perp_smart_sl_max_reentries: 2 }),
                })} options={[
                  { value: 'above_entry', label: 'Sopra entry' },
                  { value: 'delta', label: 'Delta per livello' },
                ]} />
                {settings.perp_smart_sl_rebuy_mode === 'above_entry' && (
                  <>
                    <NumberInput label="Rebuy % venduto" showHelp={h} help={'Quanta parte di ciò che è stato venduto viene ricomprata, quando il prezzo risale sopra il prezzo d\'ingresso. A 100 rientra tutto in una volta.'} value={settings.perp_smart_sl_rebuy_above_entry_pct} step={1} onChange={(perp_smart_sl_rebuy_above_entry_pct) => patch({ perp_smart_sl_rebuy_above_entry_pct })} />
                    <NumberInput label="R2 Split L1 %" showHelp={h} help={'Se un livello è già stato venduto e poi ricomprato, e il prezzo ci torna sopra, si vende una seconda volta con questa quota.'} value={settings.perp_smart_sl_split_l1_r2} step={0.01} onChange={(perp_smart_sl_split_l1_r2) => patch({ perp_smart_sl_split_l1_r2 })} />
                    <NumberInput label="R2 Split L2 %" showHelp={h} help="Quota del secondo giro per il secondo livello." value={settings.perp_smart_sl_split_l2_r2} step={0.01} onChange={(perp_smart_sl_split_l2_r2) => patch({ perp_smart_sl_split_l2_r2 })} />
                    <NumberInput label="R2 Split L3 %" showHelp={h} help="Quanta parte lasciare in piedi fino allo stop, nel secondo giro di vendite." value={settings.perp_smart_sl_split_l3_r2} step={0.01} onChange={(perp_smart_sl_split_l3_r2) => patch({ perp_smart_sl_split_l3_r2 })} />
                  </>
                )}
                {settings.perp_smart_sl_rebuy_mode === 'delta' && (
                  <>
                    <NumberInput label="Delta L1" showHelp={h} help={'Quanto deve rimbalzare il prezzo per ricomprare il primo scaglione. Si misura dal prezzo a cui hai venduto, come frazione della distanza fra ingresso e stop.'} value={settings.perp_smart_sl_delta_l1} step={0.01} onChange={(perp_smart_sl_delta_l1) => patch({ perp_smart_sl_delta_l1 })} />
                    <NumberInput label="Delta L2" showHelp={h} help="Quanto deve rimbalzare per ricomprare il secondo scaglione. Stessa misura del primo." value={settings.perp_smart_sl_delta_l2} step={0.01} onChange={(perp_smart_sl_delta_l2) => patch({ perp_smart_sl_delta_l2 })} />
                  </>
                )}
                <NumberInput label="Candele conferma SSL" showHelp={h} help="Quante candele da 5 minuti devono confermare prima di vendere o ricomprare. Più alto significa meno reazioni ai falsi movimenti, ma reazione più lenta." value={settings.perp_smart_sl_confirmation_candles} step={1} onChange={(perp_smart_sl_confirmation_candles) => patch({ perp_smart_sl_confirmation_candles: Math.round(perp_smart_sl_confirmation_candles) })} />
                <NumberInput label="Max reentries" showHelp={h} help="Quanti cicli vendi-e-ricompra sono ammessi sulla stessa posizione. A zero il rebuy è spento e la vendita è definitiva." value={settings.perp_smart_sl_max_reentries} step={1} onChange={(perp_smart_sl_max_reentries) => patch({ perp_smart_sl_max_reentries: Math.round(perp_smart_sl_max_reentries) })} />
                <ToggleInput label="Adegua TP dopo rebuy" showHelp={h} help="Dopo un rebuy sposta gli obiettivi più in là, in modo che le uscite rimaste recuperino anche le perdite già incassate durante le vendite." checked={settings.perp_smart_sl_tp_adjust_after_rebuy} onChange={(perp_smart_sl_tp_adjust_after_rebuy) => patch({ perp_smart_sl_tp_adjust_after_rebuy })} />
                {settings.perp_smart_sl_tp_adjust_after_rebuy && (
                  <NumberInput label="Delta recovery TP %" showHelp={h} help="Quanto guadagno extra pretendere oltre il semplice recupero delle perdite, quando gli obiettivi vengono spostati." value={settings.perp_smart_sl_tp_recovery_delta_pct} step={1} onChange={(perp_smart_sl_tp_recovery_delta_pct) => patch({ perp_smart_sl_tp_recovery_delta_pct })} />
                )}
              </div>
            )}
          </Collapsible>
        </>
      )}

      {/* Tab: Sistema */}
      {setupTab === 'sistema' && (
        <>
          <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-3">
            <h3 className="text-sm font-semibold text-white">Interfaccia</h3>
            <label className="flex items-center justify-between gap-3 rounded-lg border border-dark-700 bg-dark-800 px-3 py-2">
              <span className="min-w-0 text-sm font-semibold text-white">Mostra suggerimenti <span className="text-gray-500 text-xs font-normal">(?)</span></span>
              <input type="checkbox" checked={showHelp} onChange={(e) => toggleHelp(e.target.checked)} className="h-5 w-5 accent-accent-blue" />
            </label>
            <p className="text-xs text-gray-500">Mostra le icone ? accanto ai controlli per spiegare cosa fa ogni impostazione.</p>
          </section>

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
            {adminCheck !== 'idle' && (
              <p className={`text-xs flex items-center gap-1.5 ${
                adminCheck === 'valid' ? 'text-accent-green'
                : adminCheck === 'invalid' ? 'text-accent-red'
                : 'text-gray-500'
              }`}>
                {adminCheck === 'checking' && (
                  <>
                    <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>
                    Verifica del token…
                  </>
                )}
                {adminCheck === 'valid' && '✓ Admin attivo — funzioni privilegiate sbloccate'}
                {adminCheck === 'invalid' && '✗ Token non valido: il backend lo rifiuta'}
                {adminCheck === 'unreachable' && 'Backend non raggiungibile — impossibile verificare ora'}
              </p>
            )}
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
            {!adminToken && <p className="text-xs text-gray-600">Richiede admin token salvato.</p>}
          </section>

          <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-3">
            <div className="min-w-0">
              <h3 className="text-sm font-semibold text-white">Liquidità · Versamento / Prelievo</h3>
              <p className="mt-0.5 text-xs text-gray-500">Aggiunge (o toglie, con valore negativo) capitale come un deposito. Alza l'equity senza contare come PnL. Es: <span className="text-gray-400">200</span> = +200$, <span className="text-gray-400">-50</span> = −50$.</p>
            </div>
            <div className="flex gap-2">
              <input
                type="number"
                inputMode="decimal"
                value={equityInput}
                onChange={(event) => setEquityInput(event.target.value)}
                placeholder="es. 200 oppure -50"
                className="flex-1 min-w-0 bg-dark-900 border border-dark-700 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
              />
              <button
                onClick={() => { if (equityValid) { onAdjustEquity(equityValue); setEquityInput(''); } }}
                disabled={!adminToken || saving || !equityValid}
                className="rounded-lg bg-accent-blue px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
              >
                Applica
              </button>
            </div>
            {!adminToken && <p className="text-xs text-gray-600">Richiede admin token salvato.</p>}
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
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Connessione Aster</h3>
              <button
                onClick={handleAsterTest}
                disabled={asterState === 'testing' || !adminToken}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-dark-700 text-gray-300 text-xs font-semibold rounded-lg hover:bg-dark-600 transition-colors disabled:opacity-40"
              >
                {asterState === 'testing' && (
                  <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" /><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" /></svg>
                )}
                {asterState === 'testing' ? 'Test in corso…' : 'Test connessione'}
              </button>
            </div>
            <p className="text-xs text-gray-500">Verifica la comunicazione con Aster: legge saldo e posizioni, non invia ordini.</p>
            {asterError && <p className="text-xs text-accent-red">{asterError}</p>}
            {asterReport && (
              <div className="space-y-2">
                <div className={`rounded-lg px-3 py-2 text-xs font-semibold ${
                  asterReport.overall === 'ok' ? 'bg-accent-green/10 text-accent-green'
                  : asterReport.overall === 'warning' ? 'bg-accent-yellow/10 text-accent-yellow'
                  : 'bg-accent-red/10 text-accent-red'}`}>
                  {asterReport.summary}
                </div>
                <div className="bg-dark-700 rounded-lg divide-y divide-dark-600">
                  {asterReport.checks.map((check) => (
                    <div key={check.key} className="px-3 py-2 space-y-0.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs text-gray-400">{check.label}</span>
                        <span className={`text-xs font-semibold flex-shrink-0 ${
                          check.status === 'ok' ? 'text-accent-green'
                          : check.status === 'warning' ? 'text-accent-yellow'
                          : 'text-accent-red'}`}>
                          {check.status === 'ok' ? '● OK'
                            : check.status === 'warning' ? '● ATTENZIONE'
                            : check.status === 'critical' ? '● CRITICO' : '● ERRORE'}
                        </span>
                      </div>
                      <p className="text-xs text-gray-500 leading-snug">{check.detail}</p>
                      {check.technical && (
                        <p className="text-[10px] text-gray-600 font-mono">codice: {check.technical}</p>
                      )}
                    </div>
                  ))}
                </div>
                <p className="text-xs text-gray-600">
                  {new Date(asterReport.started_at).toLocaleString('it-IT')} · {asterReport.duration_ms} ms
                  {asterReport.account ? ` · ${asterReport.account}` : ''}
                </p>
                {asterReport.blocked && (
                  <p className="text-xs text-accent-red font-semibold">
                    Operazioni bloccate: l'identità dell'account non corrisponde alla configurazione.
                  </p>
                )}
              </div>
            )}
            {!adminToken && <p className="text-xs text-gray-600">Richiede admin token.</p>}
          </section>

          <section className="rounded-xl bg-dark-800 px-4 py-3">
            <p className="text-xs text-gray-500">Per indirizzi e posizioni aperte usa il tab <span className="text-accent-blue font-semibold">Wallet</span>.</p>
          </section>
        </>
      )}

      {/* Always visible: dirty warning + save */}
      {dirty && !saving && (
        <p className="rounded-lg border border-accent-yellow/30 bg-accent-yellow/10 px-3 py-2 text-xs text-accent-yellow">
          Modifiche non salvate — l'aggiornamento automatico è in pausa finché non salvi.
        </p>
      )}
      <button
        onClick={onSave}
        disabled={!adminToken || saving}
        className={`w-full rounded-lg px-3 py-3 text-sm font-semibold text-white disabled:opacity-40 ${dirty ? 'bg-accent-orange' : 'bg-accent-blue'}`}
      >
        {saving ? 'Salvataggio…' : dirty ? 'Salva le modifiche' : 'Salva impostazioni agente'}
      </button>
      {actionError && <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{actionError}</p>}
    </div>
  );
};

const TradeCandleChart: FC<{
  chart: NonNullable<TradeDetail['chart']>;
  breakeven?: string | null;
  trailing?: string | null;
}> = ({ chart, breakeven, trailing }) => {
  const candles = chart.candles ?? [];
  const postClose = chart.post_close_candles ?? [];
  const allCandles = [...candles, ...postClose];
  if (allCandles.length < 2) {
    return <p className="text-xs text-gray-500">Grafico non disponibile per questo trade.</p>;
  }
  // Geometria: area di plot + margine destro per i prezzi (Y) e inferiore per gli orari (X).
  const W = Math.max(340, allCandles.length * 8 + 58);
  const H = 200;
  const padX = 6;
  const padTop = 10;
  const axisW = 46;
  const axisH = 16;
  const plotR = W - axisW;
  const plotB = H - axisH;
  const entry = Number(chart.entry_price);
  const exit = Number(chart.exit_price);
  const sl = chart.stop_loss != null ? Number(chart.stop_loss) : null;
  const tp1 = chart.take_profit_1 != null ? Number(chart.take_profit_1) : null;
  const tp2 = chart.take_profit_2 != null ? Number(chart.take_profit_2) : null;
  const be = breakeven != null ? Number(breakeven) : null;
  const trail = trailing != null ? Number(trailing) : null;

  const levels = [entry, exit, sl, tp1, tp2, be, trail].filter((v): v is number => v != null && !Number.isNaN(v));
  let hi = Math.max(...allCandles.map((c) => c.h), ...levels);
  let lo = Math.min(...allCandles.map((c) => c.l), ...levels);
  if (hi === lo) { hi += 1; lo -= 1; }
  const range = hi - lo;
  const y = (price: number) => padTop + (1 - (price - lo) / range) * (plotB - padTop);
  const colW = (plotR - padX) / allCandles.length;
  const cx = (i: number) => padX + colW * (i + 0.5);

  // Marker temporali: candela piu' vicina ad apertura/chiusura sull'intero grafico.
  const ts = (s: string) => new Date(s).getTime();
  const nearest = (target: number, pool: typeof allCandles) => {
    let best = 0;
    let bestD = Infinity;
    pool.forEach((c, i) => { const d = Math.abs(ts(c.t) - target); if (d < bestD) { bestD = d; best = i; } });
    return best;
  };
  const atOrBefore = (target: number, pool: typeof allCandles) => {
    let best = -1;
    pool.forEach((c, i) => { if (ts(c.t) <= target) best = i; });
    return best >= 0 ? best : nearest(target, pool);
  };
  const entryIdx = nearest(ts(chart.opened_at), allCandles);
  const exitIdx = atOrBefore(ts(chart.closed_at), allCandles);
  const stopRefIdx = chart.stop_reference?.t ? nearest(ts(chart.stop_reference.t), allCandles) : null;
  const stopRefPrice = sl ?? (chart.stop_reference?.price != null ? Number(chart.stop_reference.price) : null);
  const exitGood = exit >= entry;

  // Etichette asse Y (prezzo).
  const fmtAxisPrice = (p: number) => {
    if (p >= 1000) return p.toFixed(0);
    if (p >= 1) return p.toFixed(2);
    if (p >= 0.01) return p.toFixed(4);
    return p.toPrecision(3);
  };
  const yTicks = [0, 1, 2, 3, 4].map((k) => lo + (range * k) / 4);

  // Etichette asse X (orario).
  const spanMs = ts(allCandles[allCandles.length - 1].t) - ts(allCandles[0].t);
  const fmtAxisTime = (iso: string) => {
    const d = new Date(iso);
    return spanMs > 24 * 3600 * 1000
      ? d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' })
      : d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' });
  };
  const last = allCandles.length - 1;
  const xTickIdx = [0, Math.round(last / 3), Math.round((2 * last) / 3), last];

  const levelLine = (price: number | null, color: string, dash: string) =>
    price == null || Number.isNaN(price) ? null : (
      <line x1={padX} x2={plotR} y1={y(price)} y2={y(price)} stroke={color} strokeWidth="1" strokeDasharray={dash} opacity="0.5" />
    );

  const stopRefLine = (idx: number) => {
    const candle = allCandles[idx];
    if (!candle) return null;
    const gap = 3;
    const x = cx(idx);
    const topEnd = Math.max(padTop, y(candle.h) - gap);
    const bottomStart = Math.min(plotB, y(candle.l) + gap);
    return (
      <>
        {topEnd > padTop && (
          <line x1={x} x2={x} y1={padTop} y2={topEnd} stroke="#a855f7" strokeWidth="1" strokeDasharray="2 2" opacity="0.9" />
        )}
        {bottomStart < plotB && (
          <line x1={x} x2={x} y1={bottomStart} y2={plotB} stroke="#a855f7" strokeWidth="1" strokeDasharray="2 2" opacity="0.9" />
        )}
      </>
    );
  };

  // Linea verticale tratteggiata subito dopo la candela di chiusura.
  const closeLineX = postClose.length > 0 ? cx(exitIdx + 0.5) : null;

  return (
    <div className="overflow-x-auto pb-1">
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: `${W}px`, minWidth: '100%', height: 'auto' }}>
      {/* griglia + etichette asse Y */}
      {yTicks.map((p, k) => (
        <g key={`yt${k}`}>
          <line x1={padX} x2={plotR} y1={y(p)} y2={y(p)} stroke="#1f2937" strokeWidth="0.5" opacity="0.6" />
          <text x={plotR + 4} y={y(p)} fontSize="8" fill="#6b7280" dominantBaseline="middle">{fmtAxisPrice(p)}</text>
        </g>
      ))}
      {/* assi */}
      <line x1={plotR} x2={plotR} y1={padTop} y2={plotB} stroke="#374151" strokeWidth="0.5" />
      <line x1={padX} x2={plotR} y1={plotB} y2={plotB} stroke="#374151" strokeWidth="0.5" />
      {/* etichette asse X */}
      {xTickIdx.map((i, k) => (
        <text
          key={`xt${k}`}
          x={cx(i)}
          y={H - 4}
          fontSize="8"
          fill="#6b7280"
          textAnchor={k === 0 ? 'start' : k === xTickIdx.length - 1 ? 'end' : 'middle'}
        >
          {fmtAxisTime(allCandles[i].t)}
        </text>
      ))}
      {/* sfondo post-close */}
      {closeLineX != null && (
        <rect x={closeLineX} y={padTop} width={plotR - closeLineX} height={plotB - padTop} fill="#111827" opacity="0.4" />
      )}
      {/* Candles outside the active trade window are contextual and muted. */}
      {allCandles.map((c, i) => {
        const isPost = i >= candles.length;
        const isPreEntry = i < entryIdx;
        const up = c.c >= c.o;
        const color = isPost ? (up ? '#166534' : '#7f1d1d') : (up ? '#22c55e' : '#ef4444');
        const opacity = isPost || isPreEntry ? 0.55 : 1;
        const bodyTop = y(Math.max(c.o, c.c));
        const bodyBot = y(Math.min(c.o, c.c));
        const bw = Math.max(1, colW * 0.6);
        return (
          <g key={i} opacity={opacity}>
            <line x1={cx(i)} x2={cx(i)} y1={y(c.h)} y2={y(c.l)} stroke={color} strokeWidth="1" />
            <rect x={cx(i) - bw / 2} y={bodyTop} width={bw} height={Math.max(1, bodyBot - bodyTop)} fill={color} />
          </g>
        );
      })}
      {/* linea verticale tratteggiata di chiusura */}
      {closeLineX != null && (
        <line x1={closeLineX} x2={closeLineX} y1={padTop} y2={plotB} stroke="#6b7280" strokeWidth="1" strokeDasharray="3 2" opacity="0.8" />
      )}
      {stopRefIdx != null && (
        <>
          {stopRefLine(stopRefIdx)}
          <text x={Math.min(plotR - 4, cx(stopRefIdx) + 4)} y={padTop + 8} fontSize="8" fill="#c084fc">SL ref</text>
          {stopRefPrice != null && !Number.isNaN(stopRefPrice) && (
            <circle cx={cx(stopRefIdx)} cy={y(stopRefPrice)} r="3" fill="#a855f7" stroke="#0b0e11" strokeWidth="1" />
          )}
        </>
      )}
      {levelLine(sl, '#fca5a5', '4 3')}
      {levelLine(be, '#fcd34d', '3 3')}
      {levelLine(trail, '#7dd3fc', '3 3')}
      {levelLine(tp1, '#86efac', '4 3')}
      {levelLine(tp2, '#5eead4', '2 3')}
      {levelLine(entry, '#cbd5e1', '1 0')}
      {/* marker ingresso/uscita */}
      <circle cx={cx(entryIdx)} cy={y(entry)} r="3.5" fill="#e5e7eb" stroke="#0b0e11" strokeWidth="1" />
      <circle cx={cx(exitIdx)} cy={y(exit)} r="3.5" fill={exitGood ? '#22c55e' : '#ef4444'} stroke="#0b0e11" strokeWidth="1" />
    </svg>
    </div>
  );
};

const TradeDetailScreen: FC<{ detail: TradeDetail; onBack: () => void }> = ({ detail, onBack }) => (
  <div className="space-y-4">
    <button onClick={onBack} className="rounded-lg bg-dark-800 px-3 py-2 text-sm font-semibold text-gray-300">
      Back
    </button>
    {detail.is_smart_sl ? (
      /* ── Vista dedicata per trade Smart SL (no grafico) ── */
      <section className="rounded-xl bg-dark-800 px-4 py-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-bold text-white">{detail.asset}</h3>
            <p className="text-xs text-gray-500">{detail.market} / {detail.direction}</p>
          </div>
          <span className={`rounded-full px-2 py-1 text-xs font-semibold ${detail.ssl_action === 'sell' ? 'bg-amber-500/15 text-amber-400' : 'bg-sky-500/15 text-sky-400'}`}>
            Smart SL {detail.ssl_action === 'sell' ? 'Sell' : 'Rebuy'} L{detail.ssl_level}
          </span>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-2">
          <Stat label="Azione" value={detail.ssl_action === 'sell' ? 'Vendita parziale' : 'Riacquisto'} />
          <Stat label="Livello" value={`L${detail.ssl_level}`} />
          <Stat label="Prezzo esecuzione" value={fmtPriceFull(detail.current_or_exit_price)} />
          <Stat label="Size" value={detail.size} />
          <Stat label="Entry originale" value={fmtPriceFull(detail.original_entry_price ?? detail.entry_price)} />
          {detail.current_position_entry_price && detail.current_position_entry_price !== (detail.original_entry_price ?? detail.entry_price) && (
            <Stat label="Entry corrente" value={fmtPriceFull(detail.current_position_entry_price)} />
          )}
          <Stat label="Leverage" value={detail.leverage ? `${detail.leverage.toFixed(2)}x` : '-'} />
          {detail.ssl_action === 'sell' && (
            <Stat label="PnL parziale" value={`${detail.pnl_usd} / ${detail.pnl_pct}%`} tone={Number(detail.pnl_usd) >= 0 ? 'good' : 'bad'} />
          )}
          <Stat label="Exposure" value={fmtUsd(detail.exposure_usd)} />
        </div>
      </section>
    ) : (
      /* ── Vista normale con grafico ── */
      <>
        {detail.chart && (
          <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">{detail.chart.live ? 'Grafico posizione (live)' : 'Grafico del trade'}</h3>
              <span className="text-xs text-gray-500">{detail.chart.interval}</span>
            </div>
            <TradeCandleChart chart={detail.chart} breakeven={detail.breakeven_price} trailing={detail.trailing_stop} />
            <div className="flex flex-wrap gap-3 text-[10px] text-gray-400">
              <span>⚪ Entry</span>
              <span className={Number(detail.chart.exit_price) >= Number(detail.chart.entry_price) ? 'text-accent-green' : 'text-accent-red'}>● {detail.close_reason ? 'Uscita' : 'Prezzo ora'}</span>
              <span style={{ color: '#fca5a5' }}>- - SL</span>
              {detail.chart.stop_reference && <span className="text-purple-300">- - SL ref</span>}
              {detail.breakeven_price != null && <span style={{ color: '#fcd34d' }}>- - Breakeven</span>}
              {detail.trailing_stop != null && <span style={{ color: '#7dd3fc' }}>- - Trailing</span>}
              <span style={{ color: '#86efac' }}>- - TP1</span>
              <span style={{ color: '#5eead4' }}>- - TP2</span>
            </div>
          </section>
        )}
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
            <Stat label="Entry" value={fmtPriceFull(detail.entry_price)} />
            <Stat label={detail.close_reason ? 'Uscita' : 'Prezzo ora'} value={fmtPriceFull(detail.current_or_exit_price)} />
            <Stat label="Size" value={detail.size} />
            <Stat label="Leverage" value={detail.leverage ? `${detail.leverage.toFixed(2)}x` : '-'} />
          </div>
          {detail.fee_mode && (
            <>
              <div className="mt-3 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase text-gray-500">Costi posizione</span>
                <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${detail.fee_mode === 'none' ? 'bg-gray-700 text-gray-300' : detail.fee_mode === 'maker' ? 'bg-accent-green/15 text-accent-green' : 'bg-accent-yellow/15 text-accent-yellow'}`}>
                  {detail.fee_mode === 'none' ? 'Nessuna fee' : detail.fee_mode === 'maker' ? 'Maker (limit)' : detail.fee_mode === 'all' ? 'Swap + Slippage' : 'Taker (market)'}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {detail.margin_usd != null && <Stat label="Margine" value={fmtUsd(detail.margin_usd)} />}
                {detail.opening_fee_usd != null && <Stat label="Fee applicata" value={fmtUsd(detail.opening_fee_usd)} tone="bad" />}
                {detail.taker_fee_usd != null && <Stat label="Fee taker (0.06%)" value={fmtUsd(detail.taker_fee_usd)} />}
                {detail.maker_fee_usd != null && <Stat label="Fee maker (0.02%)" value={fmtUsd(detail.maker_fee_usd)} />}
                {detail.funding_accrued_usd != null && <Stat label="Funding maturato" value={fmtUsd(detail.funding_accrued_usd)} tone={Number(detail.funding_accrued_usd) >= 0 ? 'good' : 'bad'} />}
                {detail.funding_rate_8h != null && <Stat label="Funding rate (8h)" value={`${(Number(detail.funding_rate_8h) * 100).toFixed(4)}%`} />}
                {detail.swap_fee_usd != null && <Stat label="Swap fee (0.05%)" value={fmtUsd(detail.swap_fee_usd)} tone="bad" />}
                {detail.gas_cost_bnb != null && <Stat label="Gas (BNB)" value={Number(detail.gas_cost_bnb).toFixed(6)} />}
                {detail.slippage_usd != null && Number(detail.slippage_usd) > 0 && <Stat label="Slippage" value={fmtUsd(detail.slippage_usd)} tone="bad" />}
              </div>
            </>
          )}
        </section>
        <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
          <h3 className="text-sm font-semibold text-white">Risk levels</h3>
          {[
            ['Stop loss', detail.stop_loss],
            ...(detail.market === 'perp' ? [[
              detail.stop_reference_field === 'high' ? 'Max candela ref SL' : 'Min candela ref SL',
              detail.stop_reference_price,
            ] as [string, string | null | undefined]] : []),
            ...(detail.market === 'perp' ? [['Liquidation', detail.liquidation_price] as [string, string | null | undefined]] : []),
            ['Breakeven', detail.breakeven_price],
            ['Take profit 1', detail.take_profit_1],
            ['Take profit 2', detail.take_profit_2],
            ['Trailing stop', detail.trailing_stop],
          ].map(([label, value]) => (
            <div key={label} className="flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2 text-xs">
              <span className="text-gray-500">{label}</span>
              <span className={value ? 'text-white' : 'text-gray-600'}>
                {value ? fmtPriceFull(value) : (label === 'Trailing stop' ? 'Non attivo' : '---')}
              </span>
            </div>
          ))}
        </section>
      </>
    )}
    {detail.market === 'perp' && detail.smart_sl_levels && (
      <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Smart Stop Loss</h3>
          {detail.smart_sl_protection_suspended && (
            <span className="rounded-full bg-amber-500/15 px-2 py-1 text-xs font-semibold text-amber-400">BE/Trail sospesi</span>
          )}
          {detail.smart_sl_reentries_exhausted && (
            <span className="rounded-full bg-red-500/15 px-2 py-1 text-xs font-semibold text-red-400">Reentries esauriti</span>
          )}
        </div>
        {detail.smart_sl_levels.map((price, idx) => {
          const stateInfo = detail.smart_sl_state_summary?.[idx];
          const statusLabel = stateInfo?.status === 'sold' ? 'Venduto' : stateInfo?.status === 'rebought' ? 'Ricomprato' : idx === 2 ? 'Classico SL' : 'In attesa';
          const statusColor = stateInfo?.status === 'sold' ? 'text-amber-400' : stateInfo?.status === 'rebought' ? 'text-sky-400' : 'text-gray-500';
          return (
            <div key={idx} className="rounded-lg bg-dark-900 px-3 py-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-gray-500">L{idx + 1} ({idx === 0 ? '25%' : idx === 1 ? '55%' : '20%'})</span>
                <span className="flex items-center gap-2">
                  <span className={statusColor}>{statusLabel}{stateInfo && stateInfo.reentries > 0 ? ` (${stateInfo.reentries}x)` : ''}</span>
                  <span className="text-white">{fmtPriceFull(price)}</span>
                </span>
              </div>
              {stateInfo?.fill_price && (
                <div className="mt-1 flex items-center justify-between text-amber-400/80">
                  <span>Fill vendita</span>
                  <span className="font-semibold">{fmtPriceFull(stateInfo.fill_price)}</span>
                </div>
              )}
              {stateInfo?.rebuy_fill_price && (
                <div className="mt-1 flex items-center justify-between text-sky-400/80">
                  <span>Fill rebuy</span>
                  <span className="font-semibold">{fmtPriceFull(stateInfo.rebuy_fill_price)}</span>
                </div>
              )}
            </div>
          );
        })}
        {(detail.smart_sl_original_tp1 || detail.smart_sl_original_tp2) && (
          <div className="rounded-lg bg-dark-900 px-3 py-2 text-xs space-y-1">
            <span className="text-gray-500 font-semibold">TP adeguati dopo rebuy</span>
            {detail.smart_sl_original_tp1 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">TP1 originale</span>
                <span className="text-gray-400 line-through">{fmtPriceFull(detail.smart_sl_original_tp1)}</span>
              </div>
            )}
            {detail.take_profit_1 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">TP1 nuovo</span>
                <span className="text-emerald-400 font-semibold">{fmtPriceFull(detail.take_profit_1)}</span>
              </div>
            )}
            {detail.smart_sl_original_tp2 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">TP2 originale</span>
                <span className="text-gray-400 line-through">{fmtPriceFull(detail.smart_sl_original_tp2)}</span>
              </div>
            )}
            {detail.take_profit_2 && (
              <div className="flex items-center justify-between">
                <span className="text-gray-500">TP2 nuovo</span>
                <span className="text-emerald-400 font-semibold">{fmtPriceFull(detail.take_profit_2)}</span>
              </div>
            )}
          </div>
        )}
      </section>
    )}
    <section className="rounded-xl bg-dark-800 px-4 py-4 space-y-2">
      <h3 className="text-sm font-semibold text-white">Timeline</h3>
      <p className="text-xs text-gray-500">Open {new Date(detail.opened_at).toLocaleString('it-IT')}</p>
      <p className="text-xs text-gray-500">Close {detail.closed_at ? new Date(detail.closed_at).toLocaleString('it-IT') : '-'}</p>
      <p className="text-xs text-gray-500">Reason {detail.close_reason ? (CLOSE_REASON_LABELS[detail.close_reason]?.label ?? detail.close_reason) : '-'}</p>
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

// ── Bank · Riserva di Valore ────────────────────────────────────────────────

const RESERVE_COLORS: Record<string, string> = {
  BTC: '#F7931A', ETH: '#8AA0FF', BNB: '#F0B90B', SOL: '#14F195', TRX: '#FF6B6B',
};
const RESERVE_ERROR_LABELS: Record<string, string> = {
  no_profit_available: 'Nessun profitto sopra il capitale iniziale',
  below_min_transfer: 'Importo sotto il minimo',
  frozen: 'La riserva è congelata',
  cooldown: 'Prelievo in cooldown, riprova più tardi',
  drawdown_guard: 'Prelievi bloccati durante il blocco drawdown',
  empty: 'La riserva è vuota',
  price_unavailable: 'Prezzi non disponibili, riprova',
  amount_not_a_number: 'Importo non valido',
};

const BankChart: FC<{
  history: ReserveHistoryResponse | null;
  mode: 'pct' | 'usd';
}> = ({ history, mode }) => {
  const items = history?.items ?? [];
  if (items.length < 2) {
    return <div className="py-6 text-center text-xs text-gray-500">Storico insufficiente per il grafico</div>;
  }
  const W = 320, H = 150, padL = 38, padR = 12, padT = 8, padB = 18;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const n = items.length;

  const series: Array<{ key: string; color: string; vals: (number | null)[]; label: string }> =
    mode === 'usd'
      ? [{ key: 'v', color: PNL_COLOR, label: 'Valore', vals: items.map((i) => Number(i.total_value_usd)) }]
      : [
          { key: 'r', color: '#F0B90B', label: 'Riserva', vals: items.map((i) => (i.reserve_pct != null ? Number(i.reserve_pct) : null)) },
          { key: 'b', color: '#3B82F6', label: 'BTC', vals: items.map((i) => (i.btc_hold_pct != null ? Number(i.btc_hold_pct) : null)) },
          { key: 't', color: '#8B95A7', label: 'Trading', vals: items.map((i) => (i.trading_pct != null ? Number(i.trading_pct) : null)) },
        ];

  const pool = series.flatMap((s) => s.vals.filter((v): v is number => v != null));
  if (mode === 'pct') pool.push(0);
  let lo = pool.length ? Math.min(...pool) : 0;
  let hi = pool.length ? Math.max(...pool) : 1;
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;

  const xAt = (idx: number) => (n <= 1 ? padL + plotW / 2 : padL + (idx / (n - 1)) * plotW);
  const yAt = (v: number) => padT + (1 - (v - lo) / (hi - lo)) * plotH;
  const poly = (vals: (number | null)[]) =>
    vals.map((v, i) => (v == null ? null : `${xAt(i).toFixed(1)},${yAt(v).toFixed(1)}`)).filter(Boolean).join(' ');

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 'auto' }} role="img" aria-label="Andamento riserva">
        {mode === 'pct' && (
          <line x1={padL} y1={yAt(0)} x2={W - padR} y2={yAt(0)} stroke="#9ca3af" strokeOpacity="0.4" strokeDasharray="3 3" />
        )}
        {[hi, (hi + lo) / 2, lo].map((v, i) => (
          <text key={i} x={padL - 4} y={yAt(v) + 3} textAnchor="end" fontSize="9" fill="#6b7280">
            {mode === 'usd' ? `$${v.toFixed(0)}` : `${v.toFixed(1)}%`}
          </text>
        ))}
        {series.map((s) => {
          const pts = poly(s.vals);
          return pts ? <polyline key={s.key} points={pts} fill="none" stroke={s.color} strokeWidth={s.key === 'r' || s.key === 'v' ? 2.4 : 1.8} strokeLinejoin="round" strokeLinecap="round" /> : null;
        })}
      </svg>
      <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-[10px] text-gray-400">
        {series.map((s) => (
          <span key={s.key}><span style={{ color: s.color }}>●</span> {s.label}</span>
        ))}
      </div>
    </div>
  );
};

const BankPane: FC<{ adminToken: string }> = ({ adminToken }) => {
  const [view, setView] = useState<ReserveView | null>(null);
  const [history, setHistory] = useState<ReserveHistoryResponse | null>(null);
  const [txns, setTxns] = useState<ReserveTransactionsResponse | null>(null);
  const [range, setRange] = useState<EquityRange>('7d');
  const [chartMode, setChartMode] = useState<'pct' | 'usd'>('pct');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const [amount, setAmount] = useState('');
  const [nowTs, setNowTs] = useState(() => Date.now());
  useEffect(() => { const id = window.setInterval(() => setNowTs(Date.now()), 30_000); return () => window.clearInterval(id); }, []);

  const load = useCallback(async () => {
    try {
      const [v, t] = await Promise.all([fetchReserve(), fetchReserveTransactions(8)]);
      setView(v); setTxns(t); setErr('');
    } catch {
      setErr('Impossibile caricare la riserva');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); const id = window.setInterval(() => { void load(); }, 30_000); return () => window.clearInterval(id); }, [load]);
  useEffect(() => { fetchReserveHistory(range).then(setHistory).catch(() => {}); }, [range]);

  const runAction = useCallback(async (fn: () => Promise<unknown>) => {
    setBusy(true); setErr('');
    try {
      await fn();
      await load();
      setHistory(await fetchReserveHistory(range).catch(() => history));
    } catch (e) {
      const code = (e as { payload?: { detail?: string } })?.payload?.detail
        ?? (e as { message?: string })?.message ?? '';
      setErr(RESERVE_ERROR_LABELS[code] ?? 'Operazione non riuscita');
    } finally {
      setBusy(false);
    }
  }, [load, range, history]);

  if (loading && !view) {
    return <div className="py-10 text-center text-sm text-gray-500">Caricamento riserva…</div>;
  }
  if (!view) {
    return <EmptyState title="Riserva non disponibile" detail={err || 'Riprova tra poco.'} />;
  }

  const value = Number(view.value_usd);
  const pnl = Number(view.pnl_usd);
  const capacity = Number(view.deposit_capacity_usd);
  const amountNum = parseFloat(amount);
  const canTransferIn = adminToken && !view.frozen && capacity > 0 && amountNum > 0 && amountNum <= capacity;
  const withdrawAt = view.withdrawal_available_at ? new Date(view.withdrawal_available_at) : null;
  const inCooldown = withdrawAt != null && withdrawAt.getTime() > nowTs;

  const hasAssets = view.holdings.some((h) => Number(h.value_usd) > 0);
  const emptyReserve = value < 0.01 && Number(view.cash_usd) < 0.01;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-white">🏦 Riserva di Valore</h3>
        {view.frozen && <span className="rounded-full bg-accent-blue/15 px-2 py-0.5 text-[11px] font-semibold text-accent-blue">congelata</span>}
      </div>

      <div className="rounded-xl border border-accent-yellow/20 bg-gradient-to-b from-accent-yellow/10 to-transparent px-4 py-3">
        <p className="text-[11px] uppercase text-gray-500">Valore riserva</p>
        <p className="text-2xl font-bold tabular-nums text-white">{fmtUsd(value)}</p>
        <p className={`text-xs tabular-nums ${pnl >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
          {pnl >= 0 ? '+' : ''}{fmtUsd(pnl)} · {fmtSignedPct(view.pnl_pct)} <span className="text-gray-500">· {view.portfolio_pct.toFixed(1)}% del portafoglio</span>
        </p>
        <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-gray-400">
          <span>USDC da investire: <b className="text-gray-200">{fmtUsd(Number(view.cash_usd))}</b></span>
          <span>Fee pagate: <b className="text-gray-200">{fmtUsd(Number(view.fees_total_usd))}</b></span>
          <span>Disponibile da spostare: <b className="text-accent-yellow">{fmtUsd(capacity)}</b></span>
          {view.next_deploy_at && <span>Prossimo deploy: <b className="text-gray-200">{new Date(view.next_deploy_at).toLocaleDateString('it-IT', { day: '2-digit', month: 'short' })}</b></span>}
        </div>
      </div>

      {emptyReserve ? (
        <EmptyState
          title="La riserva è vuota"
          detail="Sposta parte dei profitti qui dentro: verranno convertiti in BTC, ETH, BNB, SOL e TRX e faranno da zavorra stabile al portafoglio."
        />
      ) : (
        <>
          <div className="rounded-xl bg-dark-800 px-3 py-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex gap-1">
                {(['24h', '7d', 'all'] as EquityRange[]).map((r) => (
                  <button key={r} onClick={() => { hapticLight(); setRange(r); }} className={`rounded-md px-2 py-1 text-[11px] font-semibold ${range === r ? 'bg-accent-blue text-white' : 'bg-dark-700 text-gray-400'}`}>
                    {r === '24h' ? '24h' : r === '7d' ? '7g' : 'Tutto'}
                  </button>
                ))}
              </div>
              <button onClick={() => setChartMode((m) => (m === 'pct' ? 'usd' : 'pct'))} className="rounded-md bg-dark-700 px-2 py-1 text-[11px] font-semibold text-gray-300">
                {chartMode === 'pct' ? '% rendimento' : '$ valore'}
              </button>
            </div>
            <BankChart history={history} mode={chartMode} />
          </div>

          <div className="rounded-xl bg-dark-800 px-3 py-3">
            <p className="mb-2 text-xs font-semibold uppercase text-gray-500">Pesi · corrente vs target</p>
            <div className="space-y-2">
              {view.holdings.map((h) => (
                <div key={h.asset}>
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-gray-200">{h.asset}{h.off_target && <span className="ml-1 text-accent-yellow">•</span>}</span>
                    <span className="tabular-nums text-gray-400">{h.weight_pct.toFixed(1)}% <span className="text-gray-600">/ {h.target_weight_pct}</span></span>
                  </div>
                  <div className="mt-1 h-1.5 overflow-hidden rounded bg-dark-700">
                    <span className="block h-full" style={{ width: `${Math.min(100, h.weight_pct)}%`, background: RESERVE_COLORS[h.asset] ?? '#F0B90B' }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {hasAssets && (
            <div className="rounded-xl bg-dark-800 px-3 py-2">
              <p className="mb-1 px-1 text-xs font-semibold uppercase text-gray-500">Posizioni</p>
              {view.holdings.filter((h) => Number(h.value_usd) > 0).map((h) => (
                <div key={h.asset} className="flex items-center justify-between border-b border-dark-700 py-2 text-sm last:border-0">
                  <div>
                    <span className="font-semibold text-white">{h.asset}</span>
                    <span className="ml-2 text-[11px] text-gray-500">{Number(h.quantity).toPrecision(4)} · costo {fmtPrice(h.avg_cost_usd)}</span>
                  </div>
                  <div className="text-right">
                    <div className="tabular-nums text-white">{fmtUsd(Number(h.value_usd))}</div>
                    <div className={`text-[11px] tabular-nums ${Number(h.pnl_usd) >= 0 ? 'text-accent-green' : 'text-accent-red'}`}>
                      {Number(h.pnl_usd) >= 0 ? '+' : ''}{fmtUsd(Number(h.pnl_usd))}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {txns && txns.items.length > 0 && (
        <div className="rounded-xl bg-dark-800 px-3 py-2">
          <p className="mb-1 px-1 text-xs font-semibold uppercase text-gray-500">Movimenti</p>
          {txns.items.map((t) => (
            <div key={t.id} className="flex items-center justify-between border-b border-dark-700 py-1.5 text-xs last:border-0">
              <span className="text-gray-300">
                {t.type === 'sweep' ? 'Sweep profitti' : t.type === 'deploy_buy' ? `Acquisto ${t.asset}` : t.type === 'transfer_in' ? 'Versamento' : t.type === 'transfer_out' ? 'Prelievo' : t.type.startsWith('rebalance') ? 'Ribilancio' : t.type}
                <span className="ml-2 text-gray-600">{new Date(t.created_at).toLocaleString('it-IT', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })}</span>
              </span>
              <span className="tabular-nums text-gray-200">{fmtUsd(Number(t.value_usd))}{Number(t.fee_usd) > 0 && <span className="text-gray-600"> · fee {fmtUsd(Number(t.fee_usd))}</span>}</span>
            </div>
          ))}
        </div>
      )}

      {adminToken ? (
        <div className="rounded-xl bg-dark-800 px-4 py-3 space-y-3">
          <p className="text-xs font-semibold uppercase text-gray-500">Azioni</p>
          {err && <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{err}</p>}
          <input
            type="number" inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)}
            placeholder="Importo USD"
            className="w-full rounded-lg border border-dark-600 bg-dark-900 px-3 py-2 text-sm text-white outline-none focus:border-accent-blue"
          />
          <div className="grid grid-cols-2 gap-2">
            <button
              disabled={!canTransferIn || busy}
              onClick={() => { void runAction(() => reserveTransfer(amountNum, 'in', adminToken)).then(() => setAmount('')); }}
              className="rounded-lg bg-accent-yellow px-3 py-2 text-xs font-bold text-dark-900 disabled:opacity-40"
            >Sposta nella riserva</button>
            <button
              disabled={!adminToken || busy || inCooldown || value < 0.01}
              onClick={() => { void runAction(() => reserveTransfer(amountNum || value, 'out', adminToken)).then(() => setAmount('')); }}
              className="rounded-lg border border-dark-600 px-3 py-2 text-xs font-bold text-gray-300 disabled:opacity-40"
            >Preleva{inCooldown ? ' (cooldown)' : ''}</button>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button disabled={busy} onClick={() => void runAction(() => reserveDeploy(adminToken))} className="rounded-lg bg-dark-700 px-3 py-2 text-xs font-semibold text-gray-200 disabled:opacity-40">Deploy ora</button>
            <button disabled={busy} onClick={() => void runAction(() => reserveRebalance(false, adminToken))} className="rounded-lg bg-dark-700 px-3 py-2 text-xs font-semibold text-gray-200 disabled:opacity-40">Ribilancia</button>
          </div>
          <p className="text-[10px] text-gray-500">I pesi target e i parametri (sweep, cooldown, deploy) si impostano in <b>Setup › Bank</b>.</p>
        </div>
      ) : (
        <p className="rounded-lg bg-dark-800 px-3 py-2 text-xs text-gray-500">Inserisci l'admin token in Setup per spostare capitale nella riserva.</p>
      )}
    </div>
  );
};

// Cache a livello di modulo: conserva l'ultimo stato dell'agente tra unmount/mount
// (es. quando si cambia tab e si torna). Al rientro lo stato si inizializza con gli
// ultimi valori noti e l'aggiornamento avviene in silenzio, invece di mostrare i
// valori a 0 durante il primo fetch.
const agentCache: {
  pane: AgentPane;
  status: AgentStatus | null;
  spot: SpotView | null;
  perp: PerpView | null;
  global: GlobalView | null;
  equity: EquityCurveResponse | null;
  equityRange: EquityRange;
  decisions: AgentDecisionResponse | null;
  assetBreakdown: AssetBreakdownResponse | null;
  settings: AgentMobileSettings | null;
  execWallets: ExecutionWalletsResponse | null;
  claudeUsage: ClaudeUsageView | null;
  loaded: boolean;
} = {
  pane: 'spot', status: null, spot: null, perp: null, global: null, equity: null,
  equityRange: '24h', decisions: null, assetBreakdown: null, settings: null,
  execWallets: null, claudeUsage: null, loaded: false,
};

const AgentTab: FC<AgentTabProps> = ({
  adminToken,
  onAdminToken,
  eligibleTokens,
  selectedAiSymbols,
  watchlistSaving,
  watchlistError,
  onToggleAiSymbol,
}) => {
  const [pane, setPane] = useState<AgentPane>(agentCache.pane);
  const [status, setStatus] = useState<AgentStatus | null>(agentCache.status);
  const [spot, setSpot] = useState<SpotView | null>(agentCache.spot);
  const [perp, setPerp] = useState<PerpView | null>(agentCache.perp);
  const [global, setGlobal] = useState<GlobalView | null>(agentCache.global);
  const [equity, setEquity] = useState<EquityCurveResponse | null>(agentCache.equity);
  const [equityRange, setEquityRange] = useState<EquityRange>(agentCache.equityRange);
  const equityRangeRef = useRef<EquityRange>(equityRange);
  equityRangeRef.current = equityRange;
  const [decisions, setDecisions] = useState<AgentDecisionResponse | null>(agentCache.decisions);
  const [assetBreakdown, setAssetBreakdown] = useState<AssetBreakdownResponse | null>(agentCache.assetBreakdown);
  const [tradeDetail, setTradeDetail] = useState<TradeDetail | null>(null);
  const detailTradeIdRef = useRef<string | null>(null);
  const [settings, setSettings] = useState<AgentMobileSettings>(agentCache.settings ?? defaultSettings);
  const [settingsDirty, setSettingsDirty] = useState(false);
  const settingsDirtyRef = useRef(false);
  const handleSettingsChange = useCallback((next: AgentMobileSettings) => {
    settingsDirtyRef.current = true;
    setSettingsDirty(true);
    setSettings(next);
  }, []);
  const [execWallets, setExecWallets] = useState<ExecutionWalletsResponse | null>(agentCache.execWallets);
  const [claudeUsage, setClaudeUsage] = useState<ClaudeUsageView | null>(agentCache.claudeUsage);
  const [validation, setValidation] = useState<CredentialValidationResponse | null>(null);
  const [refreshing, setRefreshing] = useState(!agentCache.loaded);
  const [justSynced, setJustSynced] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');
  const refreshInFlightRef = useRef(false);
  const fastRefreshInFlightRef = useRef(false);

  const loadActiveTradeDetail = useCallback(async (tradeId: string, enrichChart = false) => {
    const cached = getCachedTradeDetail(tradeId);
    if (cached && (!enrichChart || hasCompleteTradeChart(cached))) {
      if (detailTradeIdRef.current === tradeId) setTradeDetail(cached);
      return cached;
    }
    const detail = await fetchTradeDetailDeduped(tradeId, {
      enrichChart,
      timeoutMs: enrichChart ? TRADE_DETAIL_ENRICH_TIMEOUT_MS : TRADE_DETAIL_BASE_TIMEOUT_MS,
    });
    if (detailTradeIdRef.current === tradeId) {
      setTradeDetail(detail);
    }
    return detail;
  }, []);

  const prefetchTradeDetails = useCallback((tradeIds: Array<string | null | undefined>) => {
    const activeTradeId = detailTradeIdRef.current;
    const ids = Array.from(new Set(tradeIds.filter((id): id is string => Boolean(id))))
      .filter((id) => id !== activeTradeId && shouldPrefetchTradeDetail(id));
    if (ids.length === 0) return;

    const queue = [...ids];
    const nextRetryAt = Date.now() + TRADE_DETAIL_PREFETCH_RETRY_MS;
    ids.forEach((tradeId) => tradeDetailPrefetchRetryAt.set(tradeId, nextRetryAt));

    const workers = Array.from(
      { length: Math.min(TRADE_DETAIL_PREFETCH_CONCURRENCY, queue.length) },
      async () => {
        while (queue.length > 0) {
          const tradeId = queue.shift();
          if (!tradeId) return;
          try {
            let detail = getCachedTradeDetail(tradeId);
            if (!detail) {
              detail = await fetchTradeDetailDeduped(tradeId, { timeoutMs: TRADE_DETAIL_BASE_TIMEOUT_MS });
            }
          } catch {
            // Background warm-up: the tap handler still owns visible error handling.
          }
        }
      },
    );

    Promise.allSettled(workers).catch(() => {});
  }, []);

  const closeTradeDetail = useCallback(() => {
    detailTradeIdRef.current = null;
    setLoadingDetail(false);
    setTradeDetail(null);
  }, []);

  const refresh = useCallback(async (silent = false) => {
    if (refreshInFlightRef.current) return;
    if (fastRefreshInFlightRef.current) return;
    refreshInFlightRef.current = true;
    if (!silent) setRefreshing(true);
    try {
      // Caricamento progressivo: ogni scheda si popola appena la sua chiamata risponde,
      // senza aspettare la piu' lenta. I dati precedenti restano visibili nel frattempo.
      const activeTradeId = detailTradeIdRef.current;
      const detailFetch = activeTradeId && !hasCompleteCachedTradeDetail(activeTradeId)
        ? loadActiveTradeDetail(activeTradeId, true).catch(() => {})
        : Promise.resolve();
      const results = await Promise.allSettled([
        fetchAgentStatus().then(setStatus),
        fetchSpotView().then(setSpot),
        fetchPerpView().then(setPerp),
        fetchGlobalView().then(setGlobal),
        fetchAgentSettings().then((r) => {
          if (!settingsDirtyRef.current) setSettings(r.settings);
        }),
        fetchEquityCurve(equityRangeRef.current).then(setEquity),
        fetchAgentDecisions().then(setDecisions),
        fetchAssetBreakdown().then(setAssetBreakdown),
        detailFetch,
      ]);
      const failed = results.filter((r) => r.status === 'rejected').length;
      setError(failed > 0 ? `${failed} endpoint non raggiungibili` : '');
      if (!silent) {
        setJustSynced(true);
        window.setTimeout(() => setJustSynced(false), 2500);
      }
    } finally {
      setRefreshing(false);
      refreshInFlightRef.current = false;
    }
  }, [loadActiveTradeDetail]);

  // Mirror dello stato nella cache di modulo: al prossimo mount (rientro nella tab)
  // i valori vengono ripristinati senza azzeramenti.
  useEffect(() => {
    agentCache.pane = pane;
    agentCache.status = status;
    agentCache.spot = spot;
    agentCache.perp = perp;
    agentCache.global = global;
    agentCache.equity = equity;
    agentCache.equityRange = equityRange;
    agentCache.decisions = decisions;
    agentCache.assetBreakdown = assetBreakdown;
    agentCache.settings = settings;
    agentCache.execWallets = execWallets;
    agentCache.claudeUsage = claudeUsage;
    if (status || spot || perp || global || equity) agentCache.loaded = true;
  }, [pane, status, spot, perp, global, equity, equityRange, decisions, assetBreakdown, settings, execWallets, claudeUsage]);

  useEffect(() => {
    // Al primo mount in assoluto mostra l'indicatore; ai rientri (cache popolata)
    // aggiorna in silenzio mantenendo i valori precedenti.
    refresh(agentCache.loaded);
  }, [refresh]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      refresh();
    }, AGENT_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);

  // Refresh leggero: aggiorna solo le viste principali e salta se un ciclo e' gia' in corso.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (refreshInFlightRef.current) return;
      if (fastRefreshInFlightRef.current) return;
      fastRefreshInFlightRef.current = true;
      Promise.allSettled([
        fetchSpotView().then(setSpot),
        fetchPerpView().then(setPerp),
        fetchGlobalView().then(setGlobal),
      ]).finally(() => {
        fastRefreshInFlightRef.current = false;
      });
    }, AGENT_FAST_REFRESH_MS);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (pane !== 'wallet') return;
    let active = true;
    const loadWallets = () => {
      fetchExecutionWallets()
        .then((value) => { if (active) setExecWallets(value); })
        .catch(() => {});
    };
    loadWallets();
    const timer = window.setInterval(loadWallets, 300_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [pane]);

  useEffect(() => {
    if (spot) {
      prefetchTradeDetails([
        ...spot.open_positions.map((position) => position.open_trade_id),
        ...spot.history.slice(0, TRADE_DETAIL_PREFETCH_LIMIT).map((trade) => trade.trade_id),
      ]);
    }
    if (perp) {
      prefetchTradeDetails([
        ...perp.open_positions.map((position) => position.open_trade_id),
        ...perp.history.slice(0, TRADE_DETAIL_PREFETCH_LIMIT).map((trade) => trade.trade_id),
      ]);
    }
  }, [spot, perp, prefetchTradeDetails]);

  // Refetch immediato della curva quando l'utente cambia il range (24h/7g/Tutto),
  // senza ricaricare tutte le altre schede.
  useEffect(() => {
    fetchEquityCurve(equityRange).then(setEquity).catch(() => {});
  }, [equityRange]);

  // Spesa API Claude: la carichiamo SOLO quando il pane Global e' attivo e con
  // cadenza ridotta (non cambia di secondo in secondo). Cosi' non appesantisce
  // gli altri pane ne' il refresh principale.
  useEffect(() => {
    if (pane !== 'global') return;
    let active = true;
    const load = () => { fetchClaudeUsage().then((v) => { if (active) setClaudeUsage(v); }).catch(() => {}); };
    load();
    const timer = window.setInterval(load, 300_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [pane]);

  const handleSave = async () => {
    setSaving(true);
    setActionError('');
    try {
      const response = await saveAgentSettings(settings, adminToken);
      settingsDirtyRef.current = false;
      setSettingsDirty(false);
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

  const handleCloseAll = async () => {
    if (!window.confirm('Chiudere TUTTE le posizioni spot e perp al prezzo di mercato e mettere in pausa l\'agente?')) return;
    setSaving(true);
    setActionError('');
    try {
      const result = await riskCloseAll(adminToken);
      setStatus(result);
      await refresh(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Close-all failed');
    } finally {
      setSaving(false);
    }
  };

  const handleAdjustEquity = async (amount: number) => {
    const verb = amount >= 0 ? 'Versare' : 'Prelevare';
    const prep = amount >= 0 ? 'in' : 'da';
    if (!window.confirm(`${verb} ${Math.abs(amount).toFixed(2)}$ ${prep} liquidità?\n\nAggiorna l'equity, non il PnL.`)) return;
    setSaving(true);
    setActionError('');
    try {
      const result = await adjustEquity(amount, null, adminToken);
      window.alert(`Applicato ${amount >= 0 ? '+' : ''}${amount}$. Equity ora: ${Number(result.total_equity_usd).toFixed(2)}$.`);
      await refresh(true);
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Adjust equity failed');
    } finally {
      setSaving(false);
    }
  };

  const handleTradeDetail = async (tradeId: string) => {
    detailTradeIdRef.current = tradeId;
    setActionError('');
    const cached = getCachedTradeDetail(tradeId);
    if (cached) {
      setTradeDetail(cached);
      setLoadingDetail(false);
      if (!hasCompleteTradeChart(cached)) {
        loadActiveTradeDetail(tradeId, true).catch(() => {});
      }
      return;
    }
    setLoadingDetail(true);
    try {
      await loadActiveTradeDetail(tradeId, true);
    } catch (err) {
      if (detailTradeIdRef.current === tradeId) {
        setActionError(err instanceof Error ? err.message : 'Unable to load trade detail');
      }
    } finally {
      if (detailTradeIdRef.current === tradeId) {
        setLoadingDetail(false);
      }
    }
    if (detailTradeIdRef.current === tradeId && !hasCompleteCachedTradeDetail(tradeId)) {
      loadActiveTradeDetail(tradeId, true).catch(() => {});
    }
  };

  const statusTone = useMemo(() => {
    if (status?.kill_switch === 'hard_stop') return 'text-accent-red';
    if (status?.kill_switch === 'soft_stop' || status?.kill_switch === 'degraded') return 'text-accent-yellow';
    return 'text-accent-green';
  }, [status]);

  return (
    <div className="space-y-4">
      {loadingDetail && (
        <div className="fixed inset-0 z-50 flex flex-col items-center justify-center bg-black/70">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-dark-700 border-t-accent-yellow" />
          <p className="mt-3 text-sm text-gray-400">Caricamento dettaglio...</p>
          <button
            type="button"
            onClick={closeTradeDetail}
            className="mt-4 rounded-lg bg-dark-800 px-4 py-2 text-sm font-semibold text-gray-300"
          >
            Annulla
          </button>
        </div>
      )}
      {actionError && !tradeDetail && (
        <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{actionError}</p>
      )}
      {tradeDetail ? (
        <TradeDetailScreen detail={tradeDetail} onBack={closeTradeDetail} />
      ) : (
        <>
      <div className="rounded-xl bg-dark-800 px-4 py-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white">AI Agent</p>
            <p className="truncate text-xs text-gray-500">{status?.mode ?? settings.mode} - {status?.execution_mode ?? settings.execution_mode}</p>
          </div>
          <button
            onClick={() => void refresh()}
            disabled={refreshing}
            aria-label="Aggiorna"
            className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-dark-700 text-gray-300 disabled:opacity-70"
          >
            {refreshing ? (
              <svg className="h-4 w-4 animate-spin text-accent-blue" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z" />
              </svg>
            ) : justSynced ? (
              <svg className="h-4 w-4 text-accent-green" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h5M20 20v-5h-5M5 9a7 7 0 0112-3m2 9a7 7 0 01-12 3" />
              </svg>
            )}
          </button>
        </div>
        <div className="mt-3 flex items-center justify-between rounded-lg bg-dark-900 px-3 py-2">
          <span className="text-xs text-gray-500">Runtime</span>
          <span className={`text-xs font-semibold ${statusTone}`}>{status?.kill_switch ?? 'loading'}</span>
        </div>
        {status?.filters && (
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div className={`rounded-lg px-3 py-1.5 text-xs ${
              !status.filters.reversal?.enabled ? 'bg-dark-900 text-gray-600'
              : status.filters.reversal?.blocks_long || status.filters.reversal?.blocks_short ? 'bg-accent-red/10 text-accent-red'
              : 'bg-accent-green/10 text-accent-green'
            }`}>
              <span className="font-semibold">Reversal</span>{' '}
              {!status.filters.reversal?.enabled ? 'off'
                : status.filters.reversal?.blocks_long ? '⛔ long'
                : status.filters.reversal?.blocks_short ? '⛔ short'
                : '✓ ok'}
            </div>
            <div className={`rounded-lg px-3 py-1.5 text-xs ${
              !status.filters.trend_shock?.enabled ? 'bg-dark-900 text-gray-600'
              : status.filters.trend_shock?.blocks_all ? 'bg-accent-red/10 text-accent-red'
              : 'bg-accent-green/10 text-accent-green'
            }`}>
              <span className="font-semibold">Shock BTC</span>{' '}
              {!status.filters.trend_shock?.enabled ? 'off'
                : status.filters.trend_shock?.state === 'BLOCKED' ? '⛔ blocked'
                : status.filters.trend_shock?.state === 'RECOVERING' ? `⏳ ${status.filters.trend_shock.recovery_count}/3`
                : '✓ ok'}
            </div>
          </div>
        )}
      </div>

      <div className="grid grid-cols-3 gap-1.5">
        <SegmentButton id="spot" label="Spot" active={pane === 'spot'} onClick={setPane} />
        <SegmentButton id="perp" label="Perp" active={pane === 'perp'} onClick={setPane} />
        <SegmentButton id="global" label="Global" active={pane === 'global'} onClick={setPane} />
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        <SegmentButton id="wallet" label="Wallet" active={pane === 'wallet'} onClick={setPane} />
        <SegmentButton id="coins" label="Coins" active={pane === 'coins'} onClick={setPane} />
        <SegmentButton id="setup" label="Setup" active={pane === 'setup'} onClick={setPane} />
      </div>
      <button
        type="button"
        onClick={() => { hapticLight(); setPane('bank'); }}
        className={`w-full rounded-xl px-4 py-3.5 text-sm font-bold transition-colors ${
          pane === 'bank'
            ? 'bg-accent-yellow text-dark-900'
            : 'border border-accent-yellow/40 bg-accent-yellow/15 text-accent-yellow'
        }`}
      >
        🏦 Bank · Riserva di Valore
      </button>

      {error && <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{error}</p>}
      {watchlistError && pane !== 'coins' && (
        <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{watchlistError}</p>
      )}
      {pane === 'spot' && <SpotPane data={spot} onTrade={(tradeId) => void handleTradeDetail(tradeId)} />}
      {pane === 'perp' && <PerpPane data={perp} onTrade={(tradeId) => void handleTradeDetail(tradeId)} />}
      {pane === 'global' && <GlobalPane data={global} status={status} equity={equity} equityRange={equityRange} onEquityRange={setEquityRange} decisions={decisions} assetBreakdown={assetBreakdown} claudeUsage={claudeUsage} />}
      {pane === 'wallet' && <WalletPane execWallets={execWallets} spot={spot} perp={perp} />}
      {pane === 'bank' && <BankPane adminToken={adminToken} />}
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
          onSettings={handleSettingsChange}
          dirty={settingsDirty}
          adminToken={adminToken}
          onAdminToken={onAdminToken}
          validation={validation}
          agentStatus={status}
          saving={saving}
          actionError={actionError}
          onSave={handleSave}
          onValidate={handleValidate}
          onKill={handleKill}
          onCloseAll={handleCloseAll}
          onAdjustEquity={handleAdjustEquity}
        />
      )}
        </>
      )}
    </div>
  );
};

export default AgentTab;
