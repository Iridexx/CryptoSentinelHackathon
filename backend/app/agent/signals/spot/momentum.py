"""Spot momentum and price-structure signal namespace."""

from backend.app.agent.signals.base import SignalModule, SignalPayload, SignalResult


class SpotMomentumSignal(SignalModule[SignalPayload, SignalResult]):
    """Placeholder for Spot V1 momentum, VWAP, ATR, and relative volume scoring."""

    name = "spot_momentum_v1"

    async def evaluate(self, payload: SignalPayload) -> SignalResult:
        raise NotImplementedError("Spot momentum evaluation is implemented in Step 6.")
