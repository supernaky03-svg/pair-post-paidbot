from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class UserRecord:
    user_id: int
    username: str | None = None
    full_name: str | None = None
    language: str = "en"
    status: str = "not_activated"
    activated_until: datetime | None = None
    is_banned: bool = False
    pair_limit_override: int | None = None
    needs_restore_choice: bool = False

    @property
    def is_active(self) -> bool:
        return self.status == "activated" and not self.is_banned


@dataclass(slots=True)
class PairRecord:
    user_id: int
    pair_no: int
    source_input: str
    source_key: str
    source_kind: str
    target_input: str
    target_key: str | None = None
    target_chat_id: int | None = None
    target_title: str | None = None
    scan_count: int | None = 100
    last_processed_id: int = 0
    recent_sent_ids: list[int] = field(default_factory=list)
    forward_rule: bool = False
    post_rule: bool = True
    keyword_mode: str = "off"
    keyword_values: list[str] = field(default_factory=list)
    ads: list[str] = field(default_factory=list)
    active: bool = True
    generation: int = 1


@dataclass(slots=True)
class SourceRecord:
    source_key: str
    source_input: str
    source_kind: str
    normalized_value: str
    invite_hash: str | None = None
    joined_by_shared_session: bool = False
    active_pair_reference_count: int = 0
    chat_id: int | None = None
    title: str | None = None
    last_verified_at: datetime | None = None
    last_error: str | None = None


@dataclass(slots=True)
class TargetRecord:
    target_key: str
    target_input: str
    target_kind: str
    normalized_value: str
    invite_hash: str | None = None
    joined_by_shared_session: bool = False
    active_pair_reference_count: int = 0
    chat_id: int | None = None
    title: str | None = None
    last_verified_at: datetime | None = None
    last_error: str | None = None
    last_session_fingerprint: str | None = None


@dataclass(slots=True)
class RuntimePairContext:
    source_entity: Any = None
    target_entity: Any = None
    source_chat_id: int | None = None
    target_chat_id: int | None = None
    last_sent_grouped_ids: set[int] = field(default_factory=set)
  
