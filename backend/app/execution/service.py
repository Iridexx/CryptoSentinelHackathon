"""Execution-layer coordination and non-sensitive status."""

from __future__ import annotations

from typing import Any

from web3 import Web3

from backend.app.core.config import Settings, get_settings
from backend.app.execution.perp_registry import PerpExecutionRegistry
from backend.app.execution.registry import ExecutionProviderRegistry
from backend.app.execution.rpc import MultiRpcClient
from backend.app.execution.spot_twak import TwakClient
from backend.app.execution.x402 import X402Client
from backend.app.persistence.database import get_session_factory


class ExecutionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rpc = MultiRpcClient(
            settings.bsc_rpc_urls,
            settings.bsc_rpc_timeout_seconds,
            settings.tatum_rpc_api_key,
        )
        self.competition_rpc = MultiRpcClient(
            settings.competition_rpc_urls,
            settings.bsc_rpc_timeout_seconds,
            settings.tatum_rpc_api_key,
        )
        self.twak = TwakClient(settings)
        self.spot_registry = ExecutionProviderRegistry(settings)
        self.perp_registry = PerpExecutionRegistry(settings)
        self.x402 = X402Client(
            settings,
            self.twak,
            session_factory=lambda: get_session_factory()(),
            user_id=str(settings.default_user_id),
        )

    def status(self) -> dict[str, Any]:
        return {
            "network": self.settings.bsc_network,
            "chain_id": self.settings.bsc_chain_id,
            "testnet_only": True,
            "rpc_endpoint_count": len(self.settings.bsc_rpc_urls),
            "rpc_failover_configured": len(self.settings.bsc_rpc_urls) >= 2,
            "gas_reserve_pct": self.settings.bnb_gas_reserve_pct,
            "gas_reserve_floor_bnb": self.settings.bnb_gas_reserve_min,
            "transaction_attempt_limit": self.settings.bsc_max_transaction_attempts,
            "spot": {
                "active_provider": self.spot_registry.active_name.value,
                "providers": [status.model_dump() for status in self.spot_registry.statuses()],
            },
            "perp": {
                "active_provider": self.perp_registry.active_name.value,
                "providers": [status.model_dump() for status in self.perp_registry.statuses()],
            },
            "x402": {
                "enabled": self.settings.x402_enabled,
                "network": self.settings.x402_network,
                "provider_count": len(self.x402.endpoints),
            },
            "competition": {
                "contract": self.settings.competition_contract_address,
                "chain_id": self.settings.competition_chain_id,
                "rpc_endpoint_count": len(self.settings.competition_rpc_urls),
                "wallet_configured": bool(self.settings.wallet_address),
            },
        }

    async def competition_registration_status(self) -> dict[str, Any]:
        if not self.settings.wallet_address:
            return {"configured": False, "registered": False, "reason": "wallet_address_missing"}
        if not self.settings.competition_contract_address:
            return {"configured": False, "registered": False, "reason": "contract_address_missing"}
        chain_id = int(await self.competition_rpc.call("eth_chainId"), 16)
        if chain_id != self.settings.competition_chain_id:
            raise RuntimeError(
                "Competition RPC chain mismatch: "
                f"expected {self.settings.competition_chain_id}, got {chain_id}"
            )
        selector = Web3.keccak(text="isRegistered(address)")[:4].hex()
        address_word = self.settings.wallet_address.lower().removeprefix("0x").rjust(64, "0")
        result = await self.competition_rpc.call(
            "eth_call",
            [
                {
                    "to": Web3.to_checksum_address(self.settings.competition_contract_address),
                    "data": f"0x{selector}{address_word}",
                },
                "latest",
            ],
        )
        return {
            "configured": True,
            "registered": int(result, 16) != 0,
            "wallet": Web3.to_checksum_address(self.settings.wallet_address),
            "contract": Web3.to_checksum_address(self.settings.competition_contract_address),
            "chain_id": chain_id,
        }


def get_execution_service() -> ExecutionService:
    return ExecutionService(get_settings())
