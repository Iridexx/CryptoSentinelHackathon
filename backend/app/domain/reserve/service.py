"""ReserveService — business logic for the "Bank" store-of-value reserve.

Two-phase model (plans/Plan_Reserve.md D29): profits are *swept* into a USDC
sleeve cheaply and often, then *deployed* into the hard assets in batches. Every
transfer / sweep / deploy lands in a single DB transaction (holdings +
``reserve_transactions`` + ``portfolio_state`` counters).

R3 = simulated execution only; ``ReserveExecutor`` refuses the live branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import Settings, get_settings
from backend.app.core.logging import get_logger
from backend.app.domain.reserve.executor import ReserveExecutor
from backend.app.domain.reserve.settings import load_reserve_settings
from backend.app.persistence.models.reserve import ReserveSnapshot, ReserveTransaction
from backend.app.persistence.repositories.pnl import PnlRepository
from backend.app.persistence.repositories.positions import (
    PerpPositionRepository,
    SpotPositionRepository,
)
from backend.app.persistence.repositories.reserve import ReserveRepository
from backend.app.persistence.repositories.trades import (
    PerpTradeRepository,
    SpotTradeRepository,
)
from backend.app.schemas.reserve import (
    ReserveHoldingView,
    ReserveSettings,
    ReserveView,
)

logger = get_logger("domain.reserve.service")

_ZERO = Decimal("0")
_CENT = Decimal("0.01")


def _cents(value: Decimal) -> Decimal:
    """Round a USD amount down to whole cents (avoids sub-cent rounding noise)."""
    return value.quantize(_CENT, rounding=ROUND_DOWN)


class ReserveError(RuntimeError):
    """A reserve operation was rejected (validation / guard / cooldown)."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _Equity:
    initial: Decimal
    total: Decimal
    transferred_net: Decimal
    tradable: Decimal
    guard_blocked: bool

    @property
    def deposit_capacity(self) -> Decimal:
        return max(_ZERO, self.tradable - self.initial)


@dataclass(frozen=True, slots=True)
class DeployResult:
    bought: dict[str, Decimal]   # asset -> usd spent
    cash_left: Decimal
    skipped: bool
    reason: str


