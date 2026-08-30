"""API schemas for the "Bank" store-of-value reserve settings.

``ReserveSettings`` is the user-tunable subset of ``core.config.ReserveConfig``.
Defaults come from ``configs/reserve.yaml``; the user can override this subset
from the Setup > Bank screen and the override is persisted in runtime_state.
The asset list itself is not user-editable and lives only in the YAML config.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.core.config import RESERVE_WEIGHT_SUM_TOLERANCE, ReserveConfig


class ReserveTargetWeight(BaseModel):
    """Target allocation for one reserve asset, in percent of reserve value."""

    symbol: str
    weight_pct: float = Field(ge=0.0)

    @field_validator("symbol", mode="before")
    @classmethod
    def _upper_symbol(cls, value: str) -> str:
        return str(value).strip().upper()


class ReserveSettings(BaseModel):
    """User-tunable reserve parameters (Setup > Bank)."""

    enabled: bool = False
    auto_rebalance: bool = True
    drift_band_pct: float = Field(default=5.0, gt=0.0)
    min_transfer_usd: float = Field(default=10.0, ge=0.0)
    withdrawal_cooldown_minutes: int = Field(default=1440, ge=0)
    block_withdrawal_during_drawdown_guard: bool = True
    sweep_enabled: bool = True
    sweep_pct: float = Field(default=20.0, ge=0.0, le=100.0)
    sweep_interval_hours: int = Field(default=24, ge=1)
    sweep_min_tradable_equity_usd: float = Field(default=50.0, ge=0.0)
    target_weights: list[ReserveTargetWeight] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_weights(self) -> "ReserveSettings":
        symbols = [w.symbol for w in self.target_weights]
        if len(symbols) != len(set(symbols)):
            raise ValueError("reserve target_weights symbols must be unique")
        if self.enabled and self.target_weights:
            total = sum(w.weight_pct for w in self.target_weights)
            if abs(total - 100.0) > RESERVE_WEIGHT_SUM_TOLERANCE:
                raise ValueError(
                    f"reserve target weights must sum to 100 (got {total:.2f})"
                )
        return self

    @classmethod
    def from_config(cls, config: ReserveConfig) -> "ReserveSettings":
        """Build the default settings instance from the versioned YAML config."""

        return cls(
            enabled=config.enabled,
            auto_rebalance=config.auto_rebalance,
            drift_band_pct=config.drift_band_pct,
            min_transfer_usd=config.min_transfer_usd,
            withdrawal_cooldown_minutes=config.withdrawal_cooldown_minutes,
            block_withdrawal_during_drawdown_guard=config.block_withdrawal_during_drawdown_guard,
            sweep_enabled=config.sweep_enabled,
            sweep_pct=config.sweep_pct,
            sweep_interval_hours=config.sweep_interval_hours,
            sweep_min_tradable_equity_usd=config.sweep_min_tradable_equity_usd,
            target_weights=[
                ReserveTargetWeight(symbol=a.symbol, weight_pct=a.target_weight_pct)
                for a in config.assets
            ],
        )

    def reconcile_with_config(self, config: ReserveConfig) -> "ReserveSettings":
        """Drop weights for assets no longer configured and add missing ones.

        Keeps a persisted override valid after the YAML asset list changes.
        """

        allowed = {a.symbol: a.target_weight_pct for a in config.assets}
        kept = [w for w in self.target_weights if w.symbol in allowed]
        known = {w.symbol for w in kept}
        for symbol, default_weight in allowed.items():
            if symbol not in known:
                kept.append(ReserveTargetWeight(symbol=symbol, weight_pct=default_weight))
        return self.model_copy(update={"target_weights": kept})


class ReserveSettingsResponse(BaseModel):
    """GET/PUT response for reserve settings."""

    settings: ReserveSettings
    source: Literal["default", "persisted"]
