#!/usr/bin/env python3
"""CLI per testare la connessione Aster senza avviare il server.

Uso:
    python -m backend.scripts.aster_test
"""

from __future__ import annotations

import asyncio
import sys

from backend.app.core.config import get_settings
from backend.app.execution.venues.aster.diagnostics import run_connection_test

STATUS_ICON = {"OK": "✅", "WARNING": "⚠️", "ERROR": "❌", "CRITICAL": "🚫"}


async def main() -> int:
    cfg = get_settings()
    report = await run_connection_test(cfg)

    print(f"\n{'=' * 50}")
    print(f"  Aster Connection Test — {STATUS_ICON.get(report.overall, '?')} {report.overall}")
    print(f"{'=' * 50}\n")

    for i, check in enumerate(report.checks, 1):
        icon = STATUS_ICON.get(check.status, "?")
        print(f"  {i}. {icon} [{check.status:>8}] {check.message}")

    print()
    return 0 if report.overall == "OK" else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