class ReserveService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        executor: ReserveExecutor,
        settings: Settings | None = None,
        now_fn=lambda: datetime.now(UTC),
    ) -> None:
        self._session = session
        self._executor = executor
        self._settings = settings or get_settings()
        self._now = now_fn
        self._repo = ReserveRepository(session)
        self._pnl = PnlRepository(session)
        self._spot_trades = SpotTradeRepository(session)
        self._perp_trades = PerpTradeRepository(session)
        self._spot_pos = SpotPositionRepository(session)
        self._perp_pos = PerpPositionRepository(session)

    # ── settings ─────────────────────────────────────────────────────────────

    def _cfg(self, user_id: str) -> ReserveSettings:
        return load_reserve_settings(user_id, settings=self._settings).settings

    def _target_weights(self, cfg: ReserveSettings) -> dict[str, Decimal]:
        return {w.symbol: Decimal(str(w.weight_pct)) for w in cfg.target_weights}

    # ── equity ───────────────────────────────────────────────────────────────

    async def _equity(self, user_id: str) -> _Equity:
        portfolio = await self._pnl.get_portfolio(user_id)
        fields = await self._repo.get_reserve_fields(user_id)
        transferred_net = Decimal(str(fields["reserve_transferred_net_usd"]))

        if portfolio is None:
            initial = Decimal(str(self._settings.dry_run_capital_usd))
        else:
            initial = Decimal(str(portfolio.initial_equity_usd))

        realized = await self._spot_trades.sum_realized_pnl(user_id)
        realized += await self._perp_trades.sum_realized_pnl(user_id)

        unrealized = _ZERO
        for p in await self._spot_pos.open_for_user(user_id):
            unrealized += Decimal(str(p.pnl_unrealized or 0))
        for p in await self._perp_pos.open_for_user(user_id):
            unrealized += Decimal(str(p.pnl_unrealized or 0))

        total = initial + realized + unrealized
        tradable = total - transferred_net

        guard_blocked = False
        if portfolio is not None:
            cap = abs(Decimal(str(self._settings.risk_max_drawdown_pct)))
            daily_cap = Decimal(str(self._settings.risk_daily_loss_limit_pct))
            floor = Decimal(str(self._settings.min_portfolio_value_usd))
            guard_blocked = (
                tradable <= floor
                or Decimal(str(portfolio.drawdown_pct)) >= cap
                or Decimal(str(portfolio.daily_loss_limit_used_pct)) <= daily_cap
            )

        return _Equity(initial, total, transferred_net, tradable, guard_blocked)

    # ── valuation ────────────────────────────────────────────────────────────

    async def _asset_mtm(self, user_id: str) -> tuple[dict[str, dict], Decimal]:
        """Per-asset {qty, price, value, avg_cost} and the total asset value."""
        out: dict[str, dict] = {}
        total = _ZERO
        for h in await self._repo.list_holdings(user_id):
            qty = Decimal(str(h.quantity))
            if qty <= 0:
                continue
            price = await self._executor.price(h.asset)
            value = qty * price
            out[h.asset] = {
                "qty": qty,
                "price": price,
                "value": value,
                "avg_cost": Decimal(str(h.avg_cost_usd)),
            }
            total += value
        return out, total

    # ── frozen toggle ────────────────────────────────────────────────────────

    async def set_frozen(self, user_id: str, frozen: bool) -> None:
        await self._ensure_portfolio(user_id)
        await self._repo.set_reserve_fields(user_id, now=self._now(), reserve_frozen=frozen)
        await self._repo.commit()

    async def _ensure_portfolio(self, user_id: str) -> None:
        if await self._pnl.get_portfolio(user_id) is None:
            base = Decimal(str(self._settings.dry_run_capital_usd))
            await self._pnl.upsert_portfolio(
                user_id, total_equity_usd=base, initial_equity_usd=base
            )

    async def _fields(self, user_id: str) -> dict:
        return await self._repo.get_reserve_fields(user_id)

    # ── transfer in ──────────────────────────────────────────────────────────

    async def transfer_in(self, user_id: str, amount_usd: Decimal) -> ReserveView:
        cfg = self._cfg(user_id)
        await self._ensure_portfolio(user_id)
        fields = await self._fields(user_id)
        if fields["reserve_frozen"]:
            raise ReserveError("frozen", "the reserve is frozen")

        eq = await self._equity(user_id)
        effective = min(Decimal(str(amount_usd)), eq.deposit_capacity)
        if effective <= 0:
            raise ReserveError("no_profit_available", "no profit above the initial capital")
        if effective < Decimal(str(cfg.min_transfer_usd)):
            raise ReserveError("below_min_transfer", f"below the ${cfg.min_transfer_usd} minimum")

        now = self._now()
        await self._repo.add_transaction(
            ReserveTransaction(
                user_id=user_id, type="transfer_in", value_usd=effective,
                cash_usd_delta=effective, created_at=now, note="manual transfer_in",
            )
        )
        await self._repo.set_reserve_fields(
            user_id,
            now=now,
            reserve_cash_usd=Decimal(str(fields["reserve_cash_usd"])) + effective,
            reserve_transferred_net_usd=eq.transferred_net + effective,
        )
        await self._repo.commit()

        await self.deploy(user_id, reason="transfer_in")
        return await self.get_view(user_id)

    # ── profit sweep (§8bis) ─────────────────────────────────────────────────

    async def run_profit_sweep(self, user_id: str) -> Decimal:
        """Move a slice of new realised trading profit into the USDC sleeve. Returns swept USD."""
        cfg = self._cfg(user_id)
        if not cfg.sweep_enabled or cfg.sweep_pct <= 0:
            return _ZERO
        fields = await self._fields(user_id)
        if fields["reserve_frozen"]:
            return _ZERO
        eq = await self._equity(user_id)
        if eq.guard_blocked:
            return _ZERO

        realized = await self._spot_trades.sum_realized_pnl(user_id)
        realized += await self._perp_trades.sum_realized_pnl(user_id)
        hwm = Decimal(str(fields["last_swept_realized_pnl_usd"]))
        delta = realized - hwm
        if delta <= 0:
            return _ZERO

        rate = Decimal(str(cfg.sweep_pct)) / Decimal("100")
        amount = delta * rate
        amount = min(amount, eq.deposit_capacity)
        if amount < Decimal(str(cfg.min_transfer_usd)):
            return _ZERO

        # Advance the high-water mark only by the profit actually consumed.
        hwm_advance = amount / rate
        now = self._now()
        await self._repo.add_transaction(
            ReserveTransaction(
                user_id=user_id, type="sweep", value_usd=amount,
                cash_usd_delta=amount, created_at=now, note="profit_sweep",
            )
        )
        await self._repo.set_reserve_fields(
            user_id,
            now=now,
            reserve_cash_usd=Decimal(str(fields["reserve_cash_usd"])) + amount,
            reserve_transferred_net_usd=eq.transferred_net + amount,
            last_swept_realized_pnl_usd=hwm + hwm_advance,
        )
        await self._repo.commit()
        await self.deploy(user_id, reason="sweep")
        return amount

    # ── deploy (§8ter) ───────────────────────────────────────────────────────

    async def deploy(self, user_id: str, *, force: bool = False, reason: str = "scheduler") -> DeployResult:
        cfg = self._cfg(user_id)
        fields = await self._fields(user_id)
        if fields["reserve_frozen"]:
            return DeployResult({}, Decimal(str(fields["reserve_cash_usd"])), True, "frozen")

        cash = Decimal(str(fields["reserve_cash_usd"]))
        min_buy = Decimal(str(self._settings.reserve.deploy_min_buy_usd))
        if cash < min_buy:
            return DeployResult({}, cash, True, "cash_below_min_buy")

        now = self._now()
        last_deploy = fields["last_deploy_at"]
        time_trigger = last_deploy is None or (
            _as_aware(now) - _as_aware(last_deploy) >= timedelta(days=cfg.deploy_interval_days)
        )
        cash_trigger = cash >= Decimal(str(cfg.deploy_min_cash_usd))
        if not (force or cash_trigger or time_trigger):
            return DeployResult({}, cash, True, "no_trigger")

        weights = self._target_weights(cfg)
        mtm, asset_total = await self._asset_mtm(user_id)
        base = _cents(asset_total + cash)
        cash = _cents(cash)

        gaps: list[tuple[str, Decimal, Decimal]] = []  # (asset, gap_usd, gap_rel)
        for asset, w in weights.items():
            if w <= 0:
                continue
            target = _cents(w / Decimal("100") * base)
            current = _cents(mtm.get(asset, {}).get("value", _ZERO))
            gap = max(_ZERO, target - current)
            if gap <= 0 or target <= 0:
                continue
            gaps.append((asset, gap, gap / target))
        if not gaps:
            return DeployResult({}, cash, True, "all_at_target")

        # Highest gap_rel first (tie-break: larger target weight), then fill each
        # asset up to its own gap from the remaining cash. No proportional
        # dilution: a tiny gap on one asset never starves a genuine underweight.
        gaps.sort(key=lambda g: (g[2], weights[g[0]]), reverse=True)

        allocations: dict[str, Decimal] = {}
        remaining = cash
        for asset, gap, _rel in gaps:
            want = _cents(min(gap, remaining))
            if want >= min_buy:
                allocations[asset] = want
                remaining -= want

        if not allocations and (force or time_trigger):
            # anti-starvation: buy the top-priority asset at least ``min_buy``
            # (bounded overshoot of its target), capped at the available cash.
            top_asset, top_gap, _ = gaps[0]
            if cash >= min_buy:
                allocations[top_asset] = _cents(min(cash, max(min_buy, top_gap)))

        if not allocations:
            return DeployResult({}, cash, True, "below_min_buy")

        bought: dict[str, Decimal] = {}
        spent = _ZERO
        for asset, usd in allocations.items():
            fill = await self._executor.buy(asset, usd)
            holding = await self._repo.get_holding(user_id, asset)
            old_qty = Decimal(str(holding.quantity)) if holding else _ZERO
            old_avg = Decimal(str(holding.avg_cost_usd)) if holding else _ZERO
            new_qty = old_qty + fill.quantity
            new_avg = (old_qty * old_avg + fill.quantity * fill.price_usd) / new_qty
            await self._repo.upsert_holding(
                user_id, asset, quantity=new_qty, avg_cost_usd=new_avg, now=now
            )
            await self._repo.add_transaction(
                ReserveTransaction(
                    user_id=user_id, type="deploy_buy", asset=asset,
                    quantity=fill.quantity, price_usd=fill.price_usd,
                    value_usd=fill.net_usd, fee_usd=fill.fee_usd,
                    cash_usd_delta=-fill.gross_usd, created_at=now, note=reason,
                )
            )
            bought[asset] = usd
            spent += usd

        cash_left = cash - spent
        await self._repo.set_reserve_fields(
            user_id, now=now, reserve_cash_usd=cash_left, last_deploy_at=now
        )
        await self._repo.commit()
        logger.info("reserve_deploy", user_id=user_id, reason=reason, bought=len(bought), spent=str(spent))
        return DeployResult(bought, cash_left, False, reason)

    # ── transfer out ─────────────────────────────────────────────────────────

    async def transfer_out(self, user_id: str, amount_usd: Decimal) -> ReserveView:
        cfg = self._cfg(user_id)
        await self._ensure_portfolio(user_id)
        fields = await self._fields(user_id)
        now = self._now()

        eq = await self._equity(user_id)
        if cfg.block_withdrawal_during_drawdown_guard and eq.guard_blocked:
            raise ReserveError("drawdown_guard", "withdrawals blocked while the drawdown guard is active")

        cooldown = timedelta(minutes=cfg.withdrawal_cooldown_minutes)
        last_out = await self._last_transfer_out_at(user_id)
        if last_out is not None and _as_aware(now) - _as_aware(last_out) < cooldown:
            raise ReserveError("cooldown", "withdrawal cooldown still active")

        cash = Decimal(str(fields["reserve_cash_usd"]))
        mtm, asset_total = await self._asset_mtm(user_id)
        reserve_value = cash + asset_total
        want = min(Decimal(str(amount_usd)), reserve_value)
        if want <= 0:
            raise ReserveError("empty", "the reserve is empty")

        from_cash = min(want, cash)
        remaining = want - from_cash
        total_fee = _ZERO
        net_from_assets = _ZERO
        note_parts = [f"cash ${from_cash:.2f}"] if from_cash > 0 else []

        if remaining > 0 and asset_total > 0:
            for asset, info in mtm.items():
                slice_usd = remaining * info["value"] / asset_total
                if slice_usd <= 0:
                    continue
                sell_qty = min(info["qty"], slice_usd / info["price"])
                fill = await self._executor.sell(asset, sell_qty)
                total_fee += fill.fee_usd
                net_from_assets += fill.net_usd
                new_qty = info["qty"] - fill.quantity
                await self._repo.upsert_holding(
                    user_id, asset,
                    quantity=new_qty if new_qty > Decimal("1e-18") else _ZERO,
                    avg_cost_usd=info["avg_cost"], now=now,
                )
                note_parts.append(f"{asset} ${fill.net_usd:.2f}")

        credited = from_cash + net_from_assets  # what the trading book receives
        await self._repo.add_transaction(
            ReserveTransaction(
                user_id=user_id, type="transfer_out", value_usd=want, fee_usd=total_fee,
                cash_usd_delta=-from_cash, created_at=now, note="; ".join(note_parts) or "transfer_out",
            )
        )
        await self._repo.set_reserve_fields(
            user_id,
            now=now,
            reserve_cash_usd=cash - from_cash,
            reserve_transferred_net_usd=eq.transferred_net - credited,
        )
        await self._repo.commit()
        return await self.get_view(user_id)

    async def _last_transfer_out_at(self, user_id: str) -> datetime | None:
        for txn in await self._repo.list_transactions(user_id, limit=50):
            if txn.type == "transfer_out":
                return txn.created_at
        return None

    # ── target weights ───────────────────────────────────────────────────────

    async def set_target_weights(self, user_id: str, weights: dict[str, float]) -> ReserveView:
        from backend.app.domain.reserve.settings import save_reserve_settings

        current = load_reserve_settings(user_id, settings=self._settings).settings
        updated = current.model_copy(
            update={
                "target_weights": [
                    {"symbol": s, "weight_pct": w} for s, w in weights.items()
                ]
            }
        )
        save_reserve_settings(user_id, updated, settings=self._settings)
        return await self.get_view(user_id)

    # ── rebalance (sell side, rare) ──────────────────────────────────────────

    async def rebalance(self, user_id: str, *, dry_run: bool = False) -> dict:
        """Sell whatever is overweight beyond ``rebalance_band_pct`` back to target.

        The proceeds land in ``reserve_cash_usd`` and are redeployed by ``deploy``.
        """
        cfg = self._cfg(user_id)
        fields = await self._fields(user_id)
        if fields["reserve_frozen"]:
            raise ReserveError("frozen", "the reserve is frozen")

        band = Decimal(str(self._settings.reserve.rebalance_band_pct))
        weights = self._target_weights(cfg)
        mtm, asset_total = await self._asset_mtm(user_id)
        cash = Decimal(str(fields["reserve_cash_usd"]))
        base = asset_total + cash
        if base <= 0:
            return {"sold": {}, "dry_run": dry_run}

        plan: dict[str, Decimal] = {}
        for asset, info in mtm.items():
            target = weights.get(asset, _ZERO) / Decimal("100") * base
            over = info["value"] - target
            drift = over / target * Decimal("100") if target > 0 else _ZERO
            if drift > band:
                plan[asset] = over  # USD to sell back

        if dry_run or not plan:
            return {"sold": {k: str(v) for k, v in plan.items()}, "dry_run": dry_run}

        now = self._now()
        proceeds = _ZERO
        for asset, over_usd in plan.items():
            info = mtm[asset]
            sell_qty = min(info["qty"], over_usd / info["price"])
            fill = await self._executor.sell(asset, sell_qty)
            proceeds += fill.net_usd
            await self._repo.upsert_holding(
                user_id, asset, quantity=info["qty"] - fill.quantity,
                avg_cost_usd=info["avg_cost"], now=now,
            )
            await self._repo.add_transaction(
                ReserveTransaction(
                    user_id=user_id, type="rebalance_sell", asset=asset,
                    quantity=fill.quantity, price_usd=fill.price_usd,
                    value_usd=fill.net_usd, fee_usd=fill.fee_usd,
                    cash_usd_delta=fill.net_usd, created_at=now, note="rebalance",
                )
            )
        await self._repo.set_reserve_fields(user_id, now=now, reserve_cash_usd=cash + proceeds)
        await self._repo.commit()
        await self.deploy(user_id, force=True, reason="rebalance")
        return {"sold": {k: str(v) for k, v in plan.items()}, "dry_run": False}

    # ── valuation snapshot ───────────────────────────────────────────────────

    async def snapshot(self, user_id: str) -> ReserveSnapshot | None:
        fields = await self._fields(user_id)
        cash = Decimal(str(fields["reserve_cash_usd"]))
        mtm, asset_total = await self._asset_mtm(user_id)
        if cash <= 0 and asset_total <= 0:
            return None
        cost_basis = Decimal(str(fields["reserve_transferred_net_usd"]))
        value = cash + asset_total
        fees = await self._repo.sum_fees(user_id)
        holdings_json = _dumps(
            [
                {
                    "asset": a,
                    "qty": str(i["qty"]),
                    "price_usd": str(i["price"]),
                    "value_usd": str(i["value"]),
                    "weight_pct": float(i["value"] / asset_total * 100) if asset_total > 0 else 0.0,
                }
                for a, i in mtm.items()
            ]
        )
        return await self._repo.save_snapshot(
            ReserveSnapshot(
                user_id=user_id, timestamp_utc=self._now(), total_value_usd=value,
                cash_usd=cash, cost_basis_usd=cost_basis, pnl_usd=value - cost_basis,
                fees_cumulative_usd=fees, holdings_json=holdings_json,
            )
        )

    async def valuate(self, user_id: str) -> Decimal:
        """Current mark-to-market value of the reserve (cash + assets)."""
        fields = await self._fields(user_id)
        _mtm, asset_total = await self._asset_mtm(user_id)
        return Decimal(str(fields["reserve_cash_usd"])) + asset_total

    # ── view ─────────────────────────────────────────────────────────────────

    async def get_view(self, user_id: str) -> ReserveView:
        cfg = self._cfg(user_id)
        fields = await self._fields(user_id)
        eq = await self._equity(user_id)
        weights = self._target_weights(cfg)
        drift_band = Decimal(str(cfg.drift_band_pct))

        cash = Decimal(str(fields["reserve_cash_usd"]))
        mtm, asset_total = await self._asset_mtm(user_id)
        value = cash + asset_total
        cost_basis = Decimal(str(fields["reserve_transferred_net_usd"]))
        pnl = value - cost_basis
        fees = await self._repo.sum_fees(user_id)
        total_portfolio = eq.tradable + value

        holdings: list[ReserveHoldingView] = []
        for asset, w in weights.items():
            info = mtm.get(asset)
            qty = info["qty"] if info else _ZERO
            price = info["price"] if info else _ZERO
            aval = info["value"] if info else _ZERO
            avg = info["avg_cost"] if info else _ZERO
            weight_pct = float(aval / asset_total * 100) if asset_total > 0 else 0.0
            holdings.append(
                ReserveHoldingView(
                    asset=asset, quantity=qty, price_usd=price, value_usd=aval,
                    avg_cost_usd=avg, pnl_usd=(price - avg) * qty,
                    weight_pct=weight_pct, target_weight_pct=float(w),
                    off_target=abs(Decimal(str(weight_pct)) - w) > drift_band,
                )
            )

        last_deploy = fields["last_deploy_at"]
        next_deploy = (
            _as_aware(last_deploy) + timedelta(days=cfg.deploy_interval_days)
            if last_deploy is not None
            else None
        )
        last_out = await self._last_transfer_out_at(user_id)
        withdrawal_at = (
            _as_aware(last_out) + timedelta(minutes=cfg.withdrawal_cooldown_minutes)
            if last_out is not None
            else None
        )

        return ReserveView(
            enabled=cfg.enabled,
            frozen=bool(fields["reserve_frozen"]),
            value_usd=value,
            cash_usd=cash,
            cost_basis_usd=cost_basis,
            pnl_usd=pnl,
            pnl_pct=float(pnl / cost_basis * 100) if cost_basis > 0 else 0.0,
            fees_total_usd=fees,
            portfolio_pct=float(value / total_portfolio * 100) if total_portfolio > 0 else 0.0,
            deposit_capacity_usd=eq.deposit_capacity,
            tradable_equity_usd=eq.tradable,
            total_portfolio_equity_usd=total_portfolio,
            next_deploy_at=next_deploy,
            withdrawal_available_at=withdrawal_at,
            holdings=holdings,
            updated_at=self._now(),
        )


def _as_aware(dt: datetime) -> datetime:
    """SQLite reads datetimes back tz-naive; treat naive as UTC."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _dumps(obj) -> str:
    import json

    return json.dumps(obj)
