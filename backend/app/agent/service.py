"""Autonomous agent orchestration for Step 6."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.brain import ClaudeMetaController, MetaControllerError
from backend.app.agent.heartbeat import heartbeat
from backend.app.agent.risk import KillSwitchState, RiskDecision, RiskManager, SignalIntent
from backend.app.agent.signals.common.indicators import ema
from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed, BinanceMarket, get_kline_cache_entry
from backend.app.agent.signals.perp.volume_profile import VolumeProfileSignal, _atr_range_leverage as _perp_atr_range_leverage
from backend.app.agent.signals.spot.momentum import MIN_SPOT_CANDLES, SpotMomentumSignal
from backend.app.agent.watchlist import selected_watchlist, selected_spot_watchlist, selected_perp_watchlist
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.data.market_data.cmc import CMCProvider
from backend.app.execution.models import ExecutionStatus
from backend.app.execution.perp_base import PerpOrder
from backend.app.execution.perp_registry import PerpExecutionRegistry, get_perp_execution_registry
from backend.app.execution.registry import ExecutionProviderRegistry, get_execution_provider_registry
from backend.app.notifications.agent_notifier import get_agent_notifier
from backend.app.persistence.database import get_session_factory
from backend.app.persistence.models.decisions import AgentDecision
from backend.app.persistence.models.pnl import PnlSnapshot
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.persistence.models.trades import PerpTrade, SpotTrade
from backend.app.persistence.repositories.api_usage import ApiUsageRepository
from backend.app.persistence.repositories.decisions import AgentDecisionRepository
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.positions import PerpPositionRepository, SpotPositionRepository
from backend.app.persistence.models.trade_charts import TradeChartSnapshot
from backend.app.persistence.repositories.trade_charts import TradeChartRepository
from backend.app.persistence.repositories.trades import PerpTradeRepository, SpotTradeRepository
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value
from backend.app.schemas.mobile_agent import AgentMobileSettings
from backend.app.execution.perp_fees import fetch_perp_fees, compute_opening_costs, accrue_funding
from backend.app.agent.signals.common.indicators import atr_series, ema
from backend.app.execution.spot_fees import compute_spot_costs

logger = get_logger("agent.service")

DAILY_TRADE_CHECK_TIME_UTC = time(20, 0, tzinfo=UTC)
DAILY_TRADE_RETRY_UNTIL_UTC = time(23, 30, tzinfo=UTC)
# Stablecoin: niente scansione spot (volatilita' ~0, nessun segnale sensato).
SPOT_EXCLUDED_STABLECOINS = frozenset(
    {"USDT", "USDC", "DAI", "USD1", "TUSD", "FDUSD", "BUSD", "USDP", "USDD", "GUSD", "PYUSD"}
)
HEARTBEAT_TRADE_ASSET = "ETH"
HEARTBEAT_TRADE_PRICE_USD_FALLBACK = Decimal("1")
# Distanza trailing-stop per il perp (coerente col livello generato dal segnale, 1%).
PERP_TRAILING_DISTANCE_PCT = Decimal("1.0")
# TTL cache del regime mercato (BTC 15m): evita un fetch BTC per ogni asset dello scan.
SPOT_REGIME_CACHE_TTL_SECONDS = 90
# Sentinel per la lazy-init del resolver token (distingue "non inizializzato" da "None").
_UNSET = object()


def _estimate_liquidation_price(entry: Decimal, leverage: int, side: str) -> Decimal | None:
    """Stima il prezzo di liquidazione (cross, senza maintenance margin).

    long: entry * (1 - 1/leva); short: entry * (1 + 1/leva).
    """
    if leverage <= 0 or entry <= 0:
        return None
    frac = Decimal(1) / Decimal(leverage)
    liq = entry * (Decimal(1) - frac) if side == "long" else entry * (Decimal(1) + frac)
    return liq.quantize(Decimal("0.00000001"))


def _auto_chart_interval(duration_min: int) -> tuple[str, int]:
    """Intervallo candele in base alla durata del trade -> (interval, minuti per candela)."""
    if duration_min <= 6 * 60:
        return "5m", 5
    if duration_min <= 2 * 24 * 60:
        return "1h", 60
    if duration_min <= 30 * 24 * 60:
        return "4h", 240
    return "1d", 1440


class AgentService:
    """Coordinates signals, risk, brain and execution providers."""

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        spot_signal: SpotMomentumSignal | None = None,
        perp_signal: VolumeProfileSignal | None = None,
        risk_manager: RiskManager | None = None,
        brain: ClaudeMetaController | None = None,
        spot_registry: ExecutionProviderRegistry | None = None,
        perp_registry: PerpExecutionRegistry | None = None,
        token_resolver: CMCProvider | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.spot_signal = spot_signal or SpotMomentumSignal(self.settings)
        self.perp_signal = perp_signal or VolumeProfileSignal(self.settings)
        self.risk = risk_manager or RiskManager(self.settings)
        self.brain = brain or ClaudeMetaController(self.settings)
        self.spot_registry = spot_registry or get_execution_provider_registry()
        self.perp_registry = perp_registry or get_perp_execution_registry()
        # Feed riusato per il refresh prezzi delle posizioni aperte (no nuova istanza a ogni tick).
        self.price_feed = BinanceKlineFeed(
            timeout_seconds=self.settings.market_data_request_timeout_seconds
        )
        # Resolver indirizzi token (CMC) per lo spot live; lazy, usato solo se serve.
        self._token_resolver_override = token_resolver
        self._token_resolver_cached: CMCProvider | None | object = _UNSET

    @property
    def _ms(self) -> AgentMobileSettings:
        """Mobile-overridable settings: reads from RuntimeState, falls back to config."""
        raw = get_runtime_value(str(self.settings.default_user_id), "mobile_agent_settings")
        if raw:
            try:
                return AgentMobileSettings.model_validate_json(raw)
            except ValueError:
                pass
        cap = self.settings.risk_capital_per_trade_pct
        slippage = self.settings.risk_max_slippage_pct
        cooldown = self.settings.risk_cooldown_minutes
        max_open = self.settings.risk_max_open_positions
        exposure = self.settings.risk_max_total_exposure_pct
        return AgentMobileSettings(
            mode=self.settings.agent_mode,
            markets_enabled=self.settings.markets_enabled,
            execution_mode=self.settings.execution_mode,
            network=self.settings.bsc_network,
            test_scaling_pct=self.settings.test_scaling_pct,
            operating_hours_utc=self.settings.operating_hours_utc,
            daily_loss_limit_pct=self.settings.risk_daily_loss_limit_pct,
            drawdown_cap_pct=self.settings.risk_max_drawdown_pct,
            min_pool_liquidity_usd=self.settings.risk_min_pool_liquidity_usd,
            # Parametri spot
            spot_capital_per_trade_pct=cap,
            spot_per_trade_pct=self.settings.risk_per_trade_pct,
            spot_max_open_positions=max_open,
            spot_max_exposure_pct=exposure,
            spot_cooldown_minutes=cooldown,
            spot_max_slippage_pct=slippage,
            # Parametri perp
            perp_capital_per_trade_pct=cap,
            perp_per_trade_pct=self.settings.risk_per_trade_pct,
            perp_max_open_positions=max_open,
            perp_max_exposure_pct=exposure,
            perp_cooldown_minutes=cooldown,
            perp_max_slippage_pct=slippage,
            perp_fixed_margin_enabled=False,
            perp_fixed_margin_usd=50.0,
            spot_time_stop_enabled=getattr(self.settings, "spot_time_stop_enabled", False),
            perp_time_stop_enabled=getattr(self.settings, "perp_time_stop_enabled", False),
            # Legacy (backward compat)
            capital_per_trade_pct=cap,
            per_trade_pct=self.settings.risk_per_trade_pct,
            max_open_positions=max_open,
            max_total_exposure_pct=exposure,
            max_slippage_pct=slippage,
            cooldown_minutes=cooldown,
            # Spot strategy
            spot_confidence_threshold=self.settings.spot_confidence_threshold,
            spot_volatility_trigger_pct=self.settings.spot_volatility_trigger_pct,
            spot_relative_volume_threshold=self.settings.spot_relative_volume_threshold,
            spot_sl_mode=getattr(self.settings, "spot_sl_mode", "atr"),
            spot_structural_stop_lookback_candles=getattr(self.settings, "spot_structural_stop_lookback_candles", 20),
            spot_structural_stop_buffer_pct=getattr(self.settings, "spot_structural_stop_buffer_pct", 1.10),
            spot_atr_stop_multiplier=self.settings.spot_atr_stop_multiplier,
            spot_trailing_distance_pct=self.settings.spot_trailing_distance_pct,
            spot_partial_take_profit_pct=self.settings.spot_partial_take_profit_pct,
            spot_tp1_close_pct=50.0,
            spot_time_stop_hours=self.settings.spot_time_stop_hours,
            spot_fee_mode="all",
            # Perp strategy
            perp_direction_mode=self.settings.perp_direction_mode,
            perp_min_leverage=self.settings.perp_min_leverage,
            perp_max_leverage=self.settings.perp_max_leverage,
            perp_value_area_pct=self.settings.perp_value_area_pct,
            perp_sl_mode=getattr(self.settings, "perp_sl_mode", "atr"),
            perp_structural_stop_lookback_candles=getattr(self.settings, "perp_structural_stop_lookback_candles", 20),
            perp_structural_stop_buffer_pct=getattr(self.settings, "perp_structural_stop_buffer_pct", 1.10),
            perp_atr_stop_multiplier=self.settings.perp_atr_stop_multiplier,
            perp_trailing_mode=self.settings.perp_trailing_mode,
            perp_trailing_pnl_pct=0.0,
            perp_tp1_close_pct=70.0,
            perp_time_stop_hours=self.settings.perp_time_stop_hours,
            post_close_candles=10,
        )

    def status(self) -> dict:
        return {
            "mode": self._ms.mode,
            "markets_enabled": self._ms.markets_enabled,
            "execution_mode": self._ms.execution_mode,
            "kill_switch": self.risk.kill_switch.value,
            "degraded_reasons": sorted(self.risk.degraded_reasons),
            "eligible_token_count": len(self.settings.eligible_tokens),
            "eligible_symbol_count": len(self.risk.eligible_symbols),
            "watchlist_count": len(selected_watchlist(self.settings)),
            "watchlist_spot_count": len(selected_spot_watchlist(self.settings)),
            "watchlist_perp_count": len(selected_perp_watchlist(self.settings)),
            "heartbeat": heartbeat.as_dict(),
        }

    def data_coverage(self) -> dict:
        """Return signal-engine OHLCV cache coverage for eligible active assets."""

        markets = _active_markets(self._ms.markets_enabled)
        items = []
        now = datetime.now(UTC)
        selected_assets = selected_watchlist(self.settings)
        for asset in selected_assets:
            if "spot" in markets:
                items.append(
                    _coverage_item(
                        asset=asset,
                        market="spot",
                        symbol=f"{asset.upper()}USDT",
                        required_candles=MIN_SPOT_CANDLES,
                        source="Binance klines 5m",
                        cache_market="spot",
                        now=now,
                    )
                )
            if "perp" in markets:
                interval = f"{self.settings.perp_volume_profile_candle_minutes}m"
                window = int(
                    self.settings.perp_volume_profile_window_hours
                    * 60
                    / self.settings.perp_volume_profile_candle_minutes
                )
                items.append(
                    _coverage_item(
                        asset=asset,
                        market="perp",
                        symbol=f"{asset.upper()}USDT",
                        required_candles=max(24, window // 4),
                        source="Binance klines 5m",
                        cache_market="futures",
                        now=now,
                        interval=interval,
                    )
                )
        return {
            "generated_at": now.isoformat(),
            "active_markets": sorted(markets),
            "selected_assets": selected_assets,
            "items": items,
        }

    def set_kill_switch(self, state: KillSwitchState) -> dict:
        self.risk.set_kill_switch(state)
        return self.status()

    async def close_all_and_pause(self, session: AsyncSession, *, reason: str = "manual_risk") -> dict:
        """Chiude TUTTE le posizioni aperte (spot + perp) al prezzo di mercato e
        mette l'agente in pausa (hard_stop). Usato dal pulsante Risk dell'app.

        La pausa blocca qualsiasi nuova entrata finche' non si riprende con
        ``set_kill_switch(RUNNING)``. Best-effort sul prezzo: se il feed non
        risponde si usa l'ultimo ``current_price`` memorizzato.
        """
        user_id = str(self.settings.default_user_id)
        spot_positions = await SpotPositionRepository(session).open_for_user(user_id)
        perp_positions = await PerpPositionRepository(session).open_for_user(user_id)
        now = datetime.now(UTC)

        if spot_positions or perp_positions:
            try:
                await self._refresh_position_prices(session, spot_positions, perp_positions)
            except Exception:
                pass

        closed_spot = 0
        for pos in spot_positions:
            if pos.status != "open":
                continue
            await self._close_spot_position(session, pos, pos.current_price, reason, now)
            closed_spot += 1

        closed_perp = 0
        for pos in perp_positions:
            if pos.status != "open":
                continue
            await self._close_perp_position(session, pos, pos.current_price, reason, now)
            closed_perp += 1

        # Pausa l'agente: nessuna nuova entrata fino al resume.
        self.risk.set_kill_switch(KillSwitchState.HARD_STOP)
        await self._update_portfolio_state(session, [], [], now)
        await session.commit()

        logger.info(
            "risk_close_all_and_pause",
            closed_spot=closed_spot, closed_perp=closed_perp, reason=reason,
        )
        return {
            "closed_spot": closed_spot,
            "closed_perp": closed_perp,
            **self.status(),
        }

    async def evaluate_spot(self, payload: dict, session: AsyncSession) -> dict:
        signal = await self.spot_signal.evaluate(payload)
        # Filtro regime mercato: blocca i nuovi ingressi spot in downtrend forte di BTC.
        if signal.get("action") == "enter_long":
            regime = await self._spot_market_regime()
            if regime.get("risk_off"):
                signal["action"] = "skip"
                signal["reason"] = "market_risk_off"
                signal.setdefault("components", {})["market_regime"] = regime
            elif self.settings.market_reversal_filter_enabled:
                reversal = await self._market_reversal_filter()
                signal.setdefault("components", {})["market_reversal"] = reversal
                if not reversal.get("risk_on"):
                    signal["action"] = "skip"
                    signal["reason"] = "market_reversal_waiting"
        return await self._handle_signal(signal, session)

    async def _spot_market_regime(self) -> dict:
        """Regime di mercato su BTC (15m), con isteresi e cache per ciclo.

        Blocca i nuovi buy spot quando BTC è sotto la EMA50 E sta facendo nuovi
        minimi (downtrend forte). Una volta in blocco ci resta finché BTC non
        richiude SOPRA la EMA50 (macchina a stati → niente flip-flop). In caso di
        dati insufficienti non blocca (fail-open).
        """
        if not self.settings.spot_market_regime_filter_enabled:
            return {"risk_off": False, "enabled": False}

        now = datetime.now(UTC)
        cached = getattr(self, "_regime_cache", None)
        if cached and (now - cached["at"]).total_seconds() < SPOT_REGIME_CACHE_TTL_SECONDS:
            return cached["value"]

        period = self.settings.spot_market_regime_ema_period
        lookback = self.settings.spot_market_regime_low_lookback
        try:
            candles = await self.price_feed.fetch(
                symbol=self.settings.spot_market_regime_symbol,
                interval=self.settings.spot_market_regime_interval,
                limit=max(period + 5, lookback + 5),
                market="spot",
            )
        except Exception:
            candles = []

        if len(candles) < max(period + 1, lookback):
            value = {"risk_off": False, "enabled": True, "reason": "insufficient_btc_klines"}
            self._regime_cache = {"at": now, "value": value}
            return value

        closes = [c.close for c in candles]
        ema_value = ema(closes, period)
        btc_close = closes[-1]
        above_ema = ema_value is not None and btc_close > ema_value
        new_low = candles[-1].low <= min(c.low for c in candles[-lookback:])

        prev_off = self._regime_risk_off_persisted()
        if prev_off:
            risk_off = not above_ema            # esce SOLO quando BTC torna sopra la EMA50
        else:
            risk_off = (not above_ema) and new_low  # entra: sotto media E nuovo minimo
        if risk_off != prev_off:
            self._set_regime_persisted(risk_off)

        value = {
            "risk_off": risk_off,
            "enabled": True,
            "btc_price": float(btc_close),
            "ema": float(ema_value) if ema_value is not None else None,
            "above_ema": above_ema,
            "new_low": new_low,
            "reason": "btc_downtrend_new_lows" if risk_off else "ok",
        }
        self._regime_cache = {"at": now, "value": value}
        return value

    def _regime_risk_off_persisted(self) -> bool:
        raw = get_runtime_value(str(self.settings.default_user_id), "spot_market_regime")
        if not raw:
            return False
        try:
            return bool(json.loads(raw).get("risk_off", False))
        except (ValueError, AttributeError):
            return False

    def _set_regime_persisted(self, risk_off: bool) -> None:
        set_runtime_value(
            str(self.settings.default_user_id),
            "spot_market_regime",
            json.dumps({"risk_off": risk_off, "updated_at": datetime.now(UTC).isoformat()}),
        )

    async def _market_reversal_filter(self) -> dict:
        """BTC 15m reversal confirmation used only as an entry filter.

        It never clears other blockers: Spot uses it only after a long signal is
        already present and market_risk_off is false; Perp uses it only to block
        shorts against confirmed BTC recovery.
        """
        if not self.settings.market_reversal_filter_enabled:
            return {"enabled": False, "risk_on": False}

        now = datetime.now(UTC)
        cached = getattr(self, "_market_reversal_cache", None)
        if cached and (now - cached["at"]).total_seconds() < SPOT_REGIME_CACHE_TTL_SECONDS:
            return cached["value"]

        period = max(1, int(self.settings.market_reversal_ema_period))
        confirmations = max(1, int(self.settings.market_reversal_confirmation_candles))
        limit = max(period + confirmations + 3, period + 5)
        try:
            candles = await self.price_feed.fetch(
                symbol=self.settings.market_reversal_symbol,
                interval=self.settings.market_reversal_interval,
                limit=limit,
                market="spot",
            )
        except Exception:
            candles = []

        if len(candles) < period + confirmations + 1:
            value = {"enabled": True, "risk_on": False, "reason": "insufficient_btc_reversal_klines"}
            self._market_reversal_cache = {"at": now, "value": value}
            return value

        closes = [c.close for c in candles]
        ema_now = ema(closes, period)
        ema_prev = ema(closes[:-1], period)
        latest_close = closes[-1]
        green_confirmed = all(c.close > c.open for c in candles[-confirmations:])
        red_confirmed = all(c.close < c.open for c in candles[-confirmations:])
        above_ema = ema_now is not None and latest_close > ema_now
        below_ema = ema_now is not None and latest_close < ema_now
        ema_rising = ema_now is not None and ema_prev is not None and ema_now > ema_prev
        bullish_entry = bool(green_confirmed and above_ema and ema_rising)
        bearish_entry = bool(red_confirmed and below_ema)
        previous_state = self._market_reversal_state_persisted()
        if previous_state == "bullish":
            state = "bearish" if bearish_entry else "bullish"
        elif previous_state == "bearish":
            state = "bullish" if bullish_entry else "bearish"
        elif bullish_entry:
            state = "bullish"
        elif bearish_entry:
            state = "bearish"
        else:
            state = "neutral"
        if state != previous_state:
            self._set_market_reversal_persisted(state)
        risk_on = state == "bullish"
        risk_off = state == "bearish"
        value = {
            "enabled": True,
            "risk_on": risk_on,
            "risk_off": risk_off,
            "state": state,
            "previous_state": previous_state,
            "symbol": self.settings.market_reversal_symbol,
            "interval": self.settings.market_reversal_interval,
            "confirmation_candles": confirmations,
            "btc_price": float(latest_close),
            "ema": float(ema_now) if ema_now is not None else None,
            "ema_rising": ema_rising,
            "green_confirmed": green_confirmed,
            "red_confirmed": red_confirmed,
            "above_ema": above_ema,
            "below_ema": below_ema,
            "bullish_entry": bullish_entry,
            "bearish_entry": bearish_entry,
            "reason": (
                "btc_reversal_confirmed"
                if state == "bullish" and previous_state != "bullish"
                else "btc_reversal_active"
                if state == "bullish"
                else "btc_reversal_bearish_confirmed"
                if state == "bearish" and previous_state != "bearish"
                else "btc_reversal_bearish_active"
                if state == "bearish"
                else "btc_reversal_waiting"
            ),
        }
        self._market_reversal_cache = {"at": now, "value": value}
        return value

    def _market_reversal_state_persisted(self) -> str:
        raw = get_runtime_value(str(self.settings.default_user_id), "market_reversal_filter")
        if not raw:
            return "neutral"
        try:
            payload = json.loads(raw)
            state = str(payload.get("state") or "").strip().lower()
            if state in {"bullish", "bearish", "neutral"}:
                return state
            if payload.get("risk_on") is True:
                return "bullish"
            if payload.get("risk_off") is True:
                return "bearish"
            return "neutral"
        except (ValueError, AttributeError):
            return "neutral"

    def _set_market_reversal_persisted(self, state: str) -> None:
        set_runtime_value(
            str(self.settings.default_user_id),
            "market_reversal_filter",
            json.dumps(
                {
                    "state": state,
                    "risk_on": state == "bullish",
                    "risk_off": state == "bearish",
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
        )

    async def evaluate_perp(self, payload: dict, session: AsyncSession) -> dict:
        signal = await self.perp_signal.evaluate(payload)
        if (
            signal.get("action") != "skip"
            and signal.get("side") == "short"
            and self.settings.market_reversal_filter_enabled
        ):
            reversal = await self._market_reversal_filter()
            signal.setdefault("components", {})["market_reversal"] = reversal
            if reversal.get("risk_on"):
                signal["action"] = "skip"
                signal["reason"] = "market_reversal_short_blocked"
        if (
            signal.get("action") != "skip"
            and signal.get("side") == "long"
            and self.settings.market_reversal_filter_enabled
        ):
            reversal = await self._market_reversal_filter()
            signal.setdefault("components", {})["market_reversal"] = reversal
            if reversal.get("risk_off"):
                signal["action"] = "skip"
                signal["reason"] = "market_reversal_long_blocked"
        # Il segnale embeds la leva calcolata con il config YAML statico.
        # La sovrascriviamo con i mobile settings (RuntimeState) per rispettare
        # la leva impostata dall'utente nell'app.
        if signal.get("action") != "skip":
            ms = self._ms
            components = signal.get("components") or {}
            atr_now = components.get("atr_lev")
            # Baseline storica più lunga per atr_min/atr_max (vol corrente vs storico ampio):
            # così la leva è graduata e il minimo è riservato alle vere anomalie.
            atr_min, atr_max = await self._perp_leverage_atr_baseline(
                signal.get("asset"), payload, atr_now
            )
            signal["leverage"] = _perp_atr_range_leverage(
                min_lev=ms.perp_min_leverage,
                max_lev=ms.perp_max_leverage,
                atr_value=atr_now,
                atr_min=atr_min,
                atr_max=atr_max,
            )
        return await self._handle_signal(signal, session)

    async def _perp_leverage_atr_baseline(
        self, asset: str | None, payload: dict, atr_now: float | None
    ) -> tuple[float | None, float | None]:
        """Ricava (atr_min, atr_max) della serie ATR su un lookback lungo (giorni), per
        modulare la leva confrontando la vol corrente con uno storico ampio.

        Best-effort: senza ATR corrente o senza dati ritorna (None, None) → leva minima.
        Eseguito solo all'apertura reale (action != skip), una fetch klines per trade.
        """
        if atr_now is None:
            return None, None
        symbol = payload.get("symbol") or (f"{asset}USDT" if asset else None)
        if not symbol:
            return None, None
        minutes = self.settings.perp_volume_profile_candle_minutes
        hours = self.settings.perp_leverage_atr_baseline_hours
        period = self.settings.perp_leverage_atr_period
        limit = min(int(hours * 60 / minutes), 1500)
        try:
            candles = await self.price_feed.fetch(
                symbol=str(symbol), interval=f"{minutes}m", limit=limit, market="futures"
            )
        except Exception:
            return None, None
        series = atr_series(candles, period=period)
        if not series:
            return None, None
        return min(series), max(series)

    async def fast_tick(self, session: AsyncSession) -> dict:
        """Manage open positions; refresh live prices and check SL/TP."""

        heartbeat.beat("agent_fast_tick")
        user_id = str(self.settings.default_user_id)
        spot_positions = await SpotPositionRepository(session).open_for_user(user_id)
        perp_positions = await PerpPositionRepository(session).open_for_user(user_id)
        now = datetime.now(UTC)
        if spot_positions or perp_positions:
            await self._refresh_position_prices(session, spot_positions, perp_positions)
            await self._check_sl_tp(session, spot_positions, perp_positions, now)
        open_spot = [p for p in spot_positions if p.status == "open"]
        open_perp = [p for p in perp_positions if p.status == "open"]
        await self._update_portfolio_state(session, open_spot, open_perp, now)
        await self._check_risk_notifications(session, open_spot, open_perp)
        return {
            "status": "ok",
            "open_spot_positions": len(spot_positions),
            "open_perp_positions": len(perp_positions),
            "kill_switch": self.risk.kill_switch.value,
        }

    async def _refresh_position_prices(
        self,
        session: AsyncSession,
        spot_positions: list,
        perp_positions: list,
    ) -> None:
        """Fetch live Binance prices and update current_price + pnl_unrealized for open positions."""
        now = datetime.now(UTC)

        perp_assets: list[str] = sorted({p.asset for p in perp_positions})
        spot_assets: list[str] = sorted({p.asset for p in spot_positions})

        # Una sola chiamata batch per mercato invece di N richieste seriali.
        perp_prices: dict[str, Decimal] = {}
        if perp_assets:
            try:
                ticker = await self.price_feed.fetch_prices(
                    symbols=[f"{a}USDT" for a in perp_assets], market="futures"
                )
                perp_prices = {a: ticker[f"{a}USDT"] for a in perp_assets if f"{a}USDT" in ticker}
            except Exception:
                pass

        spot_prices: dict[str, Decimal] = {}
        if spot_assets:
            try:
                ticker = await self.price_feed.fetch_prices(
                    symbols=[f"{a}USDT" for a in spot_assets], market="spot"
                )
                spot_prices = {a: ticker[f"{a}USDT"] for a in spot_assets if f"{a}USDT" in ticker}
            except Exception:
                pass

        # Funding rate live (best-effort) per le posizioni perp aperte.
        funding_rates: dict[str, Decimal] = {}
        if perp_assets:
            try:
                funding_rates = await self.price_feed.fetch_funding_rates(assets=perp_assets)
            except Exception:
                pass

        updated = False
        for pos in perp_positions:
            funding = funding_rates.get(pos.asset)
            if funding is not None:
                pos.funding_rate = funding
                pos.updated_at = now
                session.add(pos)
                updated = True
            price = perp_prices.get(pos.asset)
            if price is None:
                continue
            raw_pnl = (price - pos.entry_price) * pos.size if pos.side == "long" else (pos.entry_price - price) * pos.size
            pos.current_price = price
            # Aggiorna funding accrued se la posizione ha fee_mode != "none"
            if pos.funding_rate is not None and pos.fee_mode and pos.fee_mode != "none":
                hours = (now - pos.opened_at.replace(tzinfo=pos.opened_at.tzinfo or UTC)).total_seconds() / 3600
                notional = pos.entry_price * pos.size
                pos.funding_accrued_usd = accrue_funding(pos.funding_rate, notional, hours, pos.side)
            # Detrae la fee di apertura (taker o maker) dal P&L netto.
            # Lo slippage è già nell'entry_price, quindi si sottrae solo la parte
            # "pura" della fee: opening_fee_usd − slippage_usd già incluso nel prezzo.
            fee_deduction = (pos.opening_fee_usd or Decimal("0")) - (pos.slippage_usd or Decimal("0"))
            pos.pnl_unrealized = raw_pnl - fee_deduction + pos.funding_accrued_usd
            # Aggiorna anche il liq price se mancante (posizioni aperte prima del fix).
            if pos.liquidation_price is None:
                pos.liquidation_price = _estimate_liquidation_price(pos.entry_price, pos.leverage, pos.side)
            pos.updated_at = now
            session.add(pos)
            updated = True

        for pos in spot_positions:
            price = spot_prices.get(pos.asset)
            if price is None:
                continue
            pos.current_price = price
            raw_pnl = (price - pos.entry_price) * pos.size
            # Detrae la swap fee dal P&L netto (lo slippage è già nell'entry_price).
            pos.pnl_unrealized = raw_pnl - (pos.swap_fee_usd or Decimal("0"))
            pos.updated_at = now
            session.add(pos)
            updated = True

        if updated:
            await session.commit()

    async def _snapshot_closed_trade(
        self,
        session: AsyncSession,
        pos,
        *,
        market: str,
        exit_price: Decimal,
        close_trade_id: str,
        now: datetime,
    ) -> None:
        """Congela candele + livelli alla chiusura per ridisegnare il grafico nel dettaglio.

        Best-effort: un errore (es. feed irraggiungibile) non blocca la chiusura del trade.
        """
        try:
            opened_at = pos.opened_at
            if opened_at.tzinfo is None:
                opened_at = opened_at.replace(tzinfo=UTC)
            duration_min = max(1, int((now - opened_at).total_seconds() / 60))
            interval, per_min = _auto_chart_interval(duration_min)
            stop_reference_time = getattr(pos, "stop_reference_time", None)
            if stop_reference_time and stop_reference_time.tzinfo is None:
                stop_reference_time = stop_reference_time.replace(tzinfo=UTC)
            lookback_attr = "perp_structural_stop_lookback_candles" if market == "perp" else "spot_structural_stop_lookback_candles"
            try:
                lookback = max(1, int(getattr(self.settings, lookback_attr, 20)))
            except Exception:
                lookback = 20
            chart_start = (
                min(opened_at - timedelta(minutes=per_min * lookback), stop_reference_time)
                if stop_reference_time is not None
                else None
            )
            chart_span_min = (
                max(1, int((now - chart_start).total_seconds() / 60))
                if chart_start is not None
                else duration_min
            )
            limit = int(min(260, max(20, (chart_span_min / per_min) * 1.6)))
            feed_market = "futures" if market == "perp" else "spot"
            try:
                fetch_kwargs = {
                    "symbol": f"{pos.asset}USDT",
                    "interval": interval,
                    "limit": limit,
                    "market": feed_market,
                }
                if chart_start is not None:
                    fetch_kwargs["start_time"] = chart_start
                candles = await self.price_feed.fetch(
                    **fetch_kwargs,
                )
            except Exception:
                candles = await self.price_feed.fetch(
                    symbol=f"{pos.asset}USDT", interval=interval, limit=limit, market=feed_market
                )
            tp2 = getattr(pos, "take_profit_2", None)
            stop_reference_price = getattr(pos, "stop_reference_price", None)
            stop_reference_field = getattr(pos, "stop_reference_field", None)
            display_stop_loss = getattr(pos, "initial_stop_loss", None) or pos.stop_loss
            payload = {
                "interval": interval,
                "market": market,
                "side": pos.side if market == "perp" else "long",
                "entry_price": str(pos.entry_price),
                "exit_price": str(exit_price),
                "stop_loss": str(display_stop_loss) if display_stop_loss else None,
                "take_profit_1": str(pos.take_profit_1) if pos.take_profit_1 else None,
                "take_profit_2": str(tp2) if tp2 else None,
                "liquidation_price": (
                    str(pos.liquidation_price)
                    if market == "perp" and getattr(pos, "liquidation_price", None)
                    else None
                ),
                "opened_at": opened_at.isoformat(),
                "closed_at": now.isoformat(),
                "stop_reference": (
                    {
                        "t": stop_reference_time.isoformat(),
                        "price": str(stop_reference_price) if stop_reference_price else None,
                        "field": stop_reference_field,
                        "pre_candles": lookback,
                    }
                    if stop_reference_time is not None
                    else None
                ),
                "candles": [
                    {"t": c.timestamp.isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close}
                    for c in candles
                ],
            }
            await TradeChartRepository(session).save(
                TradeChartSnapshot(
                    user_id=pos.user_id,
                    position_id=pos.position_id,
                    close_trade_id=close_trade_id,
                    market=market,
                    payload=json.dumps(payload),
                    created_at=now,
                )
            )
        except Exception:
            logger.warning("trade_chart_snapshot_failed", asset=pos.asset, position_id=pos.position_id)

    async def _close_spot_position(
        self,
        session: AsyncSession,
        pos: SpotPosition,
        exit_price: Decimal,
        reason: str,
        now: datetime,
        *,
        partial: bool = False,
    ) -> Decimal:
        """Chiude (totalmente o per la quota TP1) una posizione spot; crea trade di chiusura con pnl_usd."""
        swap_fee = pos.swap_fee_usd or Decimal("0")
        if partial:
            fraction = Decimal(str(self._ms.spot_tp1_close_pct)) / Decimal("100")
            close_size = (pos.size * fraction).quantize(Decimal("0.000001"))
            raw_pnl = (exit_price - pos.entry_price) * close_size
            pnl = raw_pnl - swap_fee * fraction
            pos.size = pos.size - close_size
            pos.tp1_reached = True
            remaining = Decimal("1") - fraction
            pos.pnl_unrealized = (exit_price - pos.entry_price) * pos.size - swap_fee * remaining
            # Scala la fee residua: il close finale userà solo la quota rimasta
            pos.swap_fee_usd = swap_fee * remaining
        else:
            close_size = pos.size
            raw_pnl = (exit_price - pos.entry_price) * close_size
            pnl = raw_pnl - swap_fee
            pos.status = "closed"
            pos.pnl_unrealized = pnl
        pos.current_price = exit_price
        pos.updated_at = now
        session.add(pos)
        close_trade = SpotTrade(
            trade_id=f"cls_{pos.position_id}_{uuid4().hex[:8]}",
            user_id=pos.user_id,
            asset=pos.asset,
            side="sell",
            amount=close_size,
            price=exit_price,
            amount_quote=exit_price * close_size,
            status="confirmed",
            provider="agent",
            timestamp_utc=now,
            notes=f"auto_close:{reason}{'_partial' if partial else ''}",
            pnl_usd=pnl,
        )
        await SpotTradeRepository(session).save(close_trade)
        await self._snapshot_closed_trade(
            session, pos, market="spot", exit_price=exit_price,
            close_trade_id=close_trade.trade_id, now=now,
        )
        logger.info("spot_position_closed", asset=pos.asset, reason=reason, partial=partial, pnl_usd=float(pnl))
        return pnl

    async def _maybe_scale_in_spot(
        self,
        session: AsyncSession,
        pos: SpotPosition,
        price: Decimal,
        prev_max: Decimal | None,
        now: datetime,
    ) -> None:
        """E (v3): aggiunge a favore (piramidazione) su una posizione spot vincente.

        Vincoli assoluti: MAI media al ribasso. Aggiunge solo se la posizione è in
        profitto, lo stop è già a breakeven e c'è un nuovo higher-high confermato.
        La size totale resta entro il tetto nominale per trade (risk_capital_per_trade_pct).
        """
        s = self.settings
        if not s.spot_scale_in_enabled:
            return
        if (pos.scale_in_count or 0) >= s.spot_scale_in_max_adds:
            return
        # Mai aggiungere in perdita / non a favore.
        if price <= pos.entry_price:
            return
        # Stop già a breakeven (>= entry).
        if s.spot_scale_in_require_be_stop:
            be_moved = pos.stop_loss is not None and pos.stop_loss >= pos.entry_price
            if not be_moved:
                return
        # Nuovo higher-high confermato rispetto al massimo precedente.
        if s.spot_scale_in_require_new_hh and not (prev_max is not None and price > prev_max):
            return

        current_notional = pos.size * pos.entry_price
        add_notional = current_notional * Decimal(str(s.spot_scale_in_size_fraction))
        # Tetto: il notional totale resta entro il cap nominale per trade.
        portfolio = await PnlRepository(session).get_portfolio(str(self.settings.default_user_id))
        if portfolio is not None and Decimal(portfolio.total_equity_usd) > 0:
            cap = Decimal(portfolio.total_equity_usd) * Decimal(str(s.risk_capital_per_trade_pct)) / Decimal("100")
            room = cap - current_notional
            if room <= 0:
                return
            add_notional = min(add_notional, room)
        if add_notional <= 0:
            return

        # Costi dell'add coerenti con l'ingresso (slippage nel prezzo, swap fee accumulata).
        costs = compute_spot_costs(add_notional, pos.fee_mode or "all")
        add_price = price * (Decimal("1") + costs["slippage_rate"]) if costs["slippage_rate"] > 0 else price
        add_amount = add_notional / add_price

        # Media a favore: nuova entry = media ponderata; stop NON viene mai abbassato.
        new_size = pos.size + add_amount
        pos.entry_price = (pos.size * pos.entry_price + add_amount * add_price) / new_size
        pos.size = new_size
        pos.scale_in_count = (pos.scale_in_count or 0) + 1
        pos.swap_fee_usd = (pos.swap_fee_usd or Decimal("0")) + costs["swap_fee_usd"]
        pos.slippage_usd = (pos.slippage_usd or Decimal("0")) + costs["slippage_usd"]
        pos.updated_at = now
        session.add(pos)

        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id=f"add_{pos.position_id}_{uuid4().hex[:8]}",
                user_id=pos.user_id,
                asset=pos.asset,
                side="buy",
                amount=add_amount,
                price=add_price,
                amount_quote=add_notional,
                status="confirmed",
                provider="agent",
                timestamp_utc=now,
                notes="scale_in",
                fee_mode=pos.fee_mode,
                swap_fee_usd=costs["swap_fee_usd"],
                slippage_usd=costs["slippage_usd"],
                fees_quote=costs["applied_fee_usd"],
            )
        )
        logger.info("spot_scale_in", asset=pos.asset, add_quote=float(add_notional), adds=pos.scale_in_count)

    async def _spot_time_stop_reason(
        self,
        pos: SpotPosition,
        price: Decimal,
        atr_v: Decimal | None,
        now: datetime,
    ) -> str | None:
        """G (v3): stop temporale. In modalità ATR chiude solo se il prezzo si è mosso
        meno di ``min_move_atr * ATR`` nelle ultime N candele (trade fermo). Fallback orario
        solo se mode='hours'. Best-effort: senza dati candele non chiude."""
        s = self.settings
        opened = pos.opened_at.replace(tzinfo=pos.opened_at.tzinfo or UTC)
        if s.spot_time_stop_mode == "atr":
            if not atr_v or atr_v <= 0:
                return None
            lookback = s.spot_time_stop_lookback_candles
            age_min = (now - opened).total_seconds() / 60
            # Giudica solo dopo che è trascorsa l'intera finestra (candele 5m).
            if age_min < lookback * 5:
                return None
            past_close = self._spot_close_n_candles_ago(pos.asset, lookback)
            if past_close is None:
                return None
            move = abs(price - past_close)
            if move < atr_v * Decimal(str(s.spot_time_stop_min_move_atr)):
                return "time_stop_atr"
            return None
        # Fallback orario (mode='hours').
        if s.spot_time_stop_hours_fallback > 0:
            age_hours = (now - opened).total_seconds() / 3600
            if age_hours >= s.spot_time_stop_hours_fallback:
                return "time_stop"
        return None

    def _spot_close_n_candles_ago(self, asset: str, lookback: int) -> Decimal | None:
        """Prezzo di chiusura ~N candele 5m fa dalla cache klines (best-effort, no HTTP)."""
        try:
            entry = get_kline_cache_entry(market="spot", symbol=f"{asset}USDT", interval="5m")
            if entry is None or len(entry.candles) <= lookback:
                return None
            return Decimal(str(entry.candles[-(lookback + 1)].close))
        except Exception:
            return None

    async def _close_perp_position(
        self,
        session: AsyncSession,
        pos: PerpPosition,
        exit_price: Decimal,
        reason: str,
        now: datetime,
        *,
        partial: bool = False,
    ) -> Decimal:
        """Chiude (totalmente o al 50% per TP1) una posizione perp; crea trade di chiusura con pnl_usd."""
        is_long = pos.side == "long"
        pnl_per_unit = (exit_price - pos.entry_price) if is_long else (pos.entry_price - exit_price)
        # Fee pura = opening_fee_usd escludendo lo slippage già incluso nell'entry_price.
        fee_only = (pos.opening_fee_usd or Decimal("0")) - (pos.slippage_usd or Decimal("0"))

        if partial:
            f = Decimal(str(self._ms.perp_tp1_close_pct)) / Decimal("100")
            close_size = (pos.size * f).quantize(Decimal("0.000001"))
            funding_share = pos.funding_accrued_usd * f
            raw_pnl = pnl_per_unit * close_size
            pnl = raw_pnl - fee_only * f + funding_share
            pos.size = pos.size - close_size
            pos.tp1_reached = True
            remaining = Decimal("1") - f
            pos.pnl_unrealized = pnl_per_unit * pos.size - fee_only * remaining + pos.funding_accrued_usd * remaining
            # Scala la fee residua sulla posizione: il close finale userà solo la quota rimasta
            pos.opening_fee_usd = (pos.opening_fee_usd or Decimal("0")) * remaining
            pos.slippage_usd = (pos.slippage_usd or Decimal("0")) * remaining
            pos.funding_accrued_usd = pos.funding_accrued_usd * remaining
        else:
            close_size = pos.size
            raw_pnl = pnl_per_unit * close_size
            pnl = raw_pnl - fee_only + pos.funding_accrued_usd
            pos.status = "closed"
            pos.pnl_unrealized = pnl

        pos.current_price = exit_price
        pos.updated_at = now
        session.add(pos)
        close_trade = PerpTrade(
            trade_id=f"cls_{pos.position_id}_{uuid4().hex[:8]}",
            user_id=pos.user_id,
            asset=pos.asset,
            side=pos.side,
            direction="close",
            size=close_size,
            price=exit_price,
            leverage=pos.leverage,
            status="confirmed",
            venue=pos.venue or "agent",
            timestamp_utc=now,
            notes=f"auto_close:{reason}{'_partial' if partial else ''}",
            pnl_usd=pnl,
        )
        await PerpTradeRepository(session).save(close_trade)
        await self._snapshot_closed_trade(
            session, pos, market="perp", exit_price=exit_price,
            close_trade_id=close_trade.trade_id, now=now,
        )
        logger.info("perp_position_closed", asset=pos.asset, reason=reason, partial=partial, pnl_usd=float(pnl))
        return pnl

    async def _check_sl_tp(
        self,
        session: AsyncSession,
        spot_positions: list,
        perp_positions: list,
        now: datetime,
    ) -> None:
        """Controlla SL/TP per ogni posizione aperta e chiude quelle che le hanno raggiunte."""
        user_id = str(self.settings.default_user_id)
        notifier = get_agent_notifier()

        for pos in spot_positions:
            if pos.status != "open":
                continue
            price = pos.current_price
            reason: str | None = None
            partial = False
            atr_v = pos.entry_atr
            prev_max = pos.max_price  # E (v3): riferimento higher-high PRIMA dell'update

            # C (v3): aggiorna il massimo dall'ingresso (per il trailing ATR).
            if pos.max_price is None or price > pos.max_price:
                pos.max_price = price
                pos.updated_at = now
                session.add(pos)

            # C (v3): breakeven a +1*ATR — alza lo stop a entry (+costi), non torna più sotto.
            if atr_v and atr_v > 0:
                be_trigger = pos.entry_price + atr_v * Decimal(str(self.settings.spot_breakeven_trigger_atr))
                be_tp1_ok = self._ms.spot_breakeven_mode != "tp1" or pos.tp1_reached
                if self.settings.spot_breakeven_enabled and price >= be_trigger and be_tp1_ok:
                    be_stop = pos.entry_price
                    if self.settings.spot_breakeven_offset_costs and pos.size > 0:
                        # Costi andata+ritorno (×2): coprono anche la fee di chiusura,
                        # così chiudere a breakeven non lascia una mini-perdita.
                        costs = ((pos.swap_fee_usd or Decimal("0")) + (pos.slippage_usd or Decimal("0"))) * 2
                        be_stop = pos.entry_price + costs / pos.size
                    # Cuscinetto extra: alza lo stop a entry+X% MA solo se il prezzo
                    # l'ha già superato (altrimenti lo stop starebbe sopra il prezzo →
                    # chiusura immediata). Copre le fee con un margine confortevole.
                    buf_pct = Decimal(str(self.settings.spot_breakeven_buffer_pct))
                    if buf_pct > 0:
                        buffer_be = pos.entry_price * (Decimal("1") + buf_pct / Decimal("100"))
                        if price > buffer_be and buffer_be > be_stop:
                            be_stop = buffer_be
                    if pos.stop_loss is None or be_stop > pos.stop_loss:
                        pos.stop_loss = be_stop
                        pos.updated_at = now
                        session.add(pos)
                # C (v3): trailing ATR attivo DA SUBITO (max_price - ATR*mult), solo verso l'alto.
                # Il moltiplicatore è cappato al TP1: così l'attivazione del trailing
                # (≈ entry + mult*ATR) non supera mai il TP1, altrimenti il trailing si
                # accenderebbe oltre il primo take-profit (inutile).
                if self._ms.spot_trailing_enabled and self.settings.spot_trailing_active_from_start:
                    trail_mult = min(
                        Decimal(str(self.settings.spot_trailing_atr_multiplier)),
                        Decimal(str(self.settings.spot_tp1_atr_multiplier)),
                    )
                    trail = (pos.max_price or price) - atr_v * trail_mult
                    # Guard: il trailing spot si attiva solo quando supera l'entry
                    # (non deve sostituire lo stop con uno più stretto ma in perdita).
                    if trail >= pos.entry_price and (pos.trailing_stop is None or trail > pos.trailing_stop):
                        pos.trailing_stop = trail
                        pos.updated_at = now
                        session.add(pos)

            # E (v3): scaling-in a favore (solo HH + stop a breakeven; mai in perdita).
            await self._maybe_scale_in_spot(session, pos, price, prev_max, now)

            # Uscite — priorità massima: SL / trailing (il maggiore dei due).
            if self._ms.spot_trailing_enabled and pos.trailing_stop is not None and (pos.stop_loss is None or pos.trailing_stop > pos.stop_loss):
                if price <= pos.trailing_stop:
                    reason = "trailing_stop"
            if reason is None and pos.stop_loss is not None and price <= pos.stop_loss:
                # Se lo stop è già a breakeven (>= entry) la chiusura non è una perdita:
                # etichettala "breakeven" invece di "stop_loss".
                reason = "breakeven" if pos.stop_loss >= pos.entry_price else "stop_loss"
            # TP2 (uscita finale) solo dopo che TP1 e' stato preso.
            if reason is None and pos.tp1_reached and pos.take_profit_2 and price >= pos.take_profit_2:
                reason = "take_profit_2"
            # TP1: chiusura parziale la prima volta che viene raggiunto.
            if reason is None and not pos.tp1_reached and pos.take_profit_1 and price >= pos.take_profit_1:
                reason = "take_profit_1"
                partial = True
            # G (v3): stop temporale ATR-aware — chiude solo i trade davvero fermi.
            if reason is None and self._ms.spot_time_stop_enabled:
                reason = await self._spot_time_stop_reason(pos, price, atr_v, now)
            if reason:
                exit_price = _level_fill_price(pos, reason, price)
                pnl = await self._close_spot_position(session, pos, exit_price, reason, now, partial=partial)
                exposure = pos.entry_price * pos.size
                pnl_pct = pnl / exposure * 100 if exposure > 0 else Decimal("0")
                asyncio.create_task(
                    notifier.notify_trade_closed(
                        user_id=user_id,
                        trade_id=f"cls_{pos.position_id}",
                        asset=pos.asset,
                        market="spot",
                        pnl_usd=pnl,
                        pnl_pct=pnl_pct,
                        close_reason=reason,
                        is_dry_run=self._ms.execution_mode == "dry_run",
                    )
                )

        ms = self._ms
        if (ms.perp_trailing_mode or "largo").lower() == "stretto":
            trail_base = self.settings.perp_trailing_base_atr_stretto
            trail_floor = self.settings.perp_trailing_floor_atr_stretto
        else:
            trail_base = self.settings.perp_trailing_base_atr_largo
            trail_floor = self.settings.perp_trailing_floor_atr_largo
        be_mult = Decimal(str(self.settings.perp_breakeven_trigger_atr))

        for pos in perp_positions:
            if pos.status != "open":
                continue
            price = pos.current_price
            is_long = pos.side == "long"
            reason = None
            partial = False
            atr_v = pos.entry_atr

            # Estremo favorevole dall'ingresso (per il trailing): max per i long, min per gli short.
            if is_long:
                if pos.max_price is None or price > pos.max_price:
                    pos.max_price = price; pos.updated_at = now; session.add(pos)
            else:
                if pos.max_price is None or price < pos.max_price:
                    pos.max_price = price; pos.updated_at = now; session.add(pos)
            extreme = pos.max_price if pos.max_price is not None else price

            # Protezione ATR — solo se l'ATR è stato congelato all'ingresso (trade nuovi).
            if atr_v and atr_v > 0:
                # Breakeven: a +N×ATR lo SL si sposta a entry (+costi), solo verso il sicuro.
                be_trigger = (pos.entry_price + atr_v * be_mult) if is_long else (pos.entry_price - atr_v * be_mult)
                be_tp1_ok = ms.perp_breakeven_mode != "tp1" or pos.tp1_reached
                if self.settings.perp_breakeven_enabled and ((is_long and price >= be_trigger) or (not is_long and price <= be_trigger)) and be_tp1_ok:
                    be_stop = pos.entry_price
                    if self.settings.perp_breakeven_offset_costs and pos.size > 0:
                        # Fee andata+ritorno (×2): copre anche la chiusura.
                        fee_only = ((pos.opening_fee_usd or Decimal("0")) - (pos.slippage_usd or Decimal("0"))) * 2
                        offset = fee_only / pos.size
                        be_stop = pos.entry_price + offset if is_long else pos.entry_price - offset
                    # Cuscinetto extra entry±X%, applicato solo se il prezzo l'ha superato
                    # (mai oltre il prezzo corrente → niente chiusura immediata).
                    buf_pct = Decimal(str(self.settings.perp_breakeven_buffer_pct))
                    if buf_pct > 0:
                        if is_long:
                            buffer_be = pos.entry_price * (Decimal("1") + buf_pct / Decimal("100"))
                            if price > buffer_be and buffer_be > be_stop:
                                be_stop = buffer_be
                        else:
                            buffer_be = pos.entry_price * (Decimal("1") - buf_pct / Decimal("100"))
                            if price < buffer_be and buffer_be < be_stop:
                                be_stop = buffer_be
                    if is_long and (pos.stop_loss is None or be_stop > pos.stop_loss):
                        pos.stop_loss = be_stop; pos.updated_at = now; session.add(pos)
                    elif not is_long and (pos.stop_loss is None or be_stop < pos.stop_loss):
                        pos.stop_loss = be_stop; pos.updated_at = now; session.add(pos)

                # Trailing da subito, moltiplicatore ATR dinamico sulla leva del trade.
                mult = _perp_trailing_mult(
                    leverage=pos.leverage, min_lev=ms.perp_min_leverage, max_lev=ms.perp_max_leverage,
                    base=trail_base, floor=trail_floor,
                )
                # Cappa il moltiplicatore al TP1: l'attivazione del trailing
                # (≈ entry + mult*ATR) non deve mai superare il primo take-profit,
                # altrimenti il trailing si accende oltre TP1 (quasi a TP2) ed è inutile.
                tp1_cap = Decimal(str(self.settings.perp_tp1_atr_multiplier))
                if mult > tp1_cap:
                    mult = tp1_cap
                pnl_pct = Decimal(str(ms.perp_trailing_pnl_pct))
                if is_long:
                    trail_atr = extreme - atr_v * mult
                    # Se perp_trailing_pnl_pct > 0, calcola anche il trailing a distanza
                    # fissa (% del prezzo dal massimo). Vince il più alto tra i due.
                    if pnl_pct > 0:
                        trail_pnl = extreme * (1 - pnl_pct / Decimal("100"))
                        trail = max(trail_atr, trail_pnl)
                    else:
                        trail = trail_atr
                    # Il trailing si attiva SOLO quando supera l'entry: non deve mai
                    # sostituire lo stop originale con uno stop più stretto ma ancora
                    # in perdita (causa chiusure precoci senza dare spazio alla posizione).
                    if ms.perp_trailing_enabled and trail >= pos.entry_price and (pos.stop_loss is None or trail > pos.stop_loss) and (pos.trailing_stop is None or trail > pos.trailing_stop):
                        pos.trailing_stop = trail; pos.updated_at = now; session.add(pos)
                else:
                    trail_atr = extreme + atr_v * mult
                    if pnl_pct > 0:
                        trail_pnl = extreme * (1 + pnl_pct / Decimal("100"))
                        trail = min(trail_atr, trail_pnl)
                    else:
                        trail = trail_atr
                    # Stesso guard per gli short: trail deve essere <= entry (in profitto).
                    if ms.perp_trailing_enabled and trail <= pos.entry_price and (pos.stop_loss is None or trail < pos.stop_loss) and (pos.trailing_stop is None or trail < pos.trailing_stop):
                        pos.trailing_stop = trail; pos.updated_at = now; session.add(pos)

            # ── Uscite — trailing (se più protettivo) → stop → TP2 → TP1 → time ──
            if ms.perp_trailing_enabled and pos.trailing_stop is not None and (
                pos.stop_loss is None
                or (is_long and pos.trailing_stop > pos.stop_loss)
                or (not is_long and pos.trailing_stop < pos.stop_loss)
            ):
                if (is_long and price <= pos.trailing_stop) or (not is_long and price >= pos.trailing_stop):
                    reason = "trailing_stop"

            if reason is None and pos.stop_loss is not None:
                if (is_long and price <= pos.stop_loss) or (not is_long and price >= pos.stop_loss):
                    # Stop già a breakeven (>= entry long / <= entry short) → non è perdita.
                    at_be = pos.stop_loss >= pos.entry_price if is_long else pos.stop_loss <= pos.entry_price
                    reason = "breakeven" if at_be else "stop_loss"

            if reason is None and pos.tp1_reached and pos.take_profit_2:
                if (is_long and price >= pos.take_profit_2) or (not is_long and price <= pos.take_profit_2):
                    reason = "take_profit_2"

            if reason is None and not pos.tp1_reached and pos.take_profit_1:
                if (is_long and price >= pos.take_profit_1) or (not is_long and price <= pos.take_profit_1):
                    reason = "take_profit_1"
                    partial = True

            if reason is None and ms.perp_time_stop_enabled and ms.perp_time_stop_hours > 0:
                age_hours = (now - pos.opened_at.replace(tzinfo=pos.opened_at.tzinfo or UTC)).total_seconds() / 3600
                if age_hours >= ms.perp_time_stop_hours:
                    reason = "time_stop"

            if reason:
                exit_price = _level_fill_price(pos, reason, price)
                pnl = await self._close_perp_position(session, pos, exit_price, reason, now, partial=partial)
                margin = pos.entry_price * pos.size / Decimal(max(int(pos.leverage or 1), 1))
                pnl_pct = pnl / margin * 100 if margin > 0 else Decimal("0")
                asyncio.create_task(
                    notifier.notify_trade_closed(
                        user_id=user_id,
                        trade_id=f"cls_{pos.position_id}",
                        asset=pos.asset,
                        market="perp",
                        pnl_usd=pnl,
                        pnl_pct=pnl_pct,
                        close_reason=reason,
                        is_dry_run=ms.execution_mode == "dry_run",
                    )
                )

    async def _update_portfolio_state(
        self,
        session: AsyncSession,
        spot_positions: list,
        perp_positions: list,
        now: datetime,
    ) -> None:
        """Ricalcola equity, drawdown ed esposizione e aggiorna PortfolioState."""
        user_id = str(self.settings.default_user_id)
        pnl_repo = PnlRepository(session)
        portfolio = await pnl_repo.get_portfolio(user_id)
        if portfolio is None:
            return

        unrealized = sum((p.pnl_unrealized for p in spot_positions), Decimal("0")) + sum(
            (p.pnl_unrealized for p in perp_positions), Decimal("0")
        )

        spot_repo = SpotTradeRepository(session)
        perp_repo = PerpTradeRepository(session)
        realized_spot = await spot_repo.sum_realized_pnl(user_id)
        realized_perp = await perp_repo.sum_realized_pnl(user_id)
        realized = realized_spot + realized_perp
        total = portfolio.initial_equity_usd + realized + unrealized

        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        daily_realized_spot = await spot_repo.sum_realized_pnl(user_id, since=day_start)
        daily_realized_perp = await perp_repo.sum_realized_pnl(user_id, since=day_start)
        daily_pnl = daily_realized_spot + daily_realized_perp + unrealized
        # % di PnL giornaliero sull'equity (negativo in perdita) per la guardia daily_loss_limit.
        daily_loss_limit_used_pct = (
            (daily_pnl / total * 100).quantize(Decimal("0.01")) if total > 0 else Decimal("0")
        )

        # Esposizione = capitale impegnato (margine), non il nozionale: per il perp
        # si divide per la leva, così riflette quanto si consuma davvero dell'equity
        # (coerente col risk guard, che ragiona già in margine).
        spot_exposure = sum((p.entry_price * p.size for p in spot_positions), Decimal("0"))
        perp_exposure = sum(
            (p.entry_price * p.size / Decimal(max(int(p.leverage or 1), 1)) for p in perp_positions),
            Decimal("0"),
        )
        raw_exposure_pct = (spot_exposure + perp_exposure) / total * 100 if total > 0 else Decimal("0")
        exposure_pct = raw_exposure_pct.quantize(Decimal("0.01"))

        peak = max(portfolio.peak_equity_usd, total)
        drawdown = (peak - total) / peak * 100 if peak > 0 else Decimal("0")
        drawdown_pct = drawdown.quantize(Decimal("0.01"))
        max_drawdown_pct = max(portfolio.max_drawdown_pct, drawdown_pct)

        spot_count = await spot_repo.count_today(user_id, now)
        perp_count = await perp_repo.count_today(user_id, now)

        await pnl_repo.upsert_portfolio(
            user_id,
            total_equity_usd=total,
            peak_equity_usd=peak,
            drawdown_pct=drawdown_pct,
            max_drawdown_pct=max_drawdown_pct,
            exposure_pct=exposure_pct,
            daily_pnl_usd=daily_pnl,
            daily_loss_limit_used_pct=daily_loss_limit_used_pct,
            agent_status=self.risk.kill_switch.value,
            trades_today=spot_count + perp_count,
        )

    async def _snapshot_portfolio_hourly(self, session: AsyncSession, now: datetime) -> None:
        """Crea un PnlSnapshot ogni ora se non già presente per l'ora corrente."""
        user_id = str(self.settings.default_user_id)
        pnl_repo = PnlRepository(session)
        portfolio = await pnl_repo.get_portfolio(user_id)
        if portfolio is None:
            return

        recent = await pnl_repo.recent_for_user(user_id, limit=1)
        if recent:
            last_ts = recent[0].timestamp_utc
            if last_ts.year == now.year and last_ts.month == now.month and last_ts.day == now.day and last_ts.hour == now.hour:
                return

        open_spot = await SpotPositionRepository(session).open_for_user(user_id)
        open_perp = await PerpPositionRepository(session).open_for_user(user_id)
        spot_equity = sum((p.entry_price * p.size for p in open_spot), Decimal("0"))
        perp_equity = sum((p.entry_price * p.size for p in open_perp), Decimal("0"))

        snapshot = PnlSnapshot(
            user_id=user_id,
            timestamp_utc=now.replace(minute=0, second=0, microsecond=0),
            total_equity_usd=portfolio.total_equity_usd,
            spot_equity_usd=spot_equity,
            perp_equity_usd=perp_equity,
            cash_usd=Decimal("0"),
            drawdown_pct=portfolio.drawdown_pct,
            exposure_pct=portfolio.exposure_pct,
            daily_pnl_usd=portfolio.daily_pnl_usd,
            open_spot_positions=len(open_spot),
            open_perp_positions=len(open_perp),
        )
        await pnl_repo.save_snapshot(snapshot)

    async def slow_tick(self, session: AsyncSession, *, now: datetime | None = None) -> dict:
        """Slow scanner tick plus the hard daily Spot trade heartbeat."""

        heartbeat.beat("agent_slow_tick")
        _now = now or datetime.now(UTC)
        trade_heartbeat = await self._daily_trade_heartbeat(session, now=_now)
        markets = _active_markets(self._ms.markets_enabled)
        # Aggiorna il regime mercato una volta per ciclo, così il flag (e il messaggio
        # in app) riflette sempre lo stato reale anche se nessun segnale prova a entrare.
        if "spot" in markets:
            try:
                await self._spot_market_regime()
            except Exception as exc:
                logger.warning("spot_market_regime_error", error=str(exc))
        spot_assets = selected_spot_watchlist(self.settings) if "spot" in markets else []
        perp_assets = selected_perp_watchlist(self.settings) if "perp" in markets else []
        selected_assets = list(dict.fromkeys([*spot_assets, *perp_assets]))
        scanner_results = []
        for asset in spot_assets:
            if asset.upper() not in SPOT_EXCLUDED_STABLECOINS:
                try:
                    scanner_results.append(await self.evaluate_spot(_scanner_payload(asset, "spot"), session))
                except Exception as exc:
                    logger.warning("scanner_spot_asset_error", asset=asset, error=str(exc))
        for asset in perp_assets:
            try:
                scanner_results.append(await self.evaluate_perp(_scanner_payload(asset, "perp"), session))
            except Exception as exc:
                logger.warning("scanner_perp_asset_error", asset=asset, error=str(exc))
        try:
            await self._snapshot_portfolio_hourly(session, _now)
        except Exception as exc:
            logger.warning("snapshot_portfolio_hourly_failed", error=str(exc))
        try:
            await self._maybe_send_daily_summary(session, _now)
        except Exception as exc:
            logger.warning("daily_summary_failed", error=str(exc))
        return {
            "status": "idle" if trade_heartbeat["status"] != "executed" else "heartbeat_trade_executed",
            "reason": "watchlist_empty" if not selected_assets else "watchlist_scanned",
            "markets_enabled": self._ms.markets_enabled,
            "watchlist": selected_assets,
            "scanner_results": [_scanner_summary(result) for result in scanner_results],
            "daily_trade_heartbeat": trade_heartbeat,
        }

    async def _handle_signal(self, signal: dict, session: AsyncSession) -> dict:
        if signal.get("action") == "skip":
            skip_reasoning = _build_skip_reasoning(signal, self.settings)
            risk_decision = RiskDecision(False, f"signal_skipped:{signal.get('reason') or 'skip'}")
            brain_decision = self.brain._local_fallback(
                signal, risk_decision.__dict__, reason_prefix="no_signal_skip"
            )
            decision = await self._record_decision(
                session, signal, risk_decision, brain_decision, override_reasoning=skip_reasoning
            )
            return {
                "signal": signal,
                "risk": risk_decision.__dict__,
                "brain": brain_decision.__dict__,
                "decision_id": decision.decision_id,
                "execution": {"status": "skipped", "reason": signal.get("reason") or "signal_skipped"},
            }

        user_id = str(self.settings.default_user_id)
        now = datetime.now(UTC)

        if await self._in_cooldown(session, signal, now):
            risk_decision = RiskDecision(False, "cooldown_active")
            brain_decision = self.brain._local_fallback(
                signal, risk_decision.__dict__, reason_prefix="cooldown"
            )
            decision = await self._record_decision(session, signal, risk_decision, brain_decision)
            return {
                "signal": signal,
                "risk": risk_decision.__dict__,
                "brain": brain_decision.__dict__,
                "decision_id": decision.decision_id,
                "execution": {"status": "skipped", "reason": "cooldown_active"},
            }

        portfolio = await PnlRepository(session).get_portfolio(user_id)
        if portfolio is None and self._ms.execution_mode == "dry_run":
            portfolio = await _initialise_dry_run_portfolio(session, self.settings)
        spot_positions = await SpotPositionRepository(session).open_for_user(user_id)
        perp_positions = await PerpPositionRepository(session).open_for_user(user_id)
        intent = _intent_from_signal(signal, portfolio_total=Decimal(str(getattr(portfolio, "total_equity_usd", 0) or 0)))
        risk_decision = self.risk.evaluate(
            intent,
            portfolio=portfolio,
            open_spot_positions=spot_positions,
            open_perp_positions=perp_positions,
            ms=self._ms,
        )
        brain_decision = await self._brain_decision(session, signal, risk_decision)
        decision = await self._record_decision(session, signal, risk_decision, brain_decision)
        execution = {"status": "skipped", "reason": "brain_or_risk_blocked"}
        if risk_decision.allowed and brain_decision.allows_execution:
            execution = await self._execute_or_simulate(session, signal, risk_decision, brain_decision)
            decision.execution_result = execution["status"]
            decision.trade_id = execution.get("trade_id")
            await session.commit()
        return {
            "signal": signal,
            "risk": risk_decision.__dict__,
            "brain": brain_decision.__dict__,
            "decision_id": decision.decision_id,
            "execution": execution,
        }

    async def _brain_decision(self, session: AsyncSession, signal: dict, risk_decision) -> object:
        try:
            decision, usage = await self.brain.decide(signal=signal, risk=risk_decision.__dict__)
        except MetaControllerError:
            self.risk.mark_degraded("claude_unavailable")
            decision, usage = await self.brain.decide(
                signal={**signal, "quality": 0},
                risk={"allowed": False, "reason": "claude_unavailable"},
            )
        if usage is not None:
            try:
                await ApiUsageRepository(session).record(
                    model=usage.model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                )
            except Exception:
                pass  # non bloccare il trade per errori di logging
        return decision

    async def _in_cooldown(self, session: AsyncSession, signal: dict, now: datetime) -> bool:
        """True se esiste un trade recente sull'asset entro la finestra di cooldown."""
        ms = self._ms
        market = signal.get("market", "spot")
        minutes = ms.perp_cooldown_minutes if market == "perp" else ms.spot_cooldown_minutes
        asset = signal.get("asset")
        if minutes <= 0 or not asset:
            return False
        user_id = str(self.settings.default_user_id)
        asset = str(asset)
        spot_ts = await SpotTradeRepository(session).last_timestamp_for_asset(user_id, asset)
        perp_ts = await PerpTradeRepository(session).last_timestamp_for_asset(user_id, asset)
        candidates = [t for t in (spot_ts, perp_ts) if t is not None]
        if not candidates:
            return False
        last_ts = max(candidates)
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=UTC)
        return (now - last_ts) < timedelta(minutes=minutes)

    async def _record_decision(
        self,
        session: AsyncSession,
        signal: dict,
        risk_decision,
        brain_decision,
        *,
        override_reasoning: str | None = None,
    ) -> AgentDecision:
        reasoning = override_reasoning if override_reasoning is not None else f"{brain_decision.reasoning}; risk={risk_decision.reason}"
        decision = AgentDecision(
            decision_id=f"dec_{uuid4().hex}",
            user_id=str(self.settings.default_user_id),
            timestamp_utc=datetime.now(UTC),
            asset=signal.get("asset"),
            market=str(signal.get("market", "spot")),
            signal_quality=Decimal(str(signal.get("quality", 0))),
            confidence=brain_decision.confidence,
            action=brain_decision.action,
            reasoning=reasoning,
            execution_result=None,
            trade_id=None,
        )
        return await AgentDecisionRepository(session).save(decision)

    async def _execute_or_simulate(self, session: AsyncSession, signal: dict, risk_decision, brain_decision) -> dict:
        # H (v3): size_factor dal segnale (anti-spike reduce_size); default 1.0.
        ms = self._ms
        fixed_perp_margin = signal.get("market") == "perp" and ms.perp_fixed_margin_enabled
        size_factor = Decimal("1") if fixed_perp_margin else Decimal(str(signal.get("size_factor", 1) or 1))
        size_multiplier = Decimal("1") if fixed_perp_margin else brain_decision.size_multiplier
        size_quote = risk_decision.size_quote * size_multiplier * size_factor
        if ms.execution_mode == "dry_run":
            execution = await self._simulate_trade(session, signal, size_quote)
        elif signal.get("market") == "spot":
            # In live i parametri on-chain (token + amount) sono assenti dal segnale:
            # li deriviamo dalla mappa token configurata; se mancano, skip esplicito.
            if signal.get("from_asset") and signal.get("to_asset") and signal.get("amount_in_atomic") is not None:
                swap_params: dict | None = {}
            else:
                swap_params = await self._build_spot_swap_params(signal, size_quote)
            if swap_params is None:
                execution = {"status": "skipped", "reason": "spot_token_not_mapped"}
            else:
                execution = await self._execute_spot({**signal, **swap_params}, size_quote)
        else:
            execution = await self._execute_perp(signal, size_quote)

        if execution.get("trade_id") and execution.get("status") in {"prepared", "confirmed"}:
            asyncio.create_task(self._notify_trade_opened(signal, risk_decision, execution))
        return execution

    def _token_resolver(self) -> CMCProvider | None:
        """Resolver CMC per gli indirizzi token (lazy). None se non configurato."""
        if self._token_resolver_override is not None:
            return self._token_resolver_override
        if self._token_resolver_cached is _UNSET:
            try:
                self._token_resolver_cached = (
                    CMCProvider(self.settings) if getattr(self.settings, "cmc_api_key", None) else None
                )
            except Exception:
                self._token_resolver_cached = None
        return self._token_resolver_cached  # type: ignore[return-value]

    async def _resolve_token_address(self, symbol: str) -> str | None:
        """Indirizzo BSC del token: mappa statica (override) poi risoluzione CMC."""
        entry = self.settings.spot_token_map.get(symbol.upper())
        if entry:
            address, _, _decimals = entry.partition(":")
            if address:
                return address
        resolver = self._token_resolver()
        if resolver is not None:
            return await resolver.resolve_contract_address(symbol)
        return None

    async def _build_spot_swap_params(self, signal: dict, size_quote: Decimal) -> dict | None:
        """Costruisce from_asset/to_asset/amount_in_atomic per lo swap spot live.

        Indirizzi token: mappa statica (override .env) con fallback automatico a CMC.
        Ritorna None se non risolvibili (spot live non eseguibile per quell'asset).
        """
        asset = str(signal.get("asset") or "").upper()
        if not asset:
            return None
        to_address = await self._resolve_token_address(asset)
        if not to_address:
            return None
        quote_address = self.settings.spot_quote_token_address
        quote_decimals = int(self.settings.spot_quote_token_decimals)
        if not quote_address:
            # Quote di default: USDT, risolto via CMC se non configurato esplicitamente.
            quote_address = await self._resolve_token_address("USDT")
        if not quote_address:
            return None
        amount_in_atomic = int(size_quote * (Decimal(10) ** quote_decimals))
        if amount_in_atomic <= 0:
            return None
        return {
            "from_asset": quote_address,
            "to_asset": to_address,
            "amount_in_atomic": amount_in_atomic,
        }

    async def _simulate_trade(self, session: AsyncSession, signal: dict, size_quote: Decimal) -> dict:
        now = datetime.now(UTC)
        trade_id = f"dry_{uuid4().hex}"
        price = Decimal(str(signal.get("price", "0")))
        if price <= 0:
            return {"status": "skipped", "reason": "price_unavailable"}
        if signal.get("market") == "perp":
            side = str(signal.get("side") or "long")
            leverage = int(signal.get("leverage") or self._ms.perp_min_leverage)
            fee_mode = self._ms.perp_fee_mode
            notional_usd = size_quote * Decimal(leverage)

            # Fetch fee e funding da PancakeSwap Perps v2 (fallback a costanti se offline)
            fee_snapshot = await fetch_perp_fees(
                asset=str(signal.get("asset", "")),
                size_usd=notional_usd,
                fee_mode=fee_mode,
            )
            costs = compute_opening_costs(fee_snapshot, notional_usd)

            # Applica slippage al prezzo di entrata (solo taker): l'entry effettivo
            # è peggiore del mark price di una frazione price_impact_pct.
            if fee_mode == "taker" and costs["price_impact_pct"] > 0:
                direction_mult = Decimal("1") if side == "long" else Decimal("-1")
                effective_price = price * (
                    Decimal("1") + direction_mult * costs["price_impact_pct"] / Decimal("100")
                )
            else:
                effective_price = price

            # size = contratti controllati: capitale * leva / prezzo effettivo
            leveraged_size = size_quote * Decimal(leverage) / effective_price
            stop_ref = _stop_reference_from_signal(signal)

            await PerpTradeRepository(session).save(
                PerpTrade(
                    trade_id=trade_id,
                    user_id=str(self.settings.default_user_id),
                    asset=str(signal.get("asset")),
                    side=side,
                    direction="open",
                    size=leveraged_size,
                    price=effective_price,
                    leverage=leverage,
                    status=ExecutionStatus.PREPARED.value,
                    timestamp_utc=now,
                    venue="dry_run",
                    signal_id=signal.get("signal_id"),
                    notes="dry_run_step6",
                    fee_mode=fee_mode,
                    taker_fee_usd=costs["taker_fee_usd"],
                    maker_fee_usd=costs["maker_fee_usd"],
                    slippage_usd=costs["slippage_usd"],
                    funding_rate_8h=costs["funding_rate_8h"],
                    fees_quote=costs["applied_fee_usd"],
                    slippage_pct=costs["price_impact_pct"],
                )
            )
            await PerpPositionRepository(session).save(
                PerpPosition(
                    position_id=f"pos_{uuid4().hex}",
                    user_id=str(self.settings.default_user_id),
                    asset=str(signal.get("asset")),
                    side=side,
                    size=leveraged_size,
                    entry_price=effective_price,
                    current_price=effective_price,
                    leverage=leverage,
                    stop_loss=_optional_decimal(signal.get("stop_loss")),
                    initial_stop_loss=_optional_decimal(signal.get("stop_loss")),
                    take_profit_1=_optional_decimal(signal.get("take_profit_1")),
                    take_profit_2=_optional_decimal(signal.get("take_profit_2")),
                    trailing_stop=_optional_decimal(signal.get("trailing_stop")),
                    # Congelati all'ingresso per breakeven + trailing dinamico.
                    entry_atr=_optional_decimal((signal.get("components") or {}).get("atr")),
                    stop_reference_time=stop_ref["time"],
                    stop_reference_price=stop_ref["price"],
                    stop_reference_field=stop_ref["field"],
                    max_price=effective_price,
                    liquidation_price=_estimate_liquidation_price(effective_price, leverage, side),
                    funding_rate=costs["funding_rate_8h"],
                    fee_mode=fee_mode,
                    margin_usd=size_quote,
                    opening_fee_usd=costs["applied_fee_usd"],
                    taker_fee_usd=costs["taker_fee_usd"],
                    maker_fee_usd=costs["maker_fee_usd"],
                    slippage_usd=costs["slippage_usd"],
                    funding_accrued_usd=Decimal("0"),
                    venue="dry_run",
                    open_trade_id=trade_id,
                    opened_at=now,
                    updated_at=now,
                )
            )
            return {"status": "prepared", "mode": "dry_run", "trade_id": trade_id}

        spot_fee_mode = self._ms.spot_fee_mode
        spot_costs = compute_spot_costs(size_quote, spot_fee_mode)

        # Applica slippage al prezzo di acquisto (buy a prezzo leggermente peggiore)
        if spot_fee_mode == "all" and spot_costs["slippage_rate"] > 0:
            effective_spot_price = price * (Decimal("1") + spot_costs["slippage_rate"])
        else:
            effective_spot_price = price

        spot_amount = size_quote / effective_spot_price
        stop_ref = _stop_reference_from_signal(signal)

        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id=trade_id,
                user_id=str(self.settings.default_user_id),
                asset=str(signal.get("asset")),
                side="buy",
                amount=spot_amount,
                price=effective_spot_price,
                amount_quote=size_quote,
                status=ExecutionStatus.PREPARED.value,
                provider="dry_run",
                timestamp_utc=now,
                signal_id=signal.get("signal_id"),
                notes="dry_run_step6",
                fee_mode=spot_fee_mode,
                swap_fee_usd=spot_costs["swap_fee_usd"],
                slippage_usd=spot_costs["slippage_usd"],
                fees_quote=spot_costs["applied_fee_usd"],
            )
        )
        await SpotPositionRepository(session).save(
            SpotPosition(
                position_id=f"pos_{uuid4().hex}",
                user_id=str(self.settings.default_user_id),
                asset=str(signal.get("asset")),
                size=spot_amount,
                entry_price=effective_spot_price,
                current_price=effective_spot_price,
                stop_loss=_optional_decimal(signal.get("stop_loss")),
                initial_stop_loss=_optional_decimal(signal.get("stop_loss")),
                take_profit_1=_optional_decimal(signal.get("take_profit_1")),
                take_profit_2=_optional_decimal(signal.get("take_profit_2")),
                trailing_stop=_optional_decimal(signal.get("trailing_stop")),
                # C (v3): ATR congelato all'ingresso + max_price per breakeven/trailing ATR.
                entry_atr=_optional_decimal((signal.get("components") or {}).get("atr")),
                stop_reference_time=stop_ref["time"],
                stop_reference_price=stop_ref["price"],
                stop_reference_field=stop_ref["field"],
                max_price=effective_spot_price,
                fee_mode=spot_fee_mode,
                swap_fee_usd=spot_costs["swap_fee_usd"],
                slippage_usd=spot_costs["slippage_usd"],
                open_trade_id=trade_id,
                opened_at=now,
                updated_at=now,
            )
        )
        return {"status": "prepared", "mode": "dry_run", "trade_id": trade_id}

    async def _execute_spot(self, signal: dict, size_quote: Decimal) -> dict:
        if not self.settings.wallet_address:
            return {"status": "skipped", "reason": "wallet_address_missing"}
        from_asset = signal.get("from_asset")
        to_asset = signal.get("to_asset")
        if not from_asset or not to_asset:
            return {"status": "skipped", "reason": "spot_asset_addresses_required"}
        amount_in_atomic = signal.get("amount_in_atomic")
        if amount_in_atomic is None:
            return {"status": "skipped", "reason": "spot_amount_in_atomic_required"}
        quote = await self.spot_registry.active.get_quote(
            amount_in_atomic=int(amount_in_atomic),
            from_asset=str(from_asset),
            to_asset=str(to_asset),
            wallet_address=self.settings.wallet_address,
            slippage_pct=Decimal(str(self._ms.spot_max_slippage_pct)),
        )
        return {"status": "prepared", "provider": self.spot_registry.active_name.value, "quote": quote.model_dump()}

    async def _execute_perp(self, signal: dict, size_quote: Decimal) -> dict:
        order = PerpOrder(
            asset=str(signal.get("asset")),
            direction=str(signal.get("side") or "long"),  # type: ignore[arg-type]
            size=size_quote,
            leverage=Decimal(str(signal.get("leverage") or self._ms.perp_min_leverage)),
        )
        result = await self.perp_registry.active.open_position(order)
        return {"status": result.status.value, "provider": self.perp_registry.active_name.value, "reason": result.reason}

    async def _daily_trade_heartbeat(self, session: AsyncSession, *, now: datetime | None = None) -> dict:
        now = now or datetime.now(UTC)
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        now = now.astimezone(UTC)
        user_id = str(self.settings.default_user_id)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = await SpotTradeRepository(session).count_since(user_id, since=day_start)
        if trades_today >= self.settings.minimum_trades_per_day:
            return {
                "status": "satisfied",
                "trades_today": trades_today,
                "check_after_utc": DAILY_TRADE_CHECK_TIME_UTC.isoformat(),
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        current_time = now.timetz()
        if current_time < DAILY_TRADE_CHECK_TIME_UTC:
            return {
                "status": "waiting",
                "trades_today": trades_today,
                "check_after_utc": DAILY_TRADE_CHECK_TIME_UTC.isoformat(),
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        if current_time > DAILY_TRADE_RETRY_UNTIL_UTC:
            return {
                "status": "missed",
                "trades_today": trades_today,
                "reason": "daily_trade_retry_window_closed",
                "check_after_utc": DAILY_TRADE_CHECK_TIME_UTC.isoformat(),
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        if self.risk.kill_switch != KillSwitchState.RUNNING:
            return {
                "status": "blocked",
                "trades_today": trades_today,
                "reason": self.risk.kill_switch.value,
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        # Dedup: se ETH e' gia' in posizione (spot o perp), non forzare un secondo trade.
        open_spot = await SpotPositionRepository(session).open_for_user(user_id)
        open_perp = await PerpPositionRepository(session).open_for_user(user_id)
        if any(p.asset.upper() == HEARTBEAT_TRADE_ASSET for p in (*open_spot, *open_perp)):
            return {
                "status": "satisfied",
                "trades_today": trades_today,
                "reason": "asset_already_open",
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        # Prezzo live via feed riusato; SL/TP derivati dal segnale momentum reale.
        heartbeat_price = HEARTBEAT_TRADE_PRICE_USD_FALLBACK
        try:
            ticker = await self.price_feed.fetch_prices(
                symbols=[f"{HEARTBEAT_TRADE_ASSET}USDT"], market="spot"
            )
            heartbeat_price = ticker.get(f"{HEARTBEAT_TRADE_ASSET}USDT", heartbeat_price)
        except Exception:
            pass
        sl = tp1 = tp2 = trailing = None
        try:
            momentum = await self.spot_signal.evaluate(_scanner_payload(HEARTBEAT_TRADE_ASSET, "spot"))
            if momentum.get("price"):
                heartbeat_price = Decimal(str(momentum["price"]))
            sl = _optional_decimal(momentum.get("stop_loss"))
            tp1 = _optional_decimal(momentum.get("take_profit_1"))
            tp2 = _optional_decimal(momentum.get("take_profit_2"))
            trailing = _optional_decimal(momentum.get("trailing_stop"))
        except Exception:
            pass
        # Fallback: livelli di default se il segnale non li ha forniti (es. storico insufficiente).
        if sl is None:
            sl = heartbeat_price * Decimal("0.98")
        if tp1 is None:
            tp1 = heartbeat_price * Decimal("1.03")
        if tp2 is None:
            tp2 = heartbeat_price * Decimal("1.06")
        if trailing is None:
            trailing = heartbeat_price * Decimal("0.98")
        signal = {
            "signal_id": f"heartbeat_{now.date().isoformat()}",
            "market": "spot",
            "asset": HEARTBEAT_TRADE_ASSET,
            "action": "enter_long",
            "quality": 0.86,
            "confidence": 0.86,
            "price": heartbeat_price,
            "stop_loss": sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "trailing_stop": trailing,
            "quote_equity": Decimal(str(self.settings.dry_run_capital_usd)),
            "heartbeat_trade": True,
        }
        heartbeat_trade_quote_usd = max(Decimal(str(self.settings.min_trade_size_usd)), Decimal("1"))
        if self._ms.execution_mode == "dry_run":
            execution = await self._simulate_trade(session, signal, heartbeat_trade_quote_usd)
            return {
                "status": "executed",
                "mode": "dry_run",
                "trades_today_before": trades_today,
                "execution": execution,
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        from_asset = getattr(self.settings, "heartbeat_trade_from_asset", None)
        to_asset = getattr(self.settings, "heartbeat_trade_to_asset", None)
        amount_in_atomic = getattr(self.settings, "heartbeat_trade_amount_in_atomic", None)
        if not from_asset or not to_asset or amount_in_atomic is None:
            return {
                "status": "blocked",
                "trades_today": trades_today,
                "reason": "heartbeat_trade_live_route_not_configured",
                "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
            }
        execution = await self._execute_spot(
            {**signal, "from_asset": from_asset, "to_asset": to_asset, "amount_in_atomic": amount_in_atomic},
            heartbeat_trade_quote_usd,
        )
        return {
            "status": "executed" if execution.get("status") in {"prepared", "confirmed"} else "blocked",
            "mode": self._ms.execution_mode,
            "trades_today_before": trades_today,
            "execution": execution,
            "retry_until_utc": DAILY_TRADE_RETRY_UNTIL_UTC.isoformat(),
        }

    # ------------------------------------------------------------------
    # Integrazione notifiche agente
    # ------------------------------------------------------------------

    async def _notify_trade_opened(self, signal: dict, risk_decision, execution: dict) -> None:
        """Fire-and-forget notifica apertura trade; mai blocca l'agente."""
        try:
            notifier = get_agent_notifier()
            market = str(signal.get("market", "spot"))
            await notifier.notify_trade_opened(
                user_id=str(self.settings.default_user_id),
                trade_id=execution["trade_id"],
                asset=str(signal.get("asset", "")),
                market=market,
                direction=str(signal.get("side") or signal.get("action") or "buy"),
                entry_price=Decimal(str(signal.get("price", "0"))),
                size_usd=risk_decision.size_quote,
                stop_loss=_optional_decimal(signal.get("stop_loss")),
                is_dry_run=self._ms.execution_mode == "dry_run",
            )
        except Exception:
            pass  # le notifiche non bloccano mai l'agente

    async def _check_risk_notifications(self, session: AsyncSession, spot_positions: list, perp_positions: list) -> None:
        """Controlla condizioni di rischio e invia push se necessario."""
        try:
            user_id = str(self.settings.default_user_id)
            portfolio = await PnlRepository(session).get_portfolio(user_id)
            if portfolio is None:
                return
            notifier = get_agent_notifier()

            # Kill switch attivo
            if self.risk.kill_switch != KillSwitchState.RUNNING:
                await notifier.notify_risk_alert(
                    user_id, "kill_switch",
                    f"Kill switch: {self.risk.kill_switch.value}"
                )
                return

            # Drawdown
            drawdown = float(getattr(portfolio, "drawdown_pct", 0) or 0)
            if self.settings.risk_drawdown_alert_enabled and drawdown >= self.settings.risk_notify_drawdown_pct:
                await notifier.notify_risk_alert(
                    user_id, "drawdown",
                    f"Drawdown {drawdown:.1f}% supera soglia {self.settings.risk_notify_drawdown_pct:.0f}%"
                )

            # Portfolio floor
            equity = float(getattr(portfolio, "total_equity_usd", 1) or 1)
            if equity < 1.0:
                await notifier.notify_risk_alert(user_id, "portfolio_floor", "Equity < $1.00")
        except Exception:
            pass  # le notifiche non bloccano mai l'agente

    async def _maybe_send_daily_summary(self, session: AsyncSession, now: datetime) -> None:
        """Invia riepilogo giornaliero una volta al giorno all'ora configurata."""
        try:
            target_h = self.settings.agent_summary_hour_utc
            target_m = self.settings.agent_summary_minute_utc
            if now.hour != target_h or now.minute != target_m:
                return
            user_id = str(self.settings.default_user_id)
            # Anti-spam: verifica se già inviato oggi
            today_key = f"summary_sent_{now.date().isoformat()}"
            if get_runtime_value(user_id, today_key):
                return

            portfolio = await PnlRepository(session).get_portfolio(user_id)
            spot_today = await SpotTradeRepository(session).count_today(user_id, now)
            perp_today = await PerpTradeRepository(session).count_today(user_id, now)

            notifier = get_agent_notifier()
            daily_pnl = Decimal(str(getattr(portfolio, "daily_pnl_usd", "0") or "0")) if portfolio else Decimal("0")
            await notifier.notify_daily_summary(
                user_id=user_id,
                spot_trades=spot_today,
                perp_trades=perp_today,
                daily_pnl_usd=daily_pnl,
                win_rate_pct=0.0,
            )
            set_runtime_value(user_id, today_key, "1")
        except Exception:
            pass  # le notifiche non bloccano mai l'agente


def _intent_from_signal(signal: dict, *, portfolio_total: Decimal) -> SignalIntent:
    return SignalIntent(
        asset=str(signal.get("asset") or ""),
        market=str(signal.get("market") or "spot"),
        side=str(signal.get("side") or signal.get("action") or ""),
        price=Decimal(str(signal.get("price") or "0")),
        stop_loss=_optional_decimal(signal.get("stop_loss")),
        quality=Decimal(str(signal.get("quality") or "0")),
        quote_equity=Decimal(str(signal.get("quote_equity") or portfolio_total or "0")),
        liquidity_usd=_optional_decimal(signal.get("liquidity_usd")),
    )


def _optional_decimal(value) -> Decimal | None:
    if value is None:
        return None
    parsed = Decimal(str(value))
    return parsed if parsed > 0 else None


def _stop_reference_from_signal(signal: dict) -> dict[str, datetime | Decimal | str | None]:
    ref = (signal.get("components") or {}).get("stop_reference")
    if not isinstance(ref, dict):
        return {"time": None, "price": None, "field": None}
    parsed_time = None
    try:
        raw_time = ref.get("timestamp")
        if raw_time:
            parsed_time = datetime.fromisoformat(str(raw_time))
            if parsed_time.tzinfo is None:
                parsed_time = parsed_time.replace(tzinfo=UTC)
            parsed_time = parsed_time.astimezone(UTC)
    except Exception:
        parsed_time = None
    parsed_price = _optional_decimal(ref.get("price"))
    field = str(ref.get("field") or "")[:8] or None
    return {"time": parsed_time, "price": parsed_price, "field": field}


def _level_fill_price(pos, reason: str, market_price: Decimal) -> Decimal:
    """Prezzo di fill per le chiusure su livello.

    Uno stop/TP/trailing riempie al PROPRIO livello, non al prezzo di mercato:
    se il refresh è in ritardo (feed instabile, prezzo non aggiornato per più
    cicli) il mercato può aver superato di molto il livello, e chiudere a quel
    prezzo gonfia la perdita ben oltre il rischio realmente assunto (critico con
    leva alta). Le chiusure NON su livello (time_stop, manuali) usano il mercato.
    """
    level = None
    if reason == "stop_loss":
        level = pos.stop_loss
    elif reason == "breakeven":
        # Breakeven comes from stop_loss moved to entry/costs. Trailing keeps
        # reason="trailing_stop", even when the trailing level is profitable.
        level = pos.stop_loss
    elif reason == "trailing_stop":
        level = pos.trailing_stop
    elif reason == "take_profit_1":
        level = pos.take_profit_1
    elif reason == "take_profit_2":
        level = pos.take_profit_2
    if level is None:
        return market_price
    return Decimal(str(level))


def _perp_trailing_mult(
    *, leverage: int, min_lev: int, max_lev: int, base: float, floor: float
) -> Decimal:
    """Moltiplicatore ATR del trailing perp, dinamico sulla leva del trade.

    Interpola linearmente tra `base` (a leva minima → trailing largo) e `floor`
    (a leva massima → trailing stretto): più alta la leva, più stretto il trailing
    in prezzo, così non si restituisce il profitto amplificato dalla leva. Il
    floor resta sopra il rumore (ATR) per evitare il whipsaw.
    """
    lo = min(min_lev, max_lev)
    hi = max(min_lev, max_lev)
    if hi <= lo:
        t = 0.0
    else:
        t = (leverage - lo) / (hi - lo)
        t = min(1.0, max(0.0, t))
    mult = base - t * (base - floor)
    return Decimal(str(mult))


async def _initialise_dry_run_portfolio(session: AsyncSession, settings: Settings):
    capital = Decimal(str(settings.dry_run_capital_usd))
    return await PnlRepository(session).upsert_portfolio(
        str(settings.default_user_id),
        total_equity_usd=capital,
        initial_equity_usd=capital,
        peak_equity_usd=capital,
        agent_status="idle",
    )


def _active_markets(value: str) -> set[str]:
    normalized = value.lower()
    if normalized == "spot":
        return {"spot"}
    if normalized in {"perp", "perpetual"}:
        return {"perp"}
    return {"spot", "perp"}


def _scanner_payload(asset: str, market: str) -> dict:
    symbol = f"{asset.upper()}USDT"
    return {
        "signal_id": f"scan_{market}_{asset.upper()}_{uuid4().hex[:12]}",
        "market": market,
        "asset": asset.upper(),
        "symbol": symbol,
        "quote_asset": "USDT",
    }


def _scanner_summary(result: dict) -> dict:
    signal = result.get("signal") or {}
    risk = result.get("risk") or {}
    execution = result.get("execution") or {}
    return {
        "asset": signal.get("asset"),
        "market": signal.get("market"),
        "action": signal.get("action"),
        "reason": signal.get("reason") or risk.get("reason") or execution.get("reason"),
        "risk_allowed": risk.get("allowed"),
        "execution_status": execution.get("status"),
    }


def _build_skip_reasoning(signal: dict, settings) -> str:
    """Costruisce un reasoning leggibile per i segnali skippati, con valori reali e threshold."""
    reason = signal.get("reason") or "skip"
    components = signal.get("components") or {}
    quality = float(signal.get("quality") or 0)
    price = float(signal.get("price") or 0)

    def _ok(cond: bool) -> str:
        return "✓" if cond else "✗"

    if reason == "spot_filters_not_satisfied":
        trend = float(components.get("trend_structure") or 0)
        rvol = float(components.get("relative_volume") or 0)
        vol_pct = float(components.get("volatility_pct") or 0)
        rsi_v = components.get("rsi")
        ext = float(components.get("vwap_atr_extension") or 0)
        ext_ok = bool(components.get("extension_ok", True))
        thr_rvol = float(settings.spot_relative_volume_threshold)
        thr_vol = float(settings.spot_volatility_trigger_pct)
        thr_ext = float(settings.spot_vwap_atr_extension_limit)
        thr_q = float(settings.spot_confidence_threshold)
        parts = [
            f"trend={trend:.2f}{_ok(trend >= 0.45)}",
            f"rvol={rvol:.2f}{_ok(rvol >= thr_rvol)}(≥{thr_rvol})",
            f"vol%={vol_pct:.2f}{_ok(vol_pct >= thr_vol)}(≥{thr_vol})",
            f"ext={ext:.2f}{_ok(ext_ok)}(≤{thr_ext})",
        ]
        if rsi_v is not None:
            parts.append(f"rsi={float(rsi_v):.0f}{_ok(45 <= float(rsi_v) <= 72)}(45-72)")
        parts.append(f"q={quality:.2f}{_ok(quality >= thr_q)}(≥{thr_q})")
        return "spot_skip: " + " | ".join(parts)

    if reason == "perp_filters_not_satisfied":
        poc = components.get("poc")
        vah = components.get("vah")
        val = components.get("val")
        vwap_v = components.get("vwap")
        trend_bias = components.get("trend_bias", "?")
        side = signal.get("side")
        parts = [
            f"price={price:.5g}",
            f"poc={poc:.5g}" if poc else "poc=?",
            f"val={val:.5g}" if val else "val=?",
            f"vah={vah:.5g}" if vah else "vah=?",
            f"vwap={vwap_v:.5g}" if vwap_v else "vwap=?",
            f"bias={trend_bias}",
            f"side={side or 'none'}",
            f"q={quality:.2f}(≥0.60)",
        ]
        return "perp_skip: " + " | ".join(parts)

    if reason == "insufficient_ohlcv_history":
        count = components.get("candle_count", "?")
        req = components.get("required_candles", "?")
        return f"skip: {count}/{req} candele disponibili"

    return f"skip: {reason}"


def _coverage_item(
    *,
    asset: str,
    market: str,
    symbol: str,
    required_candles: int,
    source: str,
    cache_market: BinanceMarket,
    now: datetime,
    interval: str = "5m",
) -> dict:
    entry = get_kline_cache_entry(market=cache_market, symbol=symbol, interval=interval)
    candles = entry.candles if entry else []
    candle_count = len(candles)
    first_timestamp = candles[0].timestamp if candles else None
    last_timestamp = candles[-1].timestamp if candles else None
    updated_at = entry.updated_at if entry else None
    if candle_count >= required_candles:
        status = "ready"
    elif candle_count > 0:
        status = "warming_up"
    else:
        status = "insufficient"
    return {
        "asset": asset,
        "market": market,
        "symbol": symbol,
        "available_candles": candle_count,
        "required_candles": required_candles,
        "status": status,
        "first_candle_at": first_timestamp.isoformat() if first_timestamp else None,
        "last_candle_at": last_timestamp.isoformat() if last_timestamp else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
        "age_seconds": round((now - updated_at).total_seconds(), 2) if updated_at else None,
        "source": source,
    }


@lru_cache
def get_agent_service() -> AgentService:
    return AgentService(get_settings())


async def run_agent_fast_tick() -> dict:
    async with get_session_factory()() as session:
        return await get_agent_service().fast_tick(session)


async def run_agent_slow_tick() -> dict:
    async with get_session_factory()() as session:
        return await get_agent_service().slow_tick(session)
