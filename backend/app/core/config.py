"""Application settings for the FastAPI backend."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import yaml
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_DIR = PROJECT_ROOT / "configs"
HARD_MIN_PORTFOLIO_VALUE_USD = 1.0
HARD_MIN_TRADES_PER_DAY = 1
HARD_ELIGIBLE_TOKEN_COUNT = 149
HARD_MAX_DRAWDOWN_CAP_PCT = -15.0

FUNCTIONAL_CONFIG_FILES = (
    "risk.yaml",
    "strategy_spot.yaml",
    "strategy_perp.yaml",
    "eligible_tokens.yaml",
)

SECTION_FIELD_MAP: dict[str, dict[str, str]] = {
    "app": {
        "env": "app_env",
        "name": "app_name",
        "version": "app_version",
        "default_user_id": "default_user_id",
    },
    "api": {
        "host": "api_host",
        "port": "api_port",
        "base_url": "api_base_url",
        "cors_origins": "cors_origins",
    },
    "dashboard": {
        "port": "dashboard_port",
    },
    "database": {
        "url": "database_url",
        "echo": "database_echo",
        "pool_size": "database_pool_size",
        "max_overflow": "database_max_overflow",
    },
    "logging": {
        "level": "log_level",
        "format": "log_format",
        "retention_days": "log_retention_days",
        "decision_retention_days": "decision_log_retention_days",
    },
    "agent": {
        "mode": "agent_mode",
        "markets_enabled": "markets_enabled",
        "execution_mode": "execution_mode",
        "heartbeat_interval_seconds": "heartbeat_interval_seconds",
        "test_scaling_pct": "test_scaling_pct",
        "operating_hours_utc": "operating_hours_utc",
    },
    "bsc": {
        "network": "bsc_network",
        "chain_id": "bsc_chain_id",
        "rpc_urls": "bsc_rpc_urls",
        "explorer_base_url": "bsc_explorer_base_url",
    },
    "competition": {
        "contract_address": "competition_contract_address",
    },
    "wallet": {
        "address": "wallet_address",
        "key_kdf": "wallet_key_kdf",
        "key_rotation_days": "wallet_key_rotation_days",
    },
    "cmc": {
        "base_url": "cmc_base_url",
        "mcp_enabled": "cmc_mcp_enabled",
        "mcp_server_url": "cmc_mcp_server_url",
        "credit_warning_threshold": "cmc_credit_warning_threshold",
        "credit_critical_threshold": "cmc_credit_critical_threshold",
    },
    "anthropic": {
        "model": "anthropic_model",
        "max_tokens": "anthropic_max_tokens",
        "daily_cost_limit_usd": "anthropic_daily_cost_limit_usd",
    },
    "twak": {
        "base_url": "twak_base_url",
        "autonomous_mode": "twak_autonomous_mode",
        "approval_policy": "twak_approval_policy",
    },
    "perp_execution": {
        "bnb_ai_agent_sdk_enabled": "bnb_ai_agent_sdk_enabled",
        "provider": "perp_execution_provider",
        "eip712_domain": "perp_eip712_domain",
    },
    "x402": {
        "enabled": "x402_enabled",
        "network": "x402_network",
        "usdc_wallet_address": "x402_usdc_wallet_address",
        "daily_spend_limit_usd": "x402_daily_spend_limit_usd",
        "agentdata_base_url": "agentdata_base_url",
    },
    "fcm": {
        "enabled": "fcm_enabled",
        "project_id": "fcm_project_id",
        "critical_topic": "fcm_critical_topic",
        "token_store_path": "fcm_token_store_path",
    },
    "risk": {
        "capital_per_trade_pct": "risk_capital_per_trade_pct",
        "max_open_positions": "risk_max_open_positions",
        "max_total_exposure_pct": "risk_max_total_exposure_pct",
        "daily_loss_limit_pct": "risk_daily_loss_limit_pct",
        "max_drawdown_pct": "risk_max_drawdown_pct",
        "min_pool_liquidity_usd": "risk_min_pool_liquidity_usd",
        "max_slippage_pct": "risk_max_slippage_pct",
        "correlation_limit": "risk_correlation_limit",
        "cooldown_minutes": "risk_cooldown_minutes",
        "bnb_gas_reserve_pct": "bnb_gas_reserve_pct",
        "bnb_gas_reserve_min": "bnb_gas_reserve_min",
        "min_portfolio_value_usd": "min_portfolio_value_usd",
        "minimum_trades_per_day": "minimum_trades_per_day",
    },
    "spot": {
        "confidence_threshold": "spot_confidence_threshold",
        "volatility_trigger_pct": "spot_volatility_trigger_pct",
        "relative_volume_threshold": "spot_relative_volume_threshold",
        "atr_stop_multiplier": "spot_atr_stop_multiplier",
        "trailing_distance_pct": "spot_trailing_distance_pct",
        "partial_take_profit_pct": "spot_partial_take_profit_pct",
        "time_stop_hours": "spot_time_stop_hours",
        "vwap_atr_extension_limit": "spot_vwap_atr_extension_limit",
        "rsi_weight_pct": "spot_rsi_weight_pct",
        "trend_structure_weight_pct": "spot_trend_structure_weight_pct",
        "relative_volume_weight_pct": "spot_relative_volume_weight_pct",
        "btc_context_weight_pct": "spot_btc_context_weight_pct",
        "sentiment_weight_pct": "spot_sentiment_weight_pct",
    },
    "perp": {
        "direction_mode": "perp_direction_mode",
        "value_area_pct": "perp_value_area_pct",
        "atr_stop_multiplier": "perp_atr_stop_multiplier",
        "time_stop_hours": "perp_time_stop_hours",
        "dynamic_leverage_enabled": "perp_dynamic_leverage_enabled",
        "min_volume_profile_liquidity_usd": "perp_min_volume_profile_liquidity_usd",
        "default_leverage": "perp_default_leverage",
        "max_leverage": "perp_max_leverage",
        "volume_profile_window_hours": "perp_volume_profile_window_hours",
        "volume_profile_candle_minutes": "perp_volume_profile_candle_minutes",
    },
    "signal_engine": {
        "binance_futures_base_url": "binance_futures_base_url",
        "binance_futures_ws_url": "binance_futures_ws_url",
        "whale_flow_provider_url": "whale_flow_provider_url",
    },
}


def _config_dir() -> Path:
    """Return the config directory, allowing test/runtime override without reading secrets."""

    return Path(os.environ.get("CONFIG_DIR", DEFAULT_CONFIG_DIR)).resolve()


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping from disk; missing files are treated as empty."""

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Configuration file must contain a mapping: {path}")
    return payload


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Merge nested dictionaries, with override taking precedence."""

    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _flatten_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten documented YAML sections into Settings field names."""

    flattened: dict[str, Any] = {}
    for section, values in payload.items():
        if section == "eligible_tokens":
            flattened["eligible_tokens"] = values
            continue
        if not isinstance(values, dict):
            continue
        field_map = SECTION_FIELD_MAP.get(section, {})
        for key, value in values.items():
            field_name = field_map.get(key)
            if field_name is not None:
                flattened[field_name] = value
    return flattened


