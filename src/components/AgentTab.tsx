import { useCallback, useEffect, useMemo, useState, type FC } from 'react';
import {
  fetchAgentSettings,
  fetchAgentStatus,
  fetchGlobalView,
  fetchMobileWallet,
  fetchPerpView,
  fetchSpotView,
  saveAgentSettings,
  setKillSwitch,
  validateOnboarding,
  type AgentMobileSettings,
  type AgentStatus,
  type CredentialValidationResponse,
  type GlobalView,
  type KillSwitchState,
  type MobileWalletView,
  type PerpView,
  type SpotView,
} from '../services/agentApi';
import { hapticLight } from '../utils/haptics';

type AgentPane = 'spot' | 'perp' | 'global' | 'setup';

const fmtUsd = (value: string | number | null | undefined) => {
  const n = Number(value ?? 0);
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 2 })}`;
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

const SpotPane: FC<{ data: SpotView | null }> = ({ data }) => {
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
                <p className={Number(position.pnl_unrealized) >= 0 ? 'text-accent-green text-sm font-bold' : 'text-accent-red text-sm font-bold'}>{fmtUsd(position.pnl_unrealized)}</p>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-500">
                <span>Entry {fmtUsd(position.entry_price)}</span>
                <span>Now {fmtUsd(position.current_price)}</span>
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
          {data!.history.slice(0, 5).map((trade) => (
            <div key={trade.trade_id} className="flex items-center justify-between rounded-lg bg-dark-800 px-3 py-2 text-xs">
              <span className="text-white">{trade.asset} {trade.side}</span>
              <span className="text-gray-500">{trade.status}</span>
            </div>
          ))}
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessun trade oggi" detail="Lo storico si popola quando l'agente prepara o chiude operazioni spot." />
      )}
    </div>
  );
};

const PerpPane: FC<{ data: PerpView | null }> = ({ data }) => {
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
                <span>PnL {fmtUsd(position.pnl_unrealized)}</span>
                <span>Liq {position.liquidation_price ? fmtUsd(position.liquidation_price) : '-'}</span>
                <span>Funding {position.funding_rate ? fmtPct(Number(position.funding_rate) * 100) : '-'}</span>
                <span>{position.status}</span>
              </div>
            </div>
          ))}
        </div>
      ) : hasActivity && (
        <EmptyState title="Nessuna posizione aperta" detail="Le posizioni perp long/short appariranno qui." />
      )}
      {!hasHistory && hasActivity && (
        <EmptyState title="Nessun trade perp" detail="Lo storico perp si popola dopo le prime operazioni." />
      )}
    </div>
  );
};

const GlobalPane: FC<{ data: GlobalView | null; status: AgentStatus | null }> = ({ data, status }) => {
  const hasHistory = (data?.pnl_history.length ?? 0) > 0;
  const hasPortfolio = Number(data?.total_equity_usd ?? 0) > 0 || Number(data?.initial_equity_usd ?? 0) > 0;
  const hasTradesToday = Number(data?.trades_today ?? 0) > 0;

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
          <div className="mt-3 flex h-20 items-end gap-1">
            {data!.pnl_history.slice(-24).map((point) => {
              const equity = Number(point.total_equity_usd);
              const max = Math.max(...data!.pnl_history.slice(-24).map((p) => Number(p.total_equity_usd)), 1);
              return (
                <span
                  key={point.timestamp_utc}
                  className="flex-1 rounded-t bg-accent-blue/70"
                  style={{ height: `${Math.max(8, (equity / max) * 80)}px` }}
                />
              );
            })}
          </div>
        </div>
      ) : hasPortfolio && (
        <EmptyState title="Nessuno storico PnL" detail="La curva equity apparira' dopo i prossimi snapshot." />
      )}
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

const AgentTab: FC = () => {
  const [pane, setPane] = useState<AgentPane>('spot');
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const [spot, setSpot] = useState<SpotView | null>(null);
  const [perp, setPerp] = useState<PerpView | null>(null);
  const [global, setGlobal] = useState<GlobalView | null>(null);
  const [settings, setSettings] = useState<AgentMobileSettings>(defaultSettings);
  const [wallet, setWallet] = useState<MobileWalletView | null>(null);
  const [validation, setValidation] = useState<CredentialValidationResponse | null>(null);
  const [adminToken, setAdminToken] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [actionError, setActionError] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [statusData, spotData, perpData, globalData, settingsData, walletData] = await Promise.all([
        fetchAgentStatus(),
        fetchSpotView(),
        fetchPerpView(),
        fetchGlobalView(),
        fetchAgentSettings(),
        fetchMobileWallet(),
      ]);
      setStatus(statusData);
      setSpot(spotData);
      setPerp(perpData);
      setGlobal(globalData);
      setSettings(settingsData.settings);
      setWallet(walletData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load agent data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
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

  const statusTone = useMemo(() => {
    if (status?.kill_switch === 'hard_stop') return 'text-accent-red';
    if (status?.kill_switch === 'soft_stop' || status?.kill_switch === 'degraded') return 'text-accent-yellow';
    return 'text-accent-green';
  }, [status]);

  return (
    <div className="space-y-4">
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

      <div className="grid grid-cols-4 gap-1.5">
        <SegmentButton id="spot" label="Spot" active={pane === 'spot'} onClick={setPane} />
        <SegmentButton id="perp" label="Perp" active={pane === 'perp'} onClick={setPane} />
        <SegmentButton id="global" label="Global" active={pane === 'global'} onClick={setPane} />
        <SegmentButton id="setup" label="Setup" active={pane === 'setup'} onClick={setPane} />
      </div>

      {error && <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-xs text-accent-red">{error}</p>}
      {pane === 'spot' && <SpotPane data={spot} />}
      {pane === 'perp' && <PerpPane data={perp} />}
      {pane === 'global' && <GlobalPane data={global} status={status} />}
      {pane === 'setup' && (
        <SetupPane
          settings={settings}
          onSettings={setSettings}
          adminToken={adminToken}
          onAdminToken={setAdminToken}
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
    </div>
  );
};

export default AgentTab;
