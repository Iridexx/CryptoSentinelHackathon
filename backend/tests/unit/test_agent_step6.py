"""Step 6 agent brain, signal and risk regressions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.agent.brain import ClaudeMetaController
from backend.app.agent.risk import RiskManager, SignalIntent
from backend.app.agent.service import AgentService
from backend.app.agent.signals.common.indicators import Candle
from backend.app.agent.signals.perp import binance_klines
from backend.app.agent.signals.perp.binance_klines import BinanceKlineCacheEntry, clear_kline_cache
from backend.app.agent.signals.perp.volume_profile import VolumeProfileSignal
from backend.app.agent.signals.spot.momentum import SpotMomentumSignal
from backend.app.persistence.repositories.decisions import AgentDecisionRepository
from backend.app.persistence.repositories.trades import SpotTradeRepository
from backend.app.persistence.sync_database import (
    create_all_sync,
    init_sync_db,
    reset_sync_db,
)
from backend.app.persistence.database import close_db, get_session_factory, init_db


USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
async def db(tmp_path: Path):
    reset_sync_db()
    await init_db(f"sqlite+aiosqlite:///{tmp_path / 'agent.db'}")
    init_sync_db(f"sqlite:///{tmp_path / 'agent.db'}")
    create_all_sync()
    yield
    await close_db()
    reset_sync_db()


def settings(**overrides):
    base = dict(
        default_user_id=USER_ID,
        eligible_tokens=["BTC"] + [f"TOKEN_{i}" for i in range(148)],
        execution_mode="dry_run",
        agent_mode="conservative",
        markets_enabled="both",
        anthropic_api_key=None,
        anthropic_model="claude-test",
        anthropic_max_tokens=512,
        risk_capital_per_trade_pct=6.0,
        risk_max_open_positions=3,
        risk_max_total_exposure_pct=30.0,
        risk_daily_loss_limit_pct=-8.0,
        risk_max_drawdown_pct=-15.0,
        risk_min_pool_liquidity_usd=50000.0,
        min_portfolio_value_usd=5.0,
        test_scaling_pct=10.0,
        spot_confidence_threshold=0.70,
        spot_volatility_trigger_pct=2.0,
        spot_relative_volume_threshold=1.5,
        spot_atr_stop_multiplier=1.5,
        spot_trailing_distance_pct=2.0,
        spot_partial_take_profit_pct=5.0,
        spot_time_stop_hours=6,
        spot_vwap_atr_extension_limit=10.0,
        spot_rsi_weight_pct=15.0,
        spot_trend_structure_weight_pct=30.0,
        spot_relative_volume_weight_pct=30.0,
        spot_btc_context_weight_pct=15.0,
        spot_sentiment_weight_pct=10.0,
        perp_direction_mode="long_short",
        perp_value_area_pct=68.0,
        perp_atr_stop_multiplier=0.5,
        perp_time_stop_hours=8,
        perp_dynamic_leverage_enabled=True,
        perp_min_volume_profile_liquidity_usd=100.0,
        perp_default_leverage=2,
        perp_max_leverage=5,
        perp_volume_profile_window_hours=24,
        perp_volume_profile_candle_minutes=5,
        binance_futures_base_url="https://fapi.binance.com",
        market_data_request_timeout_seconds=5.0,
        wallet_address=None,
        risk_max_slippage_pct=1.0,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def candles(count: int = 80) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    values: list[Candle] = []
    price = 100.0
    for index in range(count):
        price += 0.2
        volume = 100.0
        if index == count - 1:
            price *= 1.03
            volume = 500.0
        values.append(
            Candle(
                timestamp=start + timedelta(minutes=5 * index),
                open=price - 0.4,
                high=price + 0.6,
                low=price - 0.8,
                close=price,
                volume=volume,
            )
        )
    return values


class FakeSpotFeed:
    def __init__(self, candle_count: int = 80) -> None:
        self.candle_count = candle_count
        self.calls: list[dict] = []

    async def fetch(self, **kwargs):
        self.calls.append(kwargs)
        return candles(self.candle_count)


@pytest.mark.asyncio
async def test_spot_momentum_signal_enters_on_volume_momentum() -> None:
    signal = await SpotMomentumSignal(settings()).evaluate(
        {"asset": "BTC", "candles": candles(), "btc_context_score": 0.7, "sentiment_score": 0.7}
    )

    assert signal["action"] == "enter_long"
    assert signal["quality"] >= 0.7
    assert signal["components"]["relative_volume"] > 1.5


@pytest.mark.asyncio
async def test_spot_momentum_warms_up_ohlcv_when_payload_has_no_candles() -> None:
    feed = FakeSpotFeed()
    signal = await SpotMomentumSignal(settings(), feed=feed).evaluate(
        {"asset": "CAKE", "btc_context_score": 0.7, "sentiment_score": 0.7}
    )

    assert feed.calls[0]["symbol"] == "CAKEUSDT"
    assert feed.calls[0]["market"] == "spot"
    assert feed.calls[0]["limit"] == 100
    assert signal["asset"] == "CAKE"
    assert signal["reason"] != "insufficient_ohlcv_history"


@pytest.mark.asyncio
async def test_spot_momentum_reports_required_ohlcv_when_warmup_is_short() -> None:
    feed = FakeSpotFeed(candle_count=20)
    signal = await SpotMomentumSignal(settings(), feed=feed).evaluate({"asset": "CAKE"})

    assert signal["reason"] == "insufficient_ohlcv_history"
    assert signal["components"]["candle_count"] == 20
    assert signal["components"]["required_candles"] == 50


@pytest.mark.asyncio
async def test_volume_profile_builds_levels_without_market_provider() -> None:
    profile_candles = candles(120)
    signal = await VolumeProfileSignal(settings()).evaluate({"asset": "BTC", "candles": profile_candles})

    assert signal["market"] == "perp"
    assert signal["components"]["poc"] > 0
    assert signal["components"]["val"] <= signal["components"]["poc"] <= signal["components"]["vah"]


def test_risk_manager_blocks_assets_outside_eligible_universe() -> None:
    manager = RiskManager(settings())
    decision = manager.evaluate(
        SignalIntent(
            asset="NOT_ALLOWED",
            market="spot",
            side="long",
            price=Decimal("100"),
            stop_loss=Decimal("95"),
            quality=Decimal("0.8"),
            quote_equity=Decimal("1000"),
        ),
        portfolio=None,
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "asset_not_in_eligible_universe"


def test_risk_manager_uses_settings_eligible_tokens() -> None:
    manager = RiskManager(settings(eligible_tokens=["BabyDoge"] + [f"TOKEN_{i}" for i in range(99)]))
    decision = manager.evaluate(
        SignalIntent(
            asset="BabyDoge",
            market="spot",
            side="long",
            price=Decimal("100"),
            stop_loss=Decimal("95"),
            quality=Decimal("0.8"),
            quote_equity=Decimal("1000"),
        ),
        portfolio=None,
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is True
    assert decision.reason == "risk_approved"


@pytest.mark.asyncio
async def test_agent_service_dry_run_persists_decision_and_trade(db) -> None:
    class FakeSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "sig-test",
                "market": "spot",
                "asset": "BTC",
                "action": "enter_long",
                "quality": 0.9,
                "confidence": 0.9,
                "price": 100.0,
                "stop_loss": 95.0,
                "quote_equity": 1000.0,
            }

    service = AgentService(
        settings(),
        spot_signal=FakeSignal(),
        perp_signal=VolumeProfileSignal(settings()),
        risk_manager=RiskManager(settings()),
        brain=ClaudeMetaController(settings()),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    async with get_session_factory()() as session:
        result = await service.evaluate_spot({}, session)
        decisions = await AgentDecisionRepository(session).recent_for_user(str(USER_ID))
        trades = await SpotTradeRepository(session).list_for_user(str(USER_ID))

    assert result["execution"]["status"] == "prepared"
    assert len(decisions) == 1
    assert decisions[0].action == "approve"
    assert len(trades) == 1
    assert trades[0].status == "prepared"


@pytest.mark.asyncio
async def test_agent_service_does_not_run_risk_universe_on_skipped_signal(db) -> None:
    class SkippedSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "sig-skip",
                "market": "spot",
                "asset": payload.get("asset"),
                "action": "skip",
                "quality": 0.0,
                "reason": "insufficient_ohlcv_history",
                "components": {},
            }

    service = AgentService(
        settings(),
        spot_signal=SkippedSignal(),
        perp_signal=VolumeProfileSignal(settings()),
        risk_manager=RiskManager(settings()),
        brain=ClaudeMetaController(settings()),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    async with get_session_factory()() as session:
        result = await service.evaluate_spot({"asset": "CAKE"}, session)

    assert result["signal"]["asset"] == "CAKE"
    assert result["risk"]["reason"] == "signal_skipped:insufficient_ohlcv_history"
    assert result["execution"]["reason"] == "insufficient_ohlcv_history"


def test_agent_service_data_coverage_reports_cached_spot_candles() -> None:
    clear_kline_cache()
    binance_klines._KLINE_CACHE[("spot", "CAKEUSDT", "5m")] = BinanceKlineCacheEntry(
        market="spot",
        symbol="CAKEUSDT",
        interval="5m",
        candles=candles(80),
        updated_at=datetime.now(UTC),
    )
    service = AgentService(
        settings(markets_enabled="spot", eligible_tokens=["CAKE"] + [f"TOKEN_{i}" for i in range(99)]),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )

    coverage = service.data_coverage()
    cake = next(item for item in coverage["items"] if item["asset"] == "CAKE")

    assert cake["market"] == "spot"
    assert cake["available_candles"] == 80
    assert cake["required_candles"] == 50
    assert cake["status"] == "ready"
    assert cake["first_candle_at"] is not None
    assert cake["last_candle_at"] is not None
    assert cake["source"] == "Binance klines 5m"


def test_agent_service_data_coverage_reports_cache_miss() -> None:
    clear_kline_cache()
    service = AgentService(
        settings(markets_enabled="spot", eligible_tokens=["CAKE"] + [f"TOKEN_{i}" for i in range(99)]),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )

    coverage = service.data_coverage()
    cake = next(item for item in coverage["items"] if item["asset"] == "CAKE")

    assert cake["available_candles"] == 0
    assert cake["status"] == "insufficient"
    assert cake["updated_at"] is None
