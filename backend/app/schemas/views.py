"""API response schemas for the dashboard Spot / Perp / Global views."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class SpotPositionView(BaseModel):
    position_id: str
    asset: str
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    pnl_unrealized: Decimal
    pnl_pct: str | None = None
    stop_loss: Decimal | None = None
    take_profit_1: Decimal | None = None
    take_profit_2: Decimal | None = None
    status: str
    opened_at: str


class SpotTradeView(BaseModel):
    trade_id: str
    asset: str
    side: str
    amount: Decimal
    price: Decimal
    pnl_usd: str | None = None
    pnl_pct: str | None = None
    entry_price: Decimal | None = None
    current_or_exit_price: Decimal | None = None
    status: str
    close_reason: str | None = None
    tx_hash: str | None = None
    timestamp_utc: str
    block_timestamp_utc: str | None = None
    is_simulated: bool = False


class SpotView(BaseModel):
    open_positions: list[SpotPositionView]
    history: list[SpotTradeView]
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal
    win_rate_pct: float
    trade_count: int


class PerpPositionView(BaseModel):
    position_id: str
    asset: str
    side: str
    size: Decimal
    entry_price: Decimal
    current_price: Decimal
    leverage: int
    pnl_unrealized: Decimal
    pnl_pct: str | None = None
    stop_loss: Decimal | None = None
    take_profit_1: Decimal | None = None
    take_profit_2: Decimal | None = None
    liquidation_price: Decimal | None = None
    funding_rate: Decimal | None = None
    status: str
    opened_at: str


class PerpTradeView(BaseModel):
    trade_id: str
    asset: str
    side: str
    direction: str
    size: Decimal
    price: Decimal
    pnl_usd: str | None = None
    pnl_pct: str | None = None
    entry_price: Decimal | None = None
    current_or_exit_price: Decimal | None = None
    leverage: int
    status: str
    close_reason: str | None = None
    tx_hash: str | None = None
    timestamp_utc: str
    block_timestamp_utc: str | None = None
    is_simulated: bool = False


class PerpView(BaseModel):
    open_positions: list[PerpPositionView]
    history: list[PerpTradeView]
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal
    win_rate_pct: float
    trade_count: int


class ClaudeUsageView(BaseModel):
    call_count: int
    input_tokens: int
    output_tokens: int
    total_cost_usd: float
    budget_usd: float
    budget_pct: float


class PnlPoint(BaseModel):
    timestamp_utc: str
    total_equity_usd: Decimal
    drawdown_pct: Decimal


class GlobalView(BaseModel):
    total_equity_usd: Decimal
    initial_equity_usd: Decimal
    pnl_total_usd: Decimal
    pnl_total_pct: float
    realized_pnl_usd: Decimal
    unrealized_pnl_usd: Decimal
    drawdown_pct: Decimal
    max_drawdown_pct: Decimal
    sharpe_status: str = "insufficient_data"
    sharpe_ratio: str | None = None
    drawdown_cap_pct: float
    exposure_pct: Decimal
    spot_exposure_usd: Decimal = Decimal("0")
    perp_exposure_usd: Decimal = Decimal("0")
    daily_pnl_usd: Decimal
    agent_status: str
    trades_today: int
    open_spot_positions: int
    open_perp_positions: int
    pnl_history: list[PnlPoint]
