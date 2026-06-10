"""Perpetual Volume Profile signal namespace."""

from backend.app.agent.signals.base import SignalModule, SignalPayload, SignalResult


class VolumeProfileSignal(SignalModule[SignalPayload, SignalResult]):
    """Placeholder for rolling 24h Volume Profile with POC, VAH, and VAL."""

    name = "perp_volume_profile_v1"

    async def evaluate(self, payload: SignalPayload) -> SignalResult:
        raise NotImplementedError("Volume Profile evaluation is implemented in Step 6.")
