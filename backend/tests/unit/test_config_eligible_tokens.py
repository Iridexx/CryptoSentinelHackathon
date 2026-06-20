import pytest
from pydantic import ValidationError

from backend.app.core.config import HARD_ELIGIBLE_TOKEN_MAX_COUNT, HARD_ELIGIBLE_TOKEN_MIN_COUNT, Settings


def test_eligible_tokens_accept_any_string_and_deduplicate_preserving_case() -> None:
    tokens = [
        "SLX",
        "币安人生",
        "BabyDoge",
        "lisUSD",
        "USDf",
        "USDe",
        "XAUt",
        "SLX",
        "USDF",
    ]

    parsed = Settings.split_eligible_tokens(tokens)

    assert parsed == ["SLX", "币安人生", "BabyDoge", "lisUSD", "USDf", "USDe", "XAUt", "USDF"]


def test_eligible_tokens_guardrail_accepts_valid_range_after_deduplication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ELIGIBLE_TOKENS", raising=False)
    tokens = [f"TOKEN_{index}" for index in range(HARD_ELIGIBLE_TOKEN_MIN_COUNT)]
    tokens.append("TOKEN_0")

    settings = Settings(
        _env_file=None,
        ELIGIBLE_TOKENS=tokens,
        BNB_GAS_RESERVE_MIN=0.001,
    )

    assert len(settings.eligible_tokens) == HARD_ELIGIBLE_TOKEN_MIN_COUNT


def test_eligible_tokens_guardrail_rejects_too_few_unique_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELIGIBLE_TOKENS", raising=False)
    tokens = [f"TOKEN_{index}" for index in range(HARD_ELIGIBLE_TOKEN_MIN_COUNT - 1)]

    with pytest.raises(ValidationError, match="between 100 and 200"):
        Settings(
            _env_file=None,
            ELIGIBLE_TOKENS=tokens,
            BNB_GAS_RESERVE_MIN=0.001,
        )


def test_eligible_tokens_guardrail_rejects_too_many_unique_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ELIGIBLE_TOKENS", raising=False)
    tokens = [f"TOKEN_{index}" for index in range(HARD_ELIGIBLE_TOKEN_MAX_COUNT + 1)]

    with pytest.raises(ValidationError, match="between 100 and 200"):
        Settings(
            _env_file=None,
            ELIGIBLE_TOKENS=tokens,
            BNB_GAS_RESERVE_MIN=0.001,
        )
