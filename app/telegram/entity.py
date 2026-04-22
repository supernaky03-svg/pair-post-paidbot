from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from telethon.errors import (
    InviteHashEmptyError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    InviteRequestSentError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

from app.core.constants import SOURCE_KIND_ID, SOURCE_KIND_PRIVATE, SOURCE_KIND_PUBLIC
from app.core.exceptions import SourceResolveError, ValidationError
from app.telegram.safe_ops import safe_get_entity, with_floodwait
from app.telegram.shared_client import client

INVITE_RE = re.compile(r"(?i)(?:https?://)?(?:t\.me|telegram\.me)/(?:joinchat/|\+)([A-Za-z0-9_-]+)")
TG_JOIN_RE = re.compile(r"(?i)tg://join\?invite=([A-Za-z0-9_-]+)")


@dataclass(slots=True)
class ResolvedSource:
    source_input: str
    source_key: str
    source_kind: str
    normalized_value: str
    invite_hash: str | None
    entity: object
    joined_by_shared_session: bool
    chat_id: int | None
    title: str | None


@dataclass(slots=True)
class TargetReference:
    target_input: str
    target_key: str
    target_kind: str
    normalized_value: str
    invite_hash: str | None


@dataclass(slots=True)
class ResolvedTarget:
    target_input: str
    target_key: str
    target_kind: str
    normalized_value: str
    invite_hash: str | None
    entity: object
    joined_by_shared_session: bool
    chat_id: int | None
    title: str | None


def extract_invite_hash(text: str) -> str | None:
    text = text.strip()
    m = INVITE_RE.search(text) or TG_JOIN_RE.search(text)
    return m.group(1) if m else None


def normalize_public_source(raw: str) -> str:
    raw = raw.strip()
    raw = raw.replace("https://t.me/", "").replace("http://t.me/", "").replace("t.me/", "")
    raw = raw.lstrip("@").strip("/")
    return raw


def normalize_public_target(raw: str) -> str:
    return normalize_public_source(raw)


def build_source_key(source_kind: str, normalized_value: str) -> str:
    return hashlib.sha256(f"{source_kind}:{normalized_value}".encode()).hexdigest()


def build_target_key(target_kind: str, normalized_value: str) -> str:
    return hashlib.sha256(f"target:{target_kind}:{normalized_value}".encode()).hexdigest()


def describe_target(raw: str) -> TargetReference:
    raw = raw.strip()
    invite_hash = extract_invite_hash(raw)
    if invite_hash:
        return TargetReference(
            target_input=raw,
            target_key=build_target_key(SOURCE_KIND_PRIVATE, invite_hash),
            target_kind=SOURCE_KIND_PRIVATE,
            normalized_value=invite_hash,
            invite_hash=invite_hash,
        )

    if raw.lstrip("-").isdigit():
        return TargetReference(
            target_input=raw,
            target_key=build_target_key(SOURCE_KIND_ID, raw),
            target_kind=SOURCE_KIND_ID,
            normalized_value=raw,
            invite_hash=None,
        )

    public_value = normalize_public_target(raw)
    if not public_value:
        raise ValidationError("Empty target.")
    return TargetReference(
        target_input=raw,
        target_key=build_target_key(SOURCE_KIND_PUBLIC, public_value),
        target_kind=SOURCE_KIND_PUBLIC,
        normalized_value=public_value,
        invite_hash=None,
    )


async def resolve_source(raw: str) -> ResolvedSource:
    raw = raw.strip()
    invite_hash = extract_invite_hash(raw)
    if invite_hash:
        try:
            updates = await with_floodwait(client.__call__, ImportChatInviteRequest(invite_hash))
            chat = getattr(updates, "chats", [None])[0]
            entity = await safe_get_entity(chat or raw)
            return ResolvedSource(
                source_input=raw,
                source_key=build_source_key(SOURCE_KIND_PRIVATE, invite_hash),
                source_kind=SOURCE_KIND_PRIVATE,
                normalized_value=invite_hash,
                invite_hash=invite_hash,
                entity=entity,
                joined_by_shared_session=True,
                chat_id=getattr(entity, "id", None),
                title=getattr(entity, "title", None),
            )
        except UserAlreadyParticipantError:
            entity = await safe_get_entity(raw)
            return ResolvedSource(
                raw,
                build_source_key(SOURCE_KIND_PRIVATE, invite_hash),
                SOURCE_KIND_PRIVATE,
                invite_hash,
                invite_hash,
                entity,
                True,
                getattr(entity, "id", None),
                getattr(entity, "title", None),
            )
        except (InviteHashEmptyError, InviteHashExpiredError, InviteHashInvalidError, InviteRequestSentError) as exc:
            raise SourceResolveError(f"Invalid private invite link: {exc}") from exc

    if raw.lstrip("-").isdigit():
        entity = await safe_get_entity(int(raw))
        return ResolvedSource(
            source_input=raw,
            source_key=build_source_key(SOURCE_KIND_ID, raw),
            source_kind=SOURCE_KIND_ID,
            normalized_value=raw,
            invite_hash=None,
            entity=entity,
            joined_by_shared_session=False,
            chat_id=getattr(entity, "id", None),
            title=getattr(entity, "title", None),
        )

    public_value = normalize_public_source(raw)
    if not public_value:
        raise ValidationError("Empty source.")
    entity = await safe_get_entity(public_value)
    return ResolvedSource(
        source_input=raw,
        source_key=build_source_key(SOURCE_KIND_PUBLIC, public_value),
        source_kind=SOURCE_KIND_PUBLIC,
        normalized_value=public_value,
        invite_hash=None,
        entity=entity,
        joined_by_shared_session=False,
        chat_id=getattr(entity, "id", None),
        title=getattr(entity, "title", None),
    )


async def resolve_target(raw: str):
    ref = describe_target(raw)
    if ref.target_kind == SOURCE_KIND_ID:
        return await safe_get_entity(int(ref.normalized_value))
    if ref.target_kind == SOURCE_KIND_PRIVATE:
        return await safe_get_entity(raw)
    return await safe_get_entity(ref.normalized_value)


async def resolve_and_join_target(raw: str) -> ResolvedTarget:
    ref = describe_target(raw)

    if ref.target_kind == SOURCE_KIND_PRIVATE:
        try:
            updates = await with_floodwait(client.__call__, ImportChatInviteRequest(ref.invite_hash))
            chat = getattr(updates, "chats", [None])[0]
            entity = await safe_get_entity(chat or raw)
            joined = True
        except UserAlreadyParticipantError:
            entity = await safe_get_entity(raw)
            joined = True
        except (InviteHashEmptyError, InviteHashExpiredError, InviteHashInvalidError, InviteRequestSentError) as exc:
            raise ValidationError(f"Invalid private target invite link: {exc}") from exc
    elif ref.target_kind == SOURCE_KIND_PUBLIC:
        try:
            await with_floodwait(client.__call__, JoinChannelRequest(ref.normalized_value))
        except UserAlreadyParticipantError:
            pass
        entity = await safe_get_entity(ref.normalized_value)
        joined = True
    else:
        entity = await safe_get_entity(int(ref.normalized_value))
        joined = False

    return ResolvedTarget(
        target_input=raw,
        target_key=ref.target_key,
        target_kind=ref.target_kind,
        normalized_value=ref.normalized_value,
        invite_hash=ref.invite_hash,
        entity=entity,
        joined_by_shared_session=joined,
        chat_id=getattr(entity, "id", None),
        title=getattr(entity, "title", None),
    )


async def leave_source(entity) -> None:
    await with_floodwait(client.__call__, LeaveChannelRequest(entity))


async def leave_target(entity) -> None:
    await with_floodwait(client.__call__, LeaveChannelRequest(entity))
