#!/usr/bin/env python3
"""R1b diagnostic — is there an Aster SPOT market for the reserve assets?

READ ONLY. Unauthenticated public GET requests only. No order, no funds, no key.

Checks, for BTC / ETH / BNB / SOL / TRX:
  * whether Aster publishes a SPOT market (tries the known public base URLs);
  * whether Aster publishes a PERP market (the one the app already wires).

Usage:
    backend\\.venv\\Scripts\\python.exe -m backend.scripts.aster_spot_probe
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import httpx

ASSETS = ["BTC", "ETH", "BNB", "SOL", "TRX"]
QUOTES = ["USDT", "USDC", "USD"]

# Candidate public, unauthenticated exchange-info endpoints. Aster's futures host
# is the one already configured in the app; the spot host is not, so we probe a
# few documented/observed variants and report what actually answers.
SPOT_CANDIDATES = [
    "https://sapi.asterdex.com/api/v1/exchangeInfo",
    "https://sapi.asterdex.com/api/v3/exchangeInfo",
    "https://api.asterdex.com/api/v1/exchangeInfo",
    "https://spot.asterdex.com/api/v1/exchangeInfo",
]
PERP_CANDIDATES = [
    "https://fapi.asterdex.com/fapi/v3/exchangeInfo",
    "https://fapi.asterdex.com/fapi/v1/exchangeInfo",
]

HEADERS = {"User-Agent": "CryptoSentinel-R1b-probe/1.0"}


async def _get_json(url: str) -> tuple[int, Any]:
    async with httpx.AsyncClient(timeout=15.0, headers=HEADERS, follow_redirects=True) as c:
        r = await c.get(url)
        body: Any
        try:
            body = r.json()
        except Exception:
            body = r.text[:300]
        return r.status_code, body


def _symbols(payload: Any) -> list[dict]:
    if isinstance(payload, dict) and isinstance(payload.get("symbols"), list):
        return [s for s in payload["symbols"] if isinstance(s, dict)]
    return []


def _match(symbols: list[dict], asset: str) -> list[str]:
    found = []
    for s in symbols:
        base = str(s.get("baseAsset", "")).upper()
        sym = str(s.get("symbol", "")).upper()
        status = str(s.get("status", "")).upper()
        if base == asset or sym.startswith(asset):
            for q in QUOTES:
                if sym == f"{asset}{q}" and status in ("TRADING", ""):
                    found.append(sym)
    return sorted(set(found))


async def _probe(label: str, candidates: list[str]) -> tuple[str | None, list[dict]]:
    for url in candidates:
        try:
            code, body = await _get_json(url)
        except Exception as exc:  # noqa: BLE001 - diagnostic
            print(f"  [{label}] {url} -> ERROR {type(exc).__name__}")
            continue
        syms = _symbols(body)
        if code == 200 and syms:
            print(f"  [{label}] {url} -> 200, {len(syms)} symbols")
            return url, syms
        snippet = body if isinstance(body, str) else str(body)[:120]
        print(f"  [{label}] {url} -> {code}, no symbol list ({snippet})")
    return None, []


async def main() -> int:
    print("\n" + "=" * 60)
    print("  Aster reserve-asset probe (R1b) — READ ONLY")
    print("=" * 60 + "\n")

    print("SPOT endpoints:")
    spot_url, spot_syms = await _probe("spot", SPOT_CANDIDATES)
    print("\nPERP endpoints:")
    perp_url, perp_syms = await _probe("perp", PERP_CANDIDATES)

    print("\n" + "-" * 60)
    print(f"{'asset':<8}{'spot':<26}{'perp':<26}")
    print("-" * 60)
    for a in ASSETS:
        spot_hit = ", ".join(_match(spot_syms, a)) if spot_syms else "?"
        perp_hit = ", ".join(_match(perp_syms, a)) if perp_syms else "?"
        print(f"{a:<8}{spot_hit or '—':<26}{perp_hit or '—':<26}")
    print("-" * 60)
    print(f"\nspot source: {spot_url or 'NONE REACHABLE'}")
    print(f"perp source: {perp_url or 'NONE REACHABLE'}\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
