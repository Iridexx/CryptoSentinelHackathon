"""Step 6 agent brain, signal and risk regressions."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.app.agent.brain import ClaudeMetaController
from backend.app.agent.ohlcv_warmup import warmup_selected_watchlist
from backend.app.agent.risk import KillSwitchState, RiskManager, SignalIntent
from backend.app.agent.service import AgentService
from backend.app.agent.signals.common.indicators import Candle
from backend.app.agent.signals.perp import binance_klines
from backend.app.agent.signals.perp.binance_klines import BinanceKlineCacheEntry, clear_kline_cache
from backend.app.agent.signals.perp.volume_profile import VolumeProfileSignal
from backend.app.agent.signals.spot.momentum import SpotMomentumSignal
from backend.app.agent.watchlist import set_selected_watchlist
from backend.app.persistence.repositories.decisions import AgentDecisionRepository
from backend.app.persistence.repositories.positions import SpotPositionRepository
from backend.app.persistence.models.pnl import PortfolioState
from backend.app.persistence.models.positions import SpotPosition
from backend.app.persistence.repositories.trades import PerpTradeRepository, SpotTradeRepository
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
        minimum_trades_per_day=1,
        execution_mode="dry_run",
        agent_mode="conservative",
        markets_enabled="both",
        anthropic_api_key=None,
        anthropic_model="claude-test",
        anthropic_max_tokens=512,
        risk_capital_per_trade_pct=4.0,
        risk_max_open_positions=5,
        risk_max_total_exposure_pct=30.0,
        risk_daily_loss_limit_pct=-8.0,
        risk_max_drawdown_pct=-15.0,
        risk_cooldown_minutes=0,
        risk_min_pool_liquidity_usd=50000.0,
        dry_run_capital_usd=200.0,
        min_trade_size_usd=7.0,
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
        spot_quote_token_address=None,
        spot_quote_token_decimals=18,
        spot_token_map={},
        cmc_api_key=None,
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


def _intent(**overrides) -> SignalIntent:
    payload = dict(
        asset="BTC",
        market="spot",
        side="long",
        price=Decimal("100"),
        stop_loss=Decimal("95"),
        quality=Decimal("0.8"),
        quote_equity=Decimal("1000"),
    )
    payload.update(overrides)
    return SignalIntent(**payload)


def _portfolio(**overrides) -> PortfolioState:
    payload = dict(
        user_id=str(USER_ID),
        total_equity_usd=Decimal("1000"),
        initial_equity_usd=Decimal("1000"),
        peak_equity_usd=Decimal("1000"),
        drawdown_pct=Decimal("0"),
        max_drawdown_pct=Decimal("0"),
        exposure_pct=Decimal("0"),
        daily_pnl_usd=Decimal("0"),
        daily_loss_limit_used_pct=Decimal("0"),
        agent_status="idle",
        trades_today=0,
        updated_at=datetime.now(UTC),
    )
    payload.update(overrides)
    return PortfolioState(**payload)


def _spot_position(index: int = 0, asset: str = "BTC") -> SpotPosition:
    now = datetime.now(UTC)
    return SpotPosition(
        position_id=f"pos-{index}",
        user_id=str(USER_ID),
        asset=asset,
        size=Decimal("1"),
        entry_price=Decimal("100"),
        current_price=Decimal("100"),
        opened_at=now,
        updated_at=now,
    )


def test_risk_engine_daily_loss_limit() -> None:
    decision = RiskManager(settings()).evaluate(
        _intent(),
        portfolio=_portfolio(daily_loss_limit_used_pct=Decimal("-8.1")),
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "daily_loss_limit_guard"


def test_risk_engine_max_positions() -> None:
    # Asset diversi tra loro e dall'intent: testa il limite totale, non il dedup per-asset.
    decision = RiskManager(settings(risk_max_open_positions=2)).evaluate(
        _intent(asset="TOKEN_5"),
        portfolio=_portfolio(),
        open_spot_positions=[_spot_position(1, asset="TOKEN_1"), _spot_position(2, asset="TOKEN_2")],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "max_open_positions_guard"


def test_risk_engine_dedup_per_asset() -> None:
    # Un nuovo segnale su un asset gia' in posizione viene bloccato prima del limite totale.
    decision = RiskManager(settings(risk_max_open_positions=5)).evaluate(
        _intent(asset="BTC"),
        portfolio=_portfolio(),
        open_spot_positions=[_spot_position(1, asset="BTC")],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "asset_already_open"


def test_risk_engine_drawdown_cap_positive_convention() -> None:
    # drawdown_pct e' positivo (entita' del calo); cap negativo -15 => blocca a >= 15.
    decision = RiskManager(settings()).evaluate(
        _intent(),
        portfolio=_portfolio(drawdown_pct=Decimal("16")),
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "drawdown_cap_guard"


def test_risk_engine_guardia_dollar() -> None:
    decision = RiskManager(settings(min_portfolio_value_usd=5.0)).evaluate(
        _intent(),
        portfolio=_portfolio(total_equity_usd=Decimal("5")),
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "portfolio_floor_guard"


def test_risk_engine_size_cap() -> None:
    decision = RiskManager(settings()).evaluate(
        _intent(price=Decimal("100"), stop_loss=Decimal("50")),
        portfolio=_portfolio(total_equity_usd=Decimal("1000")),
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is True
    assert decision.size_quote == Decimal("30.00")


def test_risk_engine_uses_200_dry_run_capital_for_natural_size() -> None:
    decision = RiskManager(settings()).evaluate(
        _intent(quote_equity=Decimal("200"), price=Decimal("100"), stop_loss=Decimal("95")),
        portfolio=None,
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is True
    assert decision.size_quote == Decimal("8.00")


def test_risk_engine_blocks_below_minimum_trade_size() -> None:
    decision = RiskManager(settings()).evaluate(
        _intent(quote_equity=Decimal("100"), price=Decimal("100"), stop_loss=Decimal("95")),
        portfolio=None,
        open_spot_positions=[],
        open_perp_positions=[],
    )

    assert decision.allowed is False
    assert decision.reason == "below_minimum_trade_size"
    assert decision.size_quote == Decimal("4.00")


@pytest.mark.asyncio
async def test_meta_controller_fallback_on_timeout(monkeypatch) -> None:
    class TimeoutClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            raise TimeoutError("timeout")

    monkeypatch.setattr("backend.app.agent.brain.meta_controller.httpx.AsyncClient", TimeoutClient)

    decision, _usage = await ClaudeMetaController(settings(anthropic_api_key="configured")).decide(
        signal={"quality": 0.9},
        risk={"allowed": True, "reason": "risk_approved"},
    )

    assert decision.action == "approve"
    assert "claude_unavailable_dry_run" in decision.reasoning


@pytest.mark.asyncio
async def test_meta_controller_reduce() -> None:
    decision, _usage = await ClaudeMetaController(settings()).decide(
        signal={"quality": 0.7},
        risk={"allowed": True, "reason": "risk_approved"},
    )

    assert decision.action == "reduce"
    assert decision.size_multiplier == Decimal("0.5")


def test_kill_switch_soft_stop() -> None:
    manager = RiskManager(settings())
    manager.set_kill_switch(KillSwitchState.SOFT_STOP)

    decision = manager.evaluate(_intent(), portfolio=_portfolio(), open_spot_positions=[], open_perp_positions=[])

    assert decision.allowed is False
    assert decision.reason == "soft_stop"


def test_kill_switch_hard_stop() -> None:
    manager = RiskManager(settings())
    manager.set_kill_switch(KillSwitchState.HARD_STOP)

    decision = manager.evaluate(_intent(), portfolio=_portfolio(), open_spot_positions=[], open_perp_positions=[])

    assert decision.allowed is False
    assert decision.reason == "hard_stop_enabled"


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
async def test_agent_service_dry_run_persists_perp_decision_and_trade(db) -> None:
    class FakeSignal:
        async def evaluate(self, payload):
            return {
                "signal_id": "sig-perp-test",
                "market": "perp",
                "asset": "BTC",
                "action": "enter_long",
                "side": "long",
                "quality": 0.9,
                "confidence": 0.9,
                "price": 100.0,
                "stop_loss": 95.0,
                "quote_equity": 1000.0,
                "leverage": 2,
            }

    service = AgentService(
        settings(),
        spot_signal=SpotMomentumSignal(settings()),
        perp_signal=FakeSignal(),
        risk_manager=RiskManager(settings()),
        brain=ClaudeMetaController(settings()),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    async with get_session_factory()() as session:
        result = await service.evaluate_perp({}, session)
        decisions = await AgentDecisionRepository(session).recent_for_user(str(USER_ID))
        trades = await PerpTradeRepository(session).list_for_user(str(USER_ID))

    assert result["execution"]["status"] == "prepared"
    assert len(decisions) == 1
    assert decisions[0].market == "perp"
    assert len(trades) == 1
    assert trades[0].status == "prepared"


@pytest.mark.asyncio
async def test_heartbeat_triggers_at_20utc(db) -> None:
    service = AgentService(
        settings(eligible_tokens=["ETH"] + [f"TOKEN_{i}" for i in range(148)]),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime(2026, 6, 22, 20, 0, tzinfo=UTC)
    async with get_session_factory()() as session:
        result = await service.slow_tick(session, now=now)
        trades = await SpotTradeRepository(session).list_for_user(str(USER_ID))

    heartbeat_result = result["daily_trade_heartbeat"]
    assert heartbeat_result["status"] == "executed"
    assert heartbeat_result["mode"] == "dry_run"
    assert len(trades) == 1
    assert trades[0].asset == "ETH"
    assert trades[0].notes == "dry_run_step6"
    assert trades[0].amount_quote == Decimal("7")


@pytest.mark.asyncio
async def test_build_spot_swap_params_maps_token() -> None:
    service = AgentService(
        settings(
            spot_quote_token_address="0xQUOTE",
            spot_quote_token_decimals=18,
            spot_token_map={"ETH": "0xETH:18"},
        ),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    params = await service._build_spot_swap_params({"asset": "ETH"}, Decimal("10"))
    assert params is not None
    assert params["from_asset"] == "0xQUOTE"
    assert params["to_asset"] == "0xETH"
    assert params["amount_in_atomic"] == 10 * 10**18


@pytest.mark.asyncio
async def test_build_spot_swap_params_skips_when_unmapped_and_no_resolver() -> None:
    # Asset non in mappa e nessun resolver CMC (api_key None) => None.
    s1 = AgentService(
        settings(spot_quote_token_address="0xQUOTE", spot_token_map={}),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    assert await s1._build_spot_swap_params({"asset": "ETH"}, Decimal("10")) is None


@pytest.mark.asyncio
async def test_build_spot_swap_params_resolves_via_cmc() -> None:
    # Niente mappa statica: indirizzi risolti dal resolver CMC iniettato.
    class FakeResolver:
        async def resolve_contract_address(self, symbol: str, **_: object) -> str:
            return {"ETH": "0xETHCMC", "USDT": "0xUSDTCMC"}[symbol.upper()]

    service = AgentService(
        settings(spot_quote_token_address=None, spot_token_map={}),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
        token_resolver=FakeResolver(),
    )
    params = await service._build_spot_swap_params({"asset": "ETH"}, Decimal("10"))
    assert params is not None
    assert params["from_asset"] == "0xUSDTCMC"
    assert params["to_asset"] == "0xETHCMC"
    assert params["amount_in_atomic"] == 10 * 10**18


@pytest.mark.asyncio
async def test_spot_trailing_activates_only_after_tp1(db) -> None:
    service = AgentService(
        settings(),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime.now(UTC)

    def _pos(position_id: str, tp1: bool) -> SpotPosition:
        # entry 100, trailing a 99, prezzo a 98 (sotto il trailing): chiuderebbe per trailing.
        # stop_loss basso (90) e nessun TP per isolare il solo trailing.
        return SpotPosition(
            position_id=position_id,
            user_id=str(USER_ID),
            asset="BTC",
            size=Decimal("1"),
            entry_price=Decimal("100"),
            current_price=Decimal("98"),
            stop_loss=Decimal("90"),
            trailing_stop=Decimal("99"),
            tp1_reached=tp1,
            status="open",
            opened_at=now,
            updated_at=now,
        )

    pos_no_tp1 = _pos("p-no-tp1", tp1=False)
    pos_tp1 = _pos("p-tp1", tp1=True)
    async with get_session_factory()() as session:
        await service._check_sl_tp(session, [pos_no_tp1, pos_tp1], [], now)

    # Senza TP1 il trailing non si attiva: la posizione resta aperta.
    assert pos_no_tp1.status == "open"
    # Con TP1 raggiunto il trailing chiude la posizione.
    assert pos_tp1.status == "closed"


@pytest.mark.asyncio
async def test_heartbeat_skips_when_eth_already_open(db) -> None:
    service = AgentService(
        settings(eligible_tokens=["ETH"] + [f"TOKEN_{i}" for i in range(148)]),
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    now = datetime(2026, 6, 22, 20, 0, tzinfo=UTC)
    async with get_session_factory()() as session:
        await SpotPositionRepository(session).save(_spot_position(0, asset="ETH"))
        result = await service.slow_tick(session, now=now)

    heartbeat_result = result["daily_trade_heartbeat"]
    assert heartbeat_result["status"] == "satisfied"
    assert heartbeat_result["reason"] == "asset_already_open"


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


@pytest.mark.asyncio
async def test_agent_service_data_coverage_reports_cached_spot_candles(db) -> None:
    clear_kline_cache()
    cfg = settings(markets_enabled="spot", eligible_tokens=["CAKE"] + [f"TOKEN_{i}" for i in range(99)])
    set_selected_watchlist(cfg, ["CAKE"])
    binance_klines._KLINE_CACHE[("spot", "CAKEUSDT", "5m")] = BinanceKlineCacheEntry(
        market="spot",
        symbol="CAKEUSDT",
        interval="5m",
        candles=candles(80),
        updated_at=datetime.now(UTC),
    )
    service = AgentService(
        cfg,
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


@pytest.mark.asyncio
async def test_agent_service_data_coverage_reports_cache_miss(db) -> None:
    clear_kline_cache()
    cfg = settings(markets_enabled="spot", eligible_tokens=["CAKE"] + [f"TOKEN_{i}" for i in range(99)])
    set_selected_watchlist(cfg, ["CAKE"])
    service = AgentService(
        cfg,
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )

    coverage = service.data_coverage()
    cake = next(item for item in coverage["items"] if item["asset"] == "CAKE")

    assert cake["available_candles"] == 0
    assert cake["status"] == "insufficient"
    assert cake["updated_at"] is None


@pytest.mark.asyncio
async def test_watchlist_warmup_populates_data_coverage_cache(db) -> None:
    clear_kline_cache()
    cfg = settings(markets_enabled="both", eligible_tokens=["CAKE"] + [f"TOKEN_{i}" for i in range(99)])
    set_selected_watchlist(cfg, ["CAKE"])

    class FakeFeed:
        def __init__(self) -> None:
            self.calls = []

        async def fetch(self, **kwargs):
            self.calls.append(kwargs)
            payload = candles(288)
            binance_klines._KLINE_CACHE[(kwargs["market"], kwargs["symbol"], kwargs["interval"])] = BinanceKlineCacheEntry(
                market=kwargs["market"],
                symbol=kwargs["symbol"],
                interval=kwargs["interval"],
                candles=payload,
                updated_at=datetime.now(UTC),
            )
            return payload

    feed = FakeFeed()
    result = await warmup_selected_watchlist(cfg, feed=feed)
    service = AgentService(
        cfg,
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )
    coverage = service.data_coverage()
    cake_items = [item for item in coverage["items"] if item["asset"] == "CAKE"]

    assert result["loaded"] == 2
    assert len(feed.calls) == 2
    assert all(call["limit"] >= 288 for call in feed.calls)
    assert {item["market"] for item in cake_items} == {"spot", "perp"}
    assert all(item["available_candles"] == 288 for item in cake_items)
    assert all(item["status"] == "ready" for item in cake_items)
