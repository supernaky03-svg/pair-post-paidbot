
from __future__ import annotations

import re

from telethon.errors import (
    InviteHashEmptyError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    InviteRequestSentError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.messages import ImportChatInviteRequest

from ..core.logging import logger
from ..core.runtime import get_pair_runtime, get_runtime
from ..models import PairRecord
from ..utils.filters import normalize_chat_id
from ..utils.parsing import ParseError, extract_invite_hash
from ..utils.telethon import run_with_floodwait, safe_get_entity


class EntityResolutionError(ValueError):
    pass


async def resolve_entity_from_numeric_id(raw_id: str):
    runtime = get_runtime()
    entity_id = int(raw_id)
    try:
        return await safe_get_entity(entity_id)
    except Exception:
        pass
    try:
        dialogs = await run_with_floodwait(runtime.telethon.get_dialogs, limit=None)
        wanted_id = abs(entity_id)
        for dialog in dialogs:
            entity = getattr(dialog, "entity", None)
            if entity and getattr(entity, "id", None) == wanted_id:
                return entity
    except Exception:
        logger.exception("Failed dialog-based entity lookup for %s", raw_id)
    raise EntityResolutionError(
        "Channel ID could not be resolved. Make sure the linked user account can access that chat."
    )


async def resolve_entity_reference(raw_ref: str, *, allow_join_via_invite: bool = True):
    runtime = get_runtime()
    ref = (raw_ref or "").strip()
    if not ref:
        raise EntityResolutionError("Empty channel reference.")
    if re.fullmatch(r"-?\d+", ref):
        return await resolve_entity_from_numeric_id(ref)

    invite_hash = extract_invite_hash(ref)
    if invite_hash:
        try:
            return await safe_get_entity(ref)
        except Exception:
            if not allow_join_via_invite:
                raise EntityResolutionError("Private invite link could not be resolved.")
            try:
                result = await run_with_floodwait(
                    runtime.telethon,
                    ImportChatInviteRequest(invite_hash),
                )
                chats = list(getattr(result, "chats", []) or [])
                if chats:
                    return chats[0]
            except UserAlreadyParticipantError:
                pass
            except InviteRequestSentError as exc:
                raise EntityResolutionError(
                    "Join request was sent for this invite link. Approve it first, then try again."
                ) from exc
            except (InviteHashEmptyError, InviteHashExpiredError, InviteHashInvalidError) as exc:
                raise EntityResolutionError("Invite link is invalid or expired.") from exc
            except Exception as exc:
                raise EntityResolutionError(
                    "Could not join or resolve this private invite link."
                ) from exc
        try:
            return await safe_get_entity(ref)
        except Exception as exc:
            raise EntityResolutionError("Private invite link could not be resolved.") from exc

    try:
        return await safe_get_entity(ref)
    except Exception as exc:
        raise EntityResolutionError(
            "Channel link, username, or ID could not be resolved."
        ) from exc


async def resolve_pair_entities(pair: PairRecord) -> bool:
    runtime = get_pair_runtime(pair.owner_user_id, pair.pair_id)
    if not pair.source_id or not pair.target_id:
        runtime.source_entity = None
        runtime.target_entity = None
        runtime.source_chat_id = None
        runtime.target_chat_id = None
        return False
    try:
        source_entity = await resolve_entity_reference(pair.source_id, allow_join_via_invite=True)
        target_entity = await resolve_entity_reference(pair.target_id, allow_join_via_invite=True)
        runtime.source_entity = source_entity
        runtime.target_entity = target_entity
        runtime.source_chat_id = normalize_chat_id(getattr(source_entity, "id", None))
        runtime.target_chat_id = normalize_chat_id(getattr(target_entity, "id", None))
        pair.source_chat_id = runtime.source_chat_id
        pair.target_chat_id = runtime.target_chat_id
        return True
    except Exception:
        logger.exception("Failed to resolve entities for user=%s pair=%s", pair.owner_user_id, pair.pair_id)
        runtime.source_entity = None
        runtime.target_entity = None
        runtime.source_chat_id = None
        runtime.target_chat_id = None
        return False


def build_channel_link(channel_id: int) -> str:
    text = str(abs(int(channel_id)))
    if text.startswith("100"):
        text = text[3:]
    return f"https://t.me/c/{text}"
