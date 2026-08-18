"""Aster connection diagnostics and wallet view — read-only endpoints.

Admin-only for the connection test; read-access for the wallet view.
"""

from __future__ import annotations

from fastapi import APIRouter

from backend.app.api.dependencies import AdminAccessDep, ReadAccessDep, SettingsDep
from backend.app.execution.venues.aster.diagnostics import run_connection_test
from backend.app.execution.venues.aster.wallet import get_wallet_view

router = APIRouter(prefix="/api/v1/aster", tags=["aster"])


@router.get("/wallet")
async def aster_wallet(settings: SettingsDep, _: ReadAccessDep) -> dict:
    """Aster addresses and balance for the Wallet screen — read-only."""
    view = await get_wallet_view(settings)
    return view.to_dict()


@router.post("/connection-test")
async def aster_connection_test(settings: SettingsDep, _: AdminAccessDep) -> dict:
    """Run the read-only Aster diagnostic and return the per-check outcome."""
    report = await run_connection_test(settings)
    return report.to_dict()
