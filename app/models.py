
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


SCAN_COUNT_ALL = -1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class UserRecord:
    telegram_user_id: int
    username: str | None = None
    is_banned: bool = False
    language: str = "en"
    database_channel_id: int | None = None
    database_channel_link: str | None = None
    access_expires_at: datetime | None = None
    pair_limit: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_otp_used: str | None = None
    restore_mode: str | None = None
    reset_version: int = 0
    reset_at: datetime | None = None

    def has_access(self) -> bool:
        return bool(self.access_expires_at and self.access_expires_at > utc_now())

    def effective_pair_limit(self, global_limit: int) -> int:
        return int(self.pair_limit or global_limit)

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "UserRecord":
        return cls(**row)


@dataclass(slots=True)
class PairRecord:
    owner_user_id: int
    pair_id: int
    source_id: str
    target_id: str
    source_chat_id: int | None = None
    target_chat_id: int | None = None
    last_processed_id: int = 0
    recent_sent_ids: List[int] = field(default_factory=list)
    forward_rule: bool = False
    post_rule: bool = True
    scan_amount: int = 100
    ads_links: List[str] = field(default_factory=list)
    ban_keywords: List[str] = field(default_factory=list)
    post_keywords: List[str] = field(default_factory=list)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "PairRecord":
        return cls(**row)

    def source_queue_key(self) -> str:
        return str(self.source_chat_id or self.source_id)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "owner_user_id": self.owner_user_id,
            "pair_id": self.pair_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "source_chat_id": self.source_chat_id,
            "target_chat_id": self.target_chat_id,
            "last_processed_id": self.last_processed_id,
            "recent_sent_ids": list(self.recent_sent_ids),
            "forward_rule": self.forward_rule,
            "post_rule": self.post_rule,
            "scan_amount": self.scan_amount,
            "ads_links": list(self.ads_links),
            "ban_keywords": list(self.ban_keywords),
            "post_keywords": list(self.post_keywords),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class OTPRecord:
    key: str
    duration_value: int
    duration_unit: str
    created_by_admin: int
    created_at: datetime | None = None
    used_by_user_id: int | None = None
    used_at: datetime | None = None
    is_used: bool = False

    @classmethod
    def from_row(cls, row: Dict[str, Any]) -> "OTPRecord":
        return cls(**row)
