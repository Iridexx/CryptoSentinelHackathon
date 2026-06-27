"""Schemas for the additive mobile agent extension."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class AgentMobileSettings(BaseModel):
    mode: str = "conservative"
    markets_enabled: str = "both"
    execution_mode: str = "dry_run"
    network: str = "testnet"
    test_scaling_pct: float = Field(default=10.0, ge=1.0, le=100.0)
    operating_hours_utc: str = "00:00-23:59"
    # --- Parametri globali (si applicano a entrambi i mercati) ---
    daily_loss_limit_pct: float = Field(default=-8.0, ge=-50.0, lt=0.0)
    drawdown_cap_pct: float = Field(default=-15.0, ge=-50.0, lt=0.0)
    min_pool_liquidity_usd: float = Field(default=50000.0, ge=0.0)

    # --- Parametri SPOT ---
    spot_capital_per_trade_pct: float = Field(default=6.0, gt=0.0, le=100.0)
    spot_per_trade_pct: float = Field(default=1.5, gt=0.0, le=20.0)
    spot_max_open_positions: int = Field(default=3, ge=1, le=20)
    spot_max_exposure_pct: float = Field(default=30.0, gt=0.0, le=100.0)
    spot_cooldown_minutes: int = Field(default=30, ge=0, le=1440)
    spot_max_slippage_pct: float = Field(default=1.0, gt=0.0, le=20.0)

    # --- Parametri PERP ---
    perp_capital_per_trade_pct: float = Field(default=4.0, gt=0.0, le=100.0)
    perp_per_trade_pct: float = Field(default=1.5, gt=0.0, le=20.0)
    perp_max_open_positions: int = Field(default=5, ge=1, le=20)
    perp_max_exposure_pct: float = Field(default=20.0, gt=0.0, le=100.0)
    perp_cooldown_minutes: int = Field(default=15, ge=0, le=1440)
    perp_max_slippage_pct: float = Field(default=0.5, gt=0.0, le=20.0)

    # --- Campi legacy (mantenuti per backward-compat con settings salvati prima del refactor) ---
    capital_per_trade_pct: float = Field(default=6.0, gt=0.0, le=100.0)
    per_trade_pct: float = Field(default=1.5, gt=0.0, le=20.0)
    max_open_positions: int = Field(default=3, ge=1, le=20)
    max_total_exposure_pct: float = Field(default=30.0, gt=0.0, le=100.0)
    max_slippage_pct: float = Field(default=1.0, gt=0.0, le=20.0)
    cooldown_minutes: int = Field(default=30, ge=0, le=1440)
    spot_confidence_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    spot_volatility_trigger_pct: float = Field(default=3.0, ge=0.0, le=100.0)
    spot_relative_volume_threshold: float = Field(default=1.8, ge=0.0, le=100.0)
    spot_atr_stop_multiplier: float = Field(default=1.5, gt=0.0, le=20.0)
    spot_trailing_distance_pct: float = Field(default=2.0, ge=0.0, le=100.0)
    spot_partial_take_profit_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    spot_time_stop_hours: int = Field(default=6, ge=0, le=168)
    perp_direction_mode: str = "long_short"
    # Leva modulata dinamicamente sull'ATR(72) in apertura: bassa volatilità → max,
    # alta volatilità → min. Range configurabile dall'utente.
    perp_min_leverage: int = Field(default=4, ge=1, le=50)
    perp_max_leverage: int = Field(default=40, ge=1, le=50)
    perp_value_area_pct: float = Field(default=68.0, ge=50.0, le=90.0)
    perp_atr_stop_multiplier: float = Field(default=0.5, gt=0.0, le=20.0)
    # Ampiezza del trailing perp: "largo" lascia correre (restituisce di più),
    # "stretto" blocca prima. Il moltiplicatore effettivo scala con la leva del trade.
    perp_trailing_mode: str = Field(default="largo", pattern="^(largo|stretto)$")
    perp_time_stop_hours: int = Field(default=8, ge=0, le=168)
    perp_fee_mode: str = Field(default="taker", pattern="^(taker|maker|none)$")
    spot_fee_mode: str = Field(default="all", pattern="^(all|none)$")

    @model_validator(mode="after")
    def _check_leverage_range(self) -> "AgentMobileSettings":
        if self.perp_min_leverage > self.perp_max_leverage:
            raise ValueError("perp_min_leverage must be <= perp_max_leverage")
        return self


class AgentMobileSettingsResponse(BaseModel):
    settings: AgentMobileSettings
    source: str
    persisted: bool


class CredentialCheck(BaseModel):
    name: str
    configured: bool
    status: str


class CredentialValidationResponse(BaseModel):
    checks: list[CredentialCheck]
    lock_expires_at: str
    lock_ttl_seconds: int


class WalletAssetBalance(BaseModel):
    asset: str
    balance: str
    decimals: int
    source: str


class WalletNetworkView(BaseModel):
    network: str
    address: str | None = None
    configured: bool
    role: str
    balance_status: str = "not_configured"
    balances: list[WalletAssetBalance] = Field(default_factory=list)


class MobileWalletView(BaseModel):
    networks: list[WalletNetworkView]