def load_yaml_settings(config_dir: Path | None = None) -> dict[str, Any]:
    """Load functional defaults and local instance configuration.

    Precedence is explicit:
    1. Environment variables and .env, handled by pydantic-settings.
    2. configs/instance.yaml, local and gitignored.
    3. Versioned functional defaults in configs/*.yaml.
    """

    root = config_dir or _config_dir()
    merged: dict[str, Any] = {}
    for file_name in FUNCTIONAL_CONFIG_FILES:
        merged = _merge_dicts(merged, _load_yaml(root / file_name))
    merged = _merge_dicts(merged, _load_yaml(root / "instance.yaml"))
    return _flatten_config(merged)


class Settings(BaseSettings):
    """Typed runtime configuration merged from environment and YAML files."""

    app_env: str = Field(default="development", alias="APP_ENV")
    app_name: str = Field(default="CryptoSentinel Agent Backend", alias="APP_NAME")
    app_version: str = Field(default="0.1.0-step2", alias="APP_VERSION")
    api_host: str = Field(default="127.0.0.1", alias="API_HOST")
    api_port: int = Field(default=8000, alias="API_PORT")
    api_base_url: str = Field(default="http://127.0.0.1:8000", alias="API_BASE_URL")
    cors_origins: list[str] = Field(default_factory=list, alias="CORS_ORIGINS")
    dashboard_port: int = Field(default=5176, alias="DASHBOARD_PORT")
    default_user_id: UUID = Field(
        default=UUID("00000000-0000-0000-0000-000000000001"),
        alias="DEFAULT_USER_ID",
    )

    api_read_token: str | None = Field(default=None, alias="API_READ_TOKEN")
    api_admin_token: str | None = Field(default=None, alias="API_ADMIN_TOKEN")
    api_device_token: str | None = Field(default=None, alias="API_DEVICE_TOKEN")
    api_alerts_token: str | None = Field(default=None, alias="API_ALERTS_TOKEN")
    token_hash_pepper: str | None = Field(default=None, alias="TOKEN_HASH_PEPPER")

    database_url: str = Field(default="sqlite+aiosqlite:///./backend/local.db", alias="DATABASE_URL")
    database_echo: bool = Field(default=False, alias="DATABASE_ECHO")
    database_pool_size: int = Field(default=5, alias="DATABASE_POOL_SIZE")
    database_max_overflow: int = Field(default=10, alias="DATABASE_MAX_OVERFLOW")

    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: Literal["json", "console"] = Field(default="json", alias="LOG_FORMAT")
    log_retention_days: int = Field(default=14, alias="LOG_RETENTION_DAYS")
    decision_log_retention_days: int = Field(default=30, alias="DECISION_LOG_RETENTION_DAYS")

    cmc_api_key: str | None = Field(default=None, alias="CMC_API_KEY")
    cmc_base_url: str = Field(default="https://pro-api.coinmarketcap.com", alias="CMC_BASE_URL")
    cmc_mcp_enabled: bool = Field(default=False, alias="CMC_MCP_ENABLED")
    cmc_mcp_server_url: str | None = Field(default=None, alias="CMC_MCP_SERVER_URL")
    cmc_credit_warning_threshold: int = Field(default=20, alias="CMC_CREDIT_WARNING_THRESHOLD")
    cmc_credit_critical_threshold: int = Field(default=10, alias="CMC_CREDIT_CRITICAL_THRESHOLD")

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-sonnet-4-5", alias="ANTHROPIC_MODEL")
    anthropic_max_tokens: int = Field(default=4096, alias="ANTHROPIC_MAX_TOKENS")
    anthropic_daily_cost_limit_usd: float = Field(default=10.0, alias="ANTHROPIC_DAILY_COST_LIMIT_USD")

    bsc_network: str = Field(default="testnet", alias="BSC_NETWORK")
    bsc_chain_id: int = Field(default=97, alias="BSC_CHAIN_ID")
    bsc_rpc_urls: list[str] = Field(default_factory=list, alias="BSC_RPC_URLS")
    bsc_explorer_base_url: str | None = Field(default=None, alias="BSC_EXPLORER_BASE_URL")
    competition_contract_address: str | None = Field(default=None, alias="COMPETITION_CONTRACT_ADDRESS")

    wallet_address: str | None = Field(default=None, alias="WALLET_ADDRESS")
    wallet_encrypted_private_key_path: str | None = Field(default=None, alias="WALLET_ENCRYPTED_PRIVATE_KEY_PATH")
    wallet_key_passphrase_env: str | None = Field(default=None, alias="WALLET_KEY_PASSPHRASE_ENV")
    wallet_key_kdf: str = Field(default="scrypt", alias="WALLET_KEY_KDF")
    wallet_key_rotation_days: int = Field(default=7, alias="WALLET_KEY_ROTATION_DAYS")

    twak_access_id: str | None = Field(default=None, alias="TWAK_ACCESS_ID")
    twak_hmac_secret: str | None = Field(default=None, alias="TWAK_HMAC_SECRET")
    twak_base_url: str | None = Field(default=None, alias="TWAK_BASE_URL")
    twak_autonomous_mode: bool = Field(default=False, alias="TWAK_AUTONOMOUS_MODE")
    twak_approval_policy: str = Field(default="exact", alias="TWAK_APPROVAL_POLICY")

    bnb_ai_agent_sdk_enabled: bool = Field(default=False, alias="BNB_AI_AGENT_SDK_ENABLED")
    perp_execution_provider: str = Field(default="bnb_sdk", alias="PERP_EXECUTION_PROVIDER")
    perp_eip712_domain: str | None = Field(default=None, alias="PERP_EIP712_DOMAIN")

    x402_enabled: bool = Field(default=False, alias="X402_ENABLED")
    x402_network: str = Field(default="base", alias="X402_NETWORK")
    x402_usdc_wallet_address: str | None = Field(default=None, alias="X402_USDC_WALLET_ADDRESS")
    x402_daily_spend_limit_usd: float = Field(default=5.0, alias="X402_DAILY_SPEND_LIMIT_USD")
    agentdata_base_url: str | None = Field(default=None, alias="AGENTDATA_BASE_URL")

    fcm_enabled: bool = Field(default=False, alias="FCM_ENABLED")
    fcm_project_id: str | None = Field(default=None, alias="FCM_PROJECT_ID")
    fcm_credentials_path: str | None = Field(default=None, alias="FCM_CREDENTIALS_PATH")
    fcm_critical_topic: str | None = Field(default=None, alias="FCM_CRITICAL_TOPIC")
    fcm_token_store_path: str = Field(default="backend/storage/fcm_tokens.json", alias="FCM_TOKEN_STORE_PATH")

    agent_mode: str = Field(default="conservative", alias="AGENT_MODE")
    markets_enabled: str = Field(default="both", alias="MARKETS_ENABLED")
    execution_mode: str = Field(default="dry_run", alias="EXECUTION_MODE")
    heartbeat_interval_seconds: int = Field(default=30, alias="HEARTBEAT_INTERVAL_SECONDS")
    test_scaling_pct: float = Field(default=10.0, alias="TEST_SCALING_PCT")
    operating_hours_utc: str = Field(default="00:00-23:59", alias="OPERATING_HOURS_UTC")

    bnb_gas_reserve_pct: float = Field(default=15.0, alias="BNB_GAS_RESERVE_PCT")
    bnb_gas_reserve_min: float | None = Field(default=None, alias="BNB_GAS_RESERVE_MIN")
    min_portfolio_value_usd: float = Field(default=5.0, alias="MIN_PORTFOLIO_VALUE_USD")
    minimum_trades_per_day: int = Field(default=1, alias="MINIMUM_TRADES_PER_DAY")
    risk_capital_per_trade_pct: float = Field(default=6.0, alias="RISK_CAPITAL_PER_TRADE_PCT")
    risk_max_open_positions: int = Field(default=3, alias="RISK_MAX_OPEN_POSITIONS")
    risk_max_total_exposure_pct: float = Field(default=30.0, alias="RISK_MAX_TOTAL_EXPOSURE_PCT")
    risk_daily_loss_limit_pct: float = Field(default=-8.0, alias="RISK_DAILY_LOSS_LIMIT_PCT")
    risk_max_drawdown_pct: float = Field(default=-15.0, alias="RISK_MAX_DRAWDOWN_PCT")
    risk_min_pool_liquidity_usd: float = Field(default=50000.0, alias="RISK_MIN_POOL_LIQUIDITY_USD")
    risk_max_slippage_pct: float = Field(default=1.0, alias="RISK_MAX_SLIPPAGE_PCT")
    risk_correlation_limit: float = Field(default=0.8, alias="RISK_CORRELATION_LIMIT")
    risk_cooldown_minutes: int = Field(default=30, alias="RISK_COOLDOWN_MINUTES")

    spot_confidence_threshold: float = Field(default=0.70, alias="SPOT_CONFIDENCE_THRESHOLD")
    spot_volatility_trigger_pct: float = Field(default=3.0, alias="SPOT_VOLATILITY_TRIGGER_PCT")
    spot_relative_volume_threshold: float = Field(default=1.8, alias="SPOT_RELATIVE_VOLUME_THRESHOLD")
    spot_atr_stop_multiplier: float = Field(default=1.5, alias="SPOT_ATR_STOP_MULTIPLIER")
    spot_trailing_distance_pct: float = Field(default=2.0, alias="SPOT_TRAILING_DISTANCE_PCT")
    spot_partial_take_profit_pct: float = Field(default=50.0, alias="SPOT_PARTIAL_TAKE_PROFIT_PCT")
    spot_time_stop_hours: int = Field(default=6, alias="SPOT_TIME_STOP_HOURS")
    spot_vwap_atr_extension_limit: float = Field(default=1.2, alias="SPOT_VWAP_ATR_EXTENSION_LIMIT")
    spot_rsi_weight_pct: float = Field(default=15.0, alias="SPOT_RSI_WEIGHT_PCT")
    spot_trend_structure_weight_pct: float = Field(default=30.0, alias="SPOT_TREND_STRUCTURE_WEIGHT_PCT")
    spot_relative_volume_weight_pct: float = Field(default=30.0, alias="SPOT_RELATIVE_VOLUME_WEIGHT_PCT")
    spot_btc_context_weight_pct: float = Field(default=15.0, alias="SPOT_BTC_CONTEXT_WEIGHT_PCT")
    spot_sentiment_weight_pct: float = Field(default=10.0, alias="SPOT_SENTIMENT_WEIGHT_PCT")

    perp_direction_mode: str = Field(default="long_short", alias="PERP_DIRECTION_MODE")
    perp_value_area_pct: float = Field(default=68.0, alias="PERP_VALUE_AREA_PCT")
    perp_atr_stop_multiplier: float = Field(default=1.0, alias="PERP_ATR_STOP_MULTIPLIER")
    perp_time_stop_hours: int = Field(default=8, alias="PERP_TIME_STOP_HOURS")
    perp_dynamic_leverage_enabled: bool = Field(default=True, alias="PERP_DYNAMIC_LEVERAGE_ENABLED")
    perp_min_volume_profile_liquidity_usd: float = Field(
        default=50000.0,
        alias="PERP_MIN_VOLUME_PROFILE_LIQUIDITY_USD",
    )
    perp_default_leverage: int = Field(default=2, alias="PERP_DEFAULT_LEVERAGE")
    perp_max_leverage: int = Field(default=5, alias="PERP_MAX_LEVERAGE")
    perp_volume_profile_window_hours: int = Field(default=24, alias="PERP_VOLUME_PROFILE_WINDOW_HOURS")
    perp_volume_profile_candle_minutes: int = Field(default=5, alias="PERP_VOLUME_PROFILE_CANDLE_MINUTES")

    binance_futures_base_url: str | None = Field(default=None, alias="BINANCE_FUTURES_BASE_URL")
    binance_futures_ws_url: str | None = Field(default=None, alias="BINANCE_FUTURES_WS_URL")
    whale_flow_provider_url: str | None = Field(default=None, alias="WHALE_FLOW_PROVIDER_URL")

    eligible_tokens: list[str] = Field(default_factory=list, alias="ELIGIBLE_TOKENS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        """Use explicit precedence: environment/.env override YAML defaults."""

        return env_settings, dotenv_settings, init_settings, file_secret_settings

    @field_validator("cors_origins", "bsc_rpc_urls", mode="before")
    @classmethod
    def split_string_list(cls, value: str | list[str] | None) -> list[str]:
        """Parse comma-separated list values from environment variables."""

        if value is None or value == "":
            return []
        if isinstance(value, list):
            return value
        return [item.strip() for item in value.split(",") if item.strip()]

    @field_validator("eligible_tokens", mode="before")
    @classmethod
    def split_eligible_tokens(cls, value: str | list[str] | None) -> list[str]:
        """Parse eligible token lists from YAML or environment overrides."""

        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(token).strip() for token in value if str(token).strip()]
        return [token.strip() for token in value.split(",") if token.strip()]

    @model_validator(mode="after")
    def validate_hard_guardrails(self) -> "Settings":
        """Reject startup if non-disablable qualification guardrails are violated."""

        if self.min_portfolio_value_usd <= HARD_MIN_PORTFOLIO_VALUE_USD:
            raise ValueError("min_portfolio_value_usd must stay above the hard $1 qualification floor")
        if self.minimum_trades_per_day < HARD_MIN_TRADES_PER_DAY:
            raise ValueError("minimum_trades_per_day must be at least 1")
        if self.risk_max_drawdown_pct < HARD_MAX_DRAWDOWN_CAP_PCT or self.risk_max_drawdown_pct >= 0:
            raise ValueError("risk_max_drawdown_pct must be negative and no looser than -15%")
        if len(self.eligible_tokens) != HARD_ELIGIBLE_TOKEN_COUNT:
            raise ValueError("eligible_tokens must contain exactly the 149 competition-eligible entries")
        return self

    @property
    def auth_configured(self) -> bool:
        """Return whether both read and admin tokens are configured."""

        return bool(self.api_read_token and self.api_admin_token)

    @property
    def is_https_enabled(self) -> bool:
        """Return whether the public API URL is configured as HTTPS."""

        return self.api_base_url.lower().startswith("https://")


@lru_cache
def get_settings() -> Settings:
    """Return cached settings for dependency injection."""

    return Settings(**load_yaml_settings())
