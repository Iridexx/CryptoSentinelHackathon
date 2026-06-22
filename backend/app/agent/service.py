"""Autonomous agent orchestration for Step 6."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from functools import lru_cache
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.agent.brain import ClaudeMetaController, MetaControllerError
from backend.app.agent.heartbeat import heartbeat
from backend.app.agent.risk import KillSwitchState, RiskDecision, RiskManager, SignalIntent
from backend.app.agent.signals.perp.binance_klines import BinanceKlineFeed, BinanceMarket, get_kline_cache_entry
from backend.app.agent.signals.perp.volume_profile import VolumeProfileSignal
from backend.app.agent.signals.spot.momentum import MIN_SPOT_CANDLES, SpotMomentumSignal
from backend.app.agent.watchlist import selected_watchlist
from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
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
from backend.app.persistence.repositories.trades import PerpTradeRepository, SpotTradeRepository
from backend.app.persistence.runtime_state import get_runtime_value, set_runtime_value

logger = get_logger("agent.service")

DAILY_TRADE_CHECK_TIME_UTC = time(20, 0, tzinfo=UTC)
DAILY_TRADE_RETRY_UNTIL_UTC = time(23, 30, tzinfo=UTC)
HEARTBEAT_TRADE_ASSET = "ETH"
HEARTBEAT_TRADE_PRICE_USD_FALLBACK = Decimal("1")
# Distanza trailing-stop per il perp (coerente col livello generato dal segnale, 1%).
PERP_TRAILING_DISTANCE_PCT = Decimal("1.0")


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
    ) -> None:
        self.settings = settings or get_settings()
        self.spot_signal = spot_signal or SpotMomentumSignal(self.settings)
        self.perp_signal = perp_signal or VolumeProfileSignal(self.settings)
        self.risk = risk_manager or RiskManager(self.settings)
        self.brain = brain or ClaudeMetaController(self.settings)
        self.spot_registry = spot_registry or get_execution_provider_registry()
        self.perp_registry = perp_registry or get_perp_execution_registry()

    def status(self) -> dict:
        return {
            "mode": self.settings.agent_mode,
            "markets_enabled": self.settings.markets_enabled,
            "execution_mode": self.settings.execution_mode,
            "kill_switch": self.risk.kill_switch.value,
            "degraded_reasons": sorted(self.risk.degraded_reasons),
            "eligible_token_count": len(self.settings.eligible_tokens),
            "eligible_symbol_count": len(self.risk.eligible_symbols),
            "watchlist_count": len(selected_watchlist(self.settings)),
            "heartbeat": heartbeat.as_dict(),
        }

    def data_coverage(self) -> dict:
        """Return signal-engine OHLCV cache coverage for eligible active assets."""

        markets = _active_markets(self.settings.markets_enabled)
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

    async def evaluate_spot(self, payload: dict, session: AsyncSession) -> dict:
        signal = await self.spot_signal.evaluate(payload)
        return await self._handle_signal(signal, session)

    async def evaluate_perp(self, payload: dict, session: AsyncSession) -> dict:
        signal = await self.perp_signal.evaluate(payload)
        return await self._handle_signal(signal, session)

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
        feed = BinanceKlineFeed()
        now = datetime.now(UTC)

        perp_assets: set[str] = {p.asset for p in perp_positions}
        spot_assets: set[str] = {p.asset for p in spot_positions}

        perp_prices: dict[str, Decimal] = {}
        for asset in perp_assets:
            try:
                candles = await feed.fetch(symbol=f"{asset}USDT", interval="1m", limit=1, market="futures")
                if candles:
                    perp_prices[asset] = Decimal(str(candles[-1].close))
            except Exception:
                pass

        spot_prices: dict[str, Decimal] = {}
        for asset in spot_assets:
            try:
                candles = await feed.fetch(symbol=f"{asset}USDT", interval="1m", limit=1, market="spot")
                if candles:
                    spot_prices[asset] = Decimal(str(candles[-1].close))
            except Exception:
                pass

        updated = False
        for pos in perp_positions:
            price = perp_prices.get(pos.asset)
            if price is None:
                continue
            pnl = (price - pos.entry_price) * pos.size if pos.side == "long" else (pos.entry_price - price) * pos.size
            pos.current_price = price
            pos.pnl_unrealized = pnl
            pos.updated_at = now
            session.add(pos)
            updated = True

        for pos in spot_positions:
            price = spot_prices.get(pos.asset)
            if price is None:
                continue
            pos.current_price = price
            pos.pnl_unrealized = (price - pos.entry_price) * pos.size
            pos.updated_at = now
            session.add(pos)
            updated = True

        if updated:
            await session.commit()

    async def _close_spot_position(
        self,
        session: AsyncSession,
        pos: SpotPosition,
        exit_price: Decimal,
        reason: str,
        now: datetime,
    ) -> Decimal:
        """Chiude una posizione spot: aggiorna status, crea trade di chiusura con pnl_usd."""
        pnl = (exit_price - pos.entry_price) * pos.size
        pos.status = "closed"
        pos.current_price = exit_price
        pos.pnl_unrealized = pnl
        pos.updated_at = now
        session.add(pos)
        close_trade = SpotTrade(
            trade_id=f"cls_{pos.position_id}_{uuid4().hex[:8]}",
            user_id=pos.user_id,
            asset=pos.asset,
            side="sell",
            amount=pos.size,
            price=exit_price,
            amount_quote=exit_price * pos.size,
            status="confirmed",
            provider="agent",
            timestamp_utc=now,
            notes=f"auto_close:{reason}",
            pnl_usd=pnl,
        )
        await SpotTradeRepository(session).save(close_trade)
        logger.info("spot_position_closed", asset=pos.asset, reason=reason, pnl_usd=float(pnl))
        return pnl

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

        if partial:
            close_size = (pos.size / Decimal("2")).quantize(Decimal("0.000001"))
            pnl = pnl_per_unit * close_size
            pos.size = pos.size - close_size
            pos.tp1_reached = True
            pos.pnl_unrealized = pnl_per_unit * pos.size
        else:
            close_size = pos.size
            pnl = pnl_per_unit * close_size
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
            if pos.stop_loss and price <= pos.stop_loss:
                reason = "stop_loss"
            elif pos.take_profit_2 and price >= pos.take_profit_2:
                reason = "take_profit_2"
            elif pos.take_profit_1 and price >= pos.take_profit_1:
                reason = "take_profit_1"
            # Trailing stop: trascina il livello verso l'alto e chiude se il prezzo ritraccia.
            if reason is None and self.settings.spot_trailing_distance_pct > 0:
                candidate = price * (Decimal("1") - Decimal(str(self.settings.spot_trailing_distance_pct)) / Decimal("100"))
                if pos.trailing_stop is None or candidate > pos.trailing_stop:
                    pos.trailing_stop = candidate
                    pos.updated_at = now
                    session.add(pos)
                if pos.trailing_stop is not None and price <= pos.trailing_stop:
                    reason = "trailing_stop"
            if reason is None and self.settings.spot_time_stop_hours > 0:
                age_hours = (now - pos.opened_at.replace(tzinfo=pos.opened_at.tzinfo or UTC)).total_seconds() / 3600
                if age_hours >= self.settings.spot_time_stop_hours:
                    reason = "time_stop"
            if reason:
                pnl = await self._close_spot_position(session, pos, price, reason, now)
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
                    )
                )

        for pos in perp_positions:
            if pos.status != "open":
                continue
            price = pos.current_price
            is_long = pos.side == "long"
            reason = None
            partial = False

            if pos.stop_loss:
                if (is_long and price <= pos.stop_loss) or (not is_long and price >= pos.stop_loss):
                    reason = "stop_loss"

            if reason is None and pos.tp1_reached and pos.take_profit_2:
                if (is_long and price >= pos.take_profit_2) or (not is_long and price <= pos.take_profit_2):
                    reason = "take_profit_2"

            if reason is None and not pos.tp1_reached and pos.take_profit_1:
                if (is_long and price >= pos.take_profit_1) or (not is_long and price <= pos.take_profit_1):
                    reason = "take_profit_1"
                    partial = True

            # Trailing stop dinamico: trascina il livello in direzione del profitto e chiude la posizione residua.
            if reason is None and pos.trailing_stop is not None:
                dist = PERP_TRAILING_DISTANCE_PCT / Decimal("100")
                if is_long:
                    candidate = price * (Decimal("1") - dist)
                    if candidate > pos.trailing_stop:
                        pos.trailing_stop = candidate
                        pos.updated_at = now
                        session.add(pos)
                    if price <= pos.trailing_stop:
                        reason = "trailing_stop"
                else:
                    candidate = price * (Decimal("1") + dist)
                    if candidate < pos.trailing_stop:
                        pos.trailing_stop = candidate
                        pos.updated_at = now
                        session.add(pos)
                    if price >= pos.trailing_stop:
                        reason = "trailing_stop"

            if reason is None and self.settings.perp_time_stop_hours > 0:
                age_hours = (now - pos.opened_at.replace(tzinfo=pos.opened_at.tzinfo or UTC)).total_seconds() / 3600
                if age_hours >= self.settings.perp_time_stop_hours:
                    reason = "time_stop"

            if reason:
                pnl = await self._close_perp_position(session, pos, price, reason, now, partial=partial)
                exposure = pos.entry_price * pos.size * pos.leverage
                pnl_pct = pnl / exposure * 100 if exposure > 0 else Decimal("0")
                asyncio.create_task(
                    notifier.notify_trade_closed(
                        user_id=user_id,
                        trade_id=f"cls_{pos.position_id}",
                        asset=pos.asset,
                        market="perp",
                        pnl_usd=pnl,
                        pnl_pct=pnl_pct,
                        close_reason=reason,
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

        spot_exposure = sum((p.entry_price * p.size for p in spot_positions), Decimal("0"))
        perp_exposure = sum((p.entry_price * p.size for p in perp_positions), Decimal("0"))
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
        selected_assets = selected_watchlist(self.settings)
        markets = _active_markets(self.settings.markets_enabled)
        scanner_results = []
        for asset in selected_assets:
            if "spot" in markets:
                scanner_results.append(await self.evaluate_spot(_scanner_payload(asset, "spot"), session))
            if "perp" in markets:
                scanner_results.append(await self.evaluate_perp(_scanner_payload(asset, "perp"), session))
        await self._snapshot_portfolio_hourly(session, _now)
        await self._maybe_send_daily_summary(session, _now)
        return {
            "status": "idle" if trade_heartbeat["status"] != "executed" else "heartbeat_trade_executed",
            "reason": "watchlist_empty" if not selected_assets else "watchlist_scanned",
            "markets_enabled": self.settings.markets_enabled,
            "watchlist": selected_assets,
            "scanner_results": [_scanner_summary(result) for result in scanner_results],
            "daily_trade_heartbeat": trade_heartbeat,
        }

    async def _handle_signal(self, signal: dict, session: AsyncSession) -> dict:
        if signal.get("action") == "skip":
            risk_decision = RiskDecision(False, f"signal_skipped:{signal.get('reason') or 'skip'}")
            brain_decision = self.brain._local_fallback(
                signal, risk_decision.__dict__, reason_prefix="no_signal_skip"
            )
            decision = await self._record_decision(session, signal, risk_decision, brain_decision)
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
        if portfolio is None and self.settings.execution_mode == "dry_run":
            portfolio = await _initialise_dry_run_portfolio(session, self.settings)
        spot_positions = await SpotPositionRepository(session).open_for_user(user_id)
        perp_positions = await PerpPositionRepository(session).open_for_user(user_id)
        intent = _intent_from_signal(signal, portfolio_total=Decimal(str(getattr(portfolio, "total_equity_usd", 0) or 0)))
        risk_decision = self.risk.evaluate(
            intent,
            portfolio=portfolio,
            open_spot_positions=spot_positions,
            open_perp_positions=perp_positions,
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
        minutes = self.settings.risk_cooldown_minutes
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

    async def _record_decision(self, session: AsyncSession, signal: dict, risk_decision, brain_decision) -> AgentDecision:
        decision = AgentDecision(
            decision_id=f"dec_{uuid4().hex}",
            user_id=str(self.settings.default_user_id),
            timestamp_utc=datetime.now(UTC),
            asset=signal.get("asset"),
            market=str(signal.get("market", "spot")),
            signal_quality=Decimal(str(signal.get("quality", 0))),
            confidence=brain_decision.confidence,
            action=brain_decision.action,
            reasoning=f"{brain_decision.reasoning}; risk={risk_decision.reason}",
            execution_result=None,
            trade_id=None,
        )
        return await AgentDecisionRepository(session).save(decision)

    async def _execute_or_simulate(self, session: AsyncSession, signal: dict, risk_decision, brain_decision) -> dict:
        size_quote = risk_decision.size_quote * brain_decision.size_multiplier
        if self.settings.execution_mode == "dry_run":
            execution = await self._simulate_trade(session, signal, size_quote)
        elif signal.get("market") == "spot":
            execution = await self._execute_spot(signal, size_quote)
        else:
            execution = await self._execute_perp(signal, size_quote)

        if execution.get("trade_id") and execution.get("status") in {"prepared", "confirmed"}:
            asyncio.create_task(self._notify_trade_opened(signal, risk_decision, execution))
        return execution

    async def _simulate_trade(self, session: AsyncSession, signal: dict, size_quote: Decimal) -> dict:
        now = datetime.now(UTC)
        trade_id = f"dry_{uuid4().hex}"
        price = Decimal(str(signal.get("price", "0")))
        if price <= 0:
            return {"status": "skipped", "reason": "price_unavailable"}
        if signal.get("market") == "perp":
            side = str(signal.get("side") or "long")
            await PerpTradeRepository(session).save(
                PerpTrade(
                    trade_id=trade_id,
                    user_id=str(self.settings.default_user_id),
                    asset=str(signal.get("asset")),
                    side=side,
                    direction="open",
                    size=size_quote / price,
                    price=price,
                    leverage=int(signal.get("leverage") or self.settings.perp_default_leverage),
                    status=ExecutionStatus.PREPARED.value,
                    timestamp_utc=now,
                    venue="dry_run",
                    signal_id=signal.get("signal_id"),
                    notes="dry_run_step6",
                )
            )
            await PerpPositionRepository(session).save(
                PerpPosition(
                    position_id=f"pos_{uuid4().hex}",
                    user_id=str(self.settings.default_user_id),
                    asset=str(signal.get("asset")),
                    side=side,
                    size=size_quote / price,
                    entry_price=price,
                    current_price=price,
                    leverage=int(signal.get("leverage") or self.settings.perp_default_leverage),
                    stop_loss=_optional_decimal(signal.get("stop_loss")),
                    take_profit_1=_optional_decimal(signal.get("take_profit_1")),
                    take_profit_2=_optional_decimal(signal.get("take_profit_2")),
                    trailing_stop=_optional_decimal(signal.get("trailing_stop")),
                    venue="dry_run",
                    open_trade_id=trade_id,
                    opened_at=now,
                    updated_at=now,
                )
            )
            return {"status": "prepared", "mode": "dry_run", "trade_id": trade_id}

        await SpotTradeRepository(session).save(
            SpotTrade(
                trade_id=trade_id,
                user_id=str(self.settings.default_user_id),
                asset=str(signal.get("asset")),
                side="buy",
                amount=size_quote / price,
                price=price,
                amount_quote=size_quote,
                status=ExecutionStatus.PREPARED.value,
                provider="dry_run",
                timestamp_utc=now,
                signal_id=signal.get("signal_id"),
                notes="dry_run_step6",
            )
        )
        await SpotPositionRepository(session).save(
            SpotPosition(
                position_id=f"pos_{uuid4().hex}",
                user_id=str(self.settings.default_user_id),
                asset=str(signal.get("asset")),
                size=size_quote / price,
                entry_price=price,
                current_price=price,
                stop_loss=_optional_decimal(signal.get("stop_loss")),
                take_profit_1=_optional_decimal(signal.get("take_profit_1")),
                trailing_stop=_optional_decimal(signal.get("trailing_stop")),
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
            slippage_pct=Decimal(str(self.settings.risk_max_slippage_pct)),
        )
        return {"status": "prepared", "provider": self.spot_registry.active_name.value, "quote": quote.model_dump()}

    async def _execute_perp(self, signal: dict, size_quote: Decimal) -> dict:
        order = PerpOrder(
            asset=str(signal.get("asset")),
            direction=str(signal.get("side") or "long"),  # type: ignore[arg-type]
            size=size_quote,
            leverage=Decimal(str(signal.get("leverage") or self.settings.perp_default_leverage)),
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
        heartbeat_price = HEARTBEAT_TRADE_PRICE_USD_FALLBACK
        try:
            feed = BinanceKlineFeed()
            candles = await feed.fetch(symbol=f"{HEARTBEAT_TRADE_ASSET}USDT", interval="1m", limit=1, market="spot")
            if candles:
                heartbeat_price = Decimal(str(candles[-1].close))
        except Exception:
            pass
        signal = {
            "signal_id": f"heartbeat_{now.date().isoformat()}",
            "market": "spot",
            "asset": HEARTBEAT_TRADE_ASSET,
            "action": "enter_long",
            "quality": 0.86,
            "confidence": 0.86,
            "price": heartbeat_price,
            "quote_equity": Decimal(str(self.settings.dry_run_capital_usd)),
            "heartbeat_trade": True,
        }
        heartbeat_trade_quote_usd = max(Decimal(str(self.settings.min_trade_size_usd)), Decimal("1"))
        if self.settings.execution_mode == "dry_run":
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
            "mode": self.settings.execution_mode,
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
                is_dry_run=self.settings.execution_mode == "dry_run",
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
            if drawdown >= self.settings.risk_notify_drawdown_pct:
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
