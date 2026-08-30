"""Agent risk management and hard guardrails."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.persistence.models.pnl import PortfolioState
from backend.app.persistence.models.positions import PerpPosition, SpotPosition
from backend.app.schemas.mobile_agent import AgentMobileSettings

logger = get_logger("agent.risk")


class KillSwitchState(StrEnum):
    RUNNING = "running"
    SOFT_STOP = "soft_stop"
    HARD_STOP = "hard_stop"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    size_quote: Decimal = Decimal("0")
    risk_amount_quote: Decimal = Decimal("0")
    exposure_after_pct: Decimal = Decimal("0")
    scaled_for_execution_mode: bool = False


@dataclass(frozen=True)
class SignalIntent:
    asset: str
    market: str
    side: str
    price: Decimal
    stop_loss: Decimal | None
    quality: Decimal
    quote_equity: Decimal
    liquidity_usd: Decimal | None = None


class RiskManager:
    """Fail-closed risk manager for Spot and Perp agent decisions."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.kill_switch = KillSwitchState.RUNNING
        self.degraded_reasons: set[str] = set()
        self.eligible_symbols = {token.upper() for token in self.settings.eligible_tokens}
        logger.info(
            "risk_manager_eligible_tokens_loaded",
            eligible_token_count=len(self.settings.eligible_tokens),
            eligible_symbol_count=len(self.eligible_symbols),
        )

    def set_kill_switch(self, state: KillSwitchState) -> None:
        self.kill_switch = state

    def mark_degraded(self, reason: str) -> None:
        self.degraded_reasons.add(reason)
        if self.kill_switch == KillSwitchState.RUNNING:
            self.kill_switch = KillSwitchState.DEGRADED

    def clear_degraded(self, reason: str | None = None) -> None:
        if reason is None:
            self.degraded_reasons.clear()
        else:
            self.degraded_reasons.discard(reason)
        if not self.degraded_reasons and self.kill_switch == KillSwitchState.DEGRADED:
            self.kill_switch = KillSwitchState.RUNNING

    def evaluate(
        self,
        intent: SignalIntent,
        *,
        portfolio: PortfolioState | None,
        open_spot_positions: list[SpotPosition],
        open_perp_positions: list[PerpPosition],
        ms: AgentMobileSettings | None = None,
    ) -> RiskDecision:
        if self.kill_switch == KillSwitchState.HARD_STOP:
            return RiskDecision(False, "hard_stop_enabled")
        if self.kill_switch in {KillSwitchState.SOFT_STOP, KillSwitchState.DEGRADED}:
            return RiskDecision(False, self.kill_switch.value)
        if intent.asset.upper() not in self.eligible_symbols:
            return RiskDecision(False, "asset_not_in_eligible_universe")
        # D25: capital moved into the "Bank" reserve is carved out of the equity
        # the agent may risk. Non-reserve users have a 0 counter → no change.
        reserve_offset = (
            Decimal(str(getattr(portfolio, "reserve_transferred_net_usd", 0) or 0))
            if portfolio is not None
            else Decimal("0")
        )
        if portfolio is not None:
            tradable_equity = Decimal(portfolio.total_equity_usd) - reserve_offset
            if tradable_equity <= Decimal(str(self.settings.min_portfolio_value_usd)):
                return RiskDecision(False, "portfolio_floor_guard")
            # drawdown_pct e' memorizzato come valore POSITIVO (entita' del calo dal picco),
            # mentre risk_max_drawdown_pct e' negativo (es. -15). Confronto su valore assoluto.
            drawdown_cap = abs(Decimal(str(ms.drawdown_cap_pct if ms else self.settings.risk_max_drawdown_pct)))
            if Decimal(portfolio.drawdown_pct) >= drawdown_cap:
                return RiskDecision(False, "drawdown_cap_guard")
            # daily_loss_limit_used_pct e' negativo in perdita (es. -8); cap negativo (es. -8).
            daily_cap = Decimal(str(ms.daily_loss_limit_pct if ms else self.settings.risk_daily_loss_limit_pct))
            if Decimal(portfolio.daily_loss_limit_used_pct) <= daily_cap:
                return RiskDecision(False, "daily_loss_limit_guard")
        liquidity_floor = Decimal(str(ms.min_pool_liquidity_usd if ms else self.settings.risk_min_pool_liquidity_usd))
        if intent.liquidity_usd is not None and intent.liquidity_usd < liquidity_floor:
            return RiskDecision(False, "liquidity_guard")

        # Dedup per-asset: una sola posizione aperta per asset (spot o perp).
        asset_upper = intent.asset.upper()
        open_assets = {p.asset.upper() for p in open_spot_positions} | {p.asset.upper() for p in open_perp_positions}
        if asset_upper in open_assets:
            return RiskDecision(False, "asset_already_open")

        # Limiti posizioni e size separati per mercato
        is_perp = intent.market == "perp"
        if ms is not None:
            cap_pct = ms.perp_capital_per_trade_pct if is_perp else ms.spot_capital_per_trade_pct
            per_trade_pct = ms.perp_per_trade_pct if is_perp else ms.spot_per_trade_pct
            max_open = ms.perp_max_open_positions if is_perp else ms.spot_max_open_positions
            max_exposure = ms.perp_max_exposure_pct if is_perp else ms.spot_max_exposure_pct
        else:
            cap_pct = self.settings.risk_capital_per_trade_pct
            per_trade_pct = self.settings.risk_per_trade_pct
            max_open = self.settings.risk_max_open_positions
            max_exposure = self.settings.risk_max_total_exposure_pct

        market_open = len(open_perp_positions) if is_perp else len(open_spot_positions)
        if market_open >= max_open:
            return RiskDecision(False, "max_open_positions_guard")

        equity = intent.quote_equity
        if equity <= Decimal("0"):
            equity = Decimal(portfolio.total_equity_usd) if portfolio is not None else Decimal("0")
        equity = max(Decimal("0"), equity - reserve_offset)  # D25: size on tradable equity
        if equity <= Decimal("0"):
            return RiskDecision(False, "portfolio_equity_unavailable")

        nominal_size = equity * Decimal(str(cap_pct)) / Decimal("100")
        risk_size = nominal_size
        # La size si adatta alla distanza dello stop; lo stop NON si stringe per rientrare nel rischio.
        risk_amount = equity * Decimal(str(per_trade_pct)) / Decimal("100")
        if intent.stop_loss is not None and intent.price > Decimal("0"):
            stop_distance_pct = abs(intent.price - intent.stop_loss) / intent.price
            # Filtro volatilità assoluta (solo spot): salta gli ingressi il cui stop è
            # troppo largo in %. Prende i micro-cap ad ATR strutturalmente mostruoso che
            # passano liquidità e spike-filter ma chiudono a -5/-12%. Per-trade, non blacklist.
            if not is_perp:
                if ms is not None:
                    vol_filter_on = ms.spot_max_stop_distance_filter_enabled
                    vol_max_pct = ms.spot_max_stop_distance_pct
                else:
                    vol_filter_on = getattr(self.settings, "spot_max_stop_distance_filter_enabled", True)
                    vol_max_pct = getattr(self.settings, "spot_max_stop_distance_pct", 4.0)
                if vol_filter_on and stop_distance_pct * Decimal("100") > Decimal(str(vol_max_pct)):
                    return RiskDecision(
                        False,
                        "max_stop_distance_guard",
                        exposure_after_pct=stop_distance_pct * Decimal("100"),
                    )
            if stop_distance_pct > 0:
                risk_size = min(nominal_size, risk_amount / stop_distance_pct)
        if is_perp and ms is not None and ms.perp_fixed_margin_enabled:
            risk_size = Decimal(str(ms.perp_fixed_margin_usd))

        # Esposizione calcolata per-mercato: spot = nozionale, perp = margine (nozionale/leva)
        if equity > Decimal("0"):
            if is_perp:
                market_exposure = sum(
                    p.entry_price * p.size / Decimal(max(int(p.leverage or 1), 1))
                    for p in open_perp_positions
                )
            else:
                market_exposure = sum(p.entry_price * p.size for p in open_spot_positions)
            current_exposure_pct = market_exposure / equity * Decimal("100")
        else:
            current_exposure_pct = Decimal("0")

        added_exposure_pct = risk_size / equity * Decimal("100")
        exposure_after = current_exposure_pct + added_exposure_pct
        if exposure_after > Decimal(str(max_exposure)):
            return RiskDecision(False, "max_total_exposure_guard", exposure_after_pct=exposure_after)

        scaled = False
        if self.settings.execution_mode == "live":
            scale = Decimal(str(self.settings.test_scaling_pct)) / Decimal("100")
            risk_size *= scale
            scaled = True
        elif self.settings.execution_mode != "dry_run":
            return RiskDecision(False, "unsupported_execution_mode")

        if risk_size <= Decimal("0"):
            return RiskDecision(False, "computed_size_zero")
        if risk_size < Decimal(str(self.settings.min_trade_size_usd)):
            return RiskDecision(False, "below_minimum_trade_size", size_quote=risk_size)

        return RiskDecision(
            True,
            "risk_approved",
            size_quote=risk_size,
            risk_amount_quote=min(risk_amount, risk_size),
            exposure_after_pct=exposure_after,
            scaled_for_execution_mode=scaled,
        )
