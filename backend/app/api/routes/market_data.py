"""Provider-neutral market data routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep
from backend.app.data.market_data.base import ProviderCapabilityError, ProviderError
from backend.app.data.market_data.registry import MarketDataRegistry, get_market_data_registry
from backend.app.data.mcp.cmc import cmc_mcp_connection
from backend.app.schemas.market_data import (
    MarketListResponse,
    OHLCVResponse,
    PriceListResponse,
    ProviderSelectionRequest,
    ProviderSelectionResponse,
)

router = APIRouter(prefix="/api/v1/market-data", tags=["market-data"])
RegistryDep = Annotated[MarketDataRegistry, Depends(get_market_data_registry)]


def _raise_provider_error(exc: ProviderError) -> None:
    if isinstance(exc, ProviderCapabilityError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/provider", response_model=ProviderSelectionResponse)
async def provider_status(registry: RegistryDep, _: ReadAccessDep) -> ProviderSelectionResponse:
    """Return the global provider selection and non-secret diagnostics."""

    return ProviderSelectionResponse(
        active=registry.active_name,
        providers=registry.statuses(),
        cmc_mcp=cmc_mcp_connection(registry.settings),
    )


@router.put("/provider", response_model=ProviderSelectionResponse)
async def select_provider(
    request: ProviderSelectionRequest,
    registry: RegistryDep,
    _: AdminAccessDep,
) -> ProviderSelectionResponse:
    """Select one global provider until restart. No fallback is performed."""

    registry.select(request.provider)
    return ProviderSelectionResponse(
        active=registry.active_name,
        providers=registry.statuses(),
        cmc_mcp=cmc_mcp_connection(registry.settings),
    )


@router.get("/markets", response_model=MarketListResponse)
async def market_list(
    registry: RegistryDep,
    _: ReadAccessDep,
    currency: str = Query(default="usd", min_length=3, max_length=5),
    limit: int = Query(default=50, ge=1, le=5000),
    page: int = Query(default=1, ge=1),
    ids: str | None = None,
) -> MarketListResponse:
    """Return a normalized market list from the selected provider."""

    asset_ids = [item.strip() for item in ids.split(",") if item.strip()] if ids else None
    try:
        items = await registry.get_market_list(currency, limit, page, asset_ids)
    except ProviderError as exc:
        _raise_provider_error(exc)
    return MarketListResponse(provider=registry.active_name, currency=currency.lower(), items=items)


@router.get("/prices", response_model=PriceListResponse)
async def prices(
    registry: RegistryDep,
    _: ReadAccessDep,
    ids: str = Query(min_length=1),
    currencies: str = Query(default="usd", min_length=3),
) -> PriceListResponse:
    """Return normalized current prices from the selected provider."""

    asset_ids = [item.strip() for item in ids.split(",") if item.strip()]
    currency_list = [item.strip().lower() for item in currencies.split(",") if item.strip()]
    try:
        items = await registry.get_prices(asset_ids, currency_list)
    except ProviderError as exc:
        _raise_provider_error(exc)
    return PriceListResponse(provider=registry.active_name, items=items)


@router.get("/search", response_model=MarketListResponse)
async def search(
    registry: RegistryDep,
    _: ReadAccessDep,
    q: str = Query(min_length=1, max_length=100),
    currency: str = Query(default="usd", min_length=3, max_length=5),
    limit: int = Query(default=25, ge=1, le=100),
) -> MarketListResponse:
    """Search assets through the selected provider."""

    try:
        items = await registry.search(q, currency, limit)
    except ProviderError as exc:
        _raise_provider_error(exc)
    return MarketListResponse(provider=registry.active_name, currency=currency.lower(), items=items)


@router.get("/ohlcv", response_model=OHLCVResponse)
async def ohlcv(
    registry: RegistryDep,
    _: ReadAccessDep,
    asset_id: str = Query(min_length=1),
    currency: str = Query(default="usd", min_length=3, max_length=5),
    days: int = Query(default=7, ge=1, le=3650),
    interval: str | None = None,
) -> OHLCVResponse:
    """Return normalized OHLCV history from the selected provider."""

    try:
        items = await registry.get_ohlcv(asset_id, currency, days, interval)
    except ProviderError as exc:
        _raise_provider_error(exc)
    return OHLCVResponse(
        provider=registry.active_name,
        asset_id=asset_id,
        currency=currency.lower(),
        interval=interval,
        items=items,
    )
