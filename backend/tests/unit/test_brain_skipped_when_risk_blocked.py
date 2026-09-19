"""Il brain (Claude) non va interpellato quando il risk manager ha gia' bloccato.

L'esecuzione richiede risk manager E brain: se il rischio dice no la risposta di Claude
non puo' cambiare l'esito. Chiamarlo comunque costa, rallenta la scansione sequenziale e
un errore API metterebbe l'agente in DEGRADED per un segnale gia' scartato.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from backend.app.agent.risk import RiskDecision, RiskManager
from backend.app.agent.service import AgentService
from backend.tests.unit.test_agent_step6 import settings


class _ExplodingBrain:
    """Se viene chiamato, il test fallisce."""

    async def decide(self, *, signal, risk):  # pragma: no cover - non deve girare
        raise AssertionError("Claude non va chiamato quando il risk manager ha gia' bloccato")


class _RecordingBrain:
    def __init__(self) -> None:
        self.calls = 0

    async def decide(self, *, signal, risk):
        self.calls += 1
        from backend.app.agent.brain import BrainDecision

        return BrainDecision(action="approve", confidence=Decimal("0.9"), reasoning="ok"), None


def _service(brain) -> AgentService:
    return AgentService(
        settings(),
        spot_signal=SimpleNamespace(),
        perp_signal=SimpleNamespace(),
        risk_manager=RiskManager(settings()),
        brain=brain,
        spot_registry=SimpleNamespace(),
        perp_registry=SimpleNamespace(),
    )


async def test_brain_is_not_called_when_risk_already_blocked() -> None:
    service = _service(_ExplodingBrain())
    decision = await service._brain_decision(None, {"asset": "X"}, RiskDecision(False, "direction_risk_cap_guard"))
    assert decision.action == "block"
    assert decision.allows_execution is False
    assert "direction_risk_cap_guard" in decision.reasoning


async def test_brain_is_still_called_when_risk_allows() -> None:
    brain = _RecordingBrain()
    service = _service(brain)

    class _Session:  # ApiUsageRepository non viene raggiunto: usage e' None
        pass

    decision = await service._brain_decision(_Session(), {"asset": "X"}, RiskDecision(True, "risk_approved"))
    assert brain.calls == 1
    assert decision.action == "approve"


