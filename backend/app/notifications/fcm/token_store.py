"""Persistent FCM device token registry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import UUID

from backend.app.domain.common.models import DEFAULT_SINGLE_USER_ID


@dataclass
class DeviceTokenRecord:
    """Stored FCM device token record."""

    token_id: str
    token: str
    user_id: str
    platform: str
    device_id: str | None
    app_version: str | None
    locale: str | None
    created_at: str
    updated_at: str


class DeviceTokenStore:
    """File-backed token registry used until database persistence is introduced."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._lock = Lock()
        self._records: dict[str, DeviceTokenRecord] = {}
        self._load()

    @staticmethod
    def token_id_for(token: str) -> str:
        """Return a stable non-secret identifier for a token."""

        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:24]

    def register(
        self,
        token: str,
        user_id: UUID = DEFAULT_SINGLE_USER_ID,
        platform: str = "android",
        device_id: str | None = None,
        app_version: str | None = None,
        locale: str | None = None,
    ) -> DeviceTokenRecord:
        """Add or update a device token."""

        now = datetime.now(UTC).isoformat()
        token_id = self.token_id_for(token)
        with self._lock:
            existing = self._records.get(token_id)
            record = DeviceTokenRecord(
                token_id=token_id,
                token=token,
                user_id=str(user_id),
                platform=platform,
                device_id=device_id,
                app_version=app_version,
                locale=locale,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
            self._records[token_id] = record
            self._save_locked()
            return record

    def remove(self, token: str, user_id: UUID = DEFAULT_SINGLE_USER_ID) -> str:
        """Remove a device token and return its token id."""

        token_id = self.token_id_for(token)
        with self._lock:
            record = self._records.get(token_id)
            if record and record.user_id == str(user_id):
                del self._records[token_id]
                self._save_locked()
            return token_id

    def tokens_for_user(self, user_id: UUID, token_ids: list[str] | None = None) -> list[str]:
        """Return raw FCM tokens for a user, optionally filtered by token id."""

        allowed = set(token_ids) if token_ids else None
        with self._lock:
            return [
                record.token
                for record in self._records.values()
                if record.user_id == str(user_id) and (allowed is None or record.token_id in allowed)
            ]

    def count(self) -> int:
        """Return registered token count."""

        with self._lock:
            return len(self._records)

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            self._records = {
                item["token_id"]: DeviceTokenRecord(**item)
                for item in payload.get("tokens", [])
                if "token_id" in item and "token" in item
            }
        except (OSError, json.JSONDecodeError, TypeError):
            self._records = {}

    def _save_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"tokens": [asdict(record) for record in self._records.values()]}
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
