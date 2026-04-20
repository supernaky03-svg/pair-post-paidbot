from __future__ import annotations

from app.core.config import settings
from app.core.constants import KEYWORD_MODES
from app.core.exceptions import ValidationError
from app.db.repositories import PairRepo, SettingsRepo, UserRepo
from app.domain.models import PairRecord
from app.services.source_registry import SourceRegistryService
from app.telegram.entity import resolve_source, resolve_target


class PairService:
    def __init__(self) -> None:
        self.pairs = PairRepo()
        self.users = UserRepo()
        self.settings = SettingsRepo()
        self.sources = SourceRegistryService()

    async def get_pair_limit(self, user_id: int) -> int:
        user = await self.users.get(user_id)
        if user and user.pair_limit_override:
            return user.pair_limit_override
        global_settings = await self.settings.get_json("pair_limit", {"value": settings.default_pair_limit})
        return int(global_settings.get("value", settings.default_pair_limit))

    async def next_pair_no(self, user_id: int) -> int:
        pairs = await self.pairs.list_for_user(user_id)
        current = {p.pair_no for p in pairs}
        candidate = 1
        while candidate in current:
            candidate += 1
        return candidate

    async def validate_pair_no(self, user_id: int, pair_no: int, *, creating: bool) -> None:
        pair = await self.pairs.get(user_id, pair_no)
        if creating and pair and pair.active:
            raise ValidationError("That pair number already exists.")
        if not creating and (not pair or not pair.active):
            raise ValidationError("Pair not found.")

    async def validate_source_reuse(self, user_id: int, source_key: str, *, ignore_pair_no: int | None = None) -> None:
        pairs = await self.pairs.list_for_user(user_id)
        count = sum(1 for p in pairs if p.source_key == source_key and p.pair_no != ignore_pair_no)
        if count >= 3:
            raise ValidationError(
                "The same source can only be used in up to 3 pairs. Too many same-source pairs may cause posting errors."
            )

    def parse_scan_count(self, raw: str) -> int | None:
        raw = raw.strip().lower()
        if raw == "all":
            return None
        if not raw:
            return settings.default_scan_count
        try:
            value = int(raw)
        except ValueError as exc:
            raise ValidationError("Scan amount must be a positive number or all.") from exc
        if value <= 0:
            raise ValidationError("Scan amount must be a positive number or all.")
        return value

    def normalize_keywords(self, raw: str) -> list[str]:
        return sorted({part.strip().lower() for part in raw.split(",") if part.strip()})

    def normalize_ads(self, raw: str) -> list[str]:
        if raw.strip().lower() == "skip":
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    async def build_pair(
        self,
        *,
        user_id: int,
        pair_no: int,
        source_input: str,
        scan_count: int | None,
        target_input: str,
        ads: list[str],
        post_rule: bool,
        forward_rule: bool,
        generation: int = 1,
    ) -> PairRecord:
        await self.validate_pair_no(user_id, pair_no, creating=True)
        pair_limit = await self.get_pair_limit(user_id)
        active_pairs = await self.pairs.list_for_user(user_id)
        if len(active_pairs) >= pair_limit:
            raise ValidationError(f"Pair limit exceeded. Your limit is {pair_limit}.")
        resolved_source = await resolve_source(source_input)
        await self.validate_source_reuse(user_id, resolved_source.source_key)
        target_entity = await resolve_target(target_input)
        pair = PairRecord(
            user_id=user_id,
            pair_no=pair_no,
            source_input=source_input,
            source_key=resolved_source.source_key,
            source_kind=resolved_source.source_kind,
            target_input=target_input,
            target_chat_id=getattr(target_entity, "id", None),
            target_title=getattr(target_entity, "title", None),
            scan_count=scan_count,
            forward_rule=forward_rule,
            post_rule=post_rule,
            ads=ads,
            generation=generation,
        )
        await self.pairs.save(pair)
        await self.sources.attach_source(pair, resolved_source)
        return pair

    async def delete_pair(self, user_id: int, pair_no: int) -> PairRecord:
        pair = await self.pairs.get(user_id, pair_no)
        if not pair or not pair.active:
            raise ValidationError("Pair not found.")
        await self.pairs.deactivate(user_id, pair_no)
        try:
            old_entity = (await resolve_source(pair.source_input)).entity
        except Exception:
            old_entity = None
        await self.sources.detach_source_if_unused(pair.source_key, old_entity)
        return pair

    async def update_source(self, user_id: int, pair_no: int, source_input: str, scan_count: int | None) -> PairRecord:
        pair = await self.pairs.get(user_id, pair_no)
        if not pair or not pair.active:
            raise ValidationError("Pair not found.")
        old_source_key = pair.source_key
        old_source_input = pair.source_input
        resolved_source = await resolve_source(source_input)
        await self.validate_source_reuse(user_id, resolved_source.source_key, ignore_pair_no=pair_no)
        pair.source_input = source_input
        pair.source_key = resolved_source.source_key
        pair.source_kind = resolved_source.source_kind
        pair.scan_count = scan_count
        pair.last_processed_id = 0
        pair.recent_sent_ids = []
        await self.pairs.save(pair)
        await self.sources.attach_source(pair, resolved_source)
        if old_source_key != pair.source_key:
            try:
                old_entity = (await resolve_source(old_source_input)).entity
            except Exception:
                old_entity = None
            await self.sources.detach_source_if_unused(old_source_key, old_entity)
        return pair

    async def update_target(self, user_id: int, pair_no: int, target_input: str) -> PairRecord:
        pair = await self.pairs.get(user_id, pair_no)
        if not pair or not pair.active:
            raise ValidationError("Pair not found.")
        target_entity = await resolve_target(target_input)
        pair.target_input = target_input
        pair.target_chat_id = getattr(target_entity, "id", None)
        pair.target_title = getattr(target_entity, "title", None)
        await self.pairs.save(pair)
        return pair

    async def update_keywords(self, user_id: int, pair_no: int, mode: str, values: list[str]) -> PairRecord:
        pair = await self.pairs.get(user_id, pair_no)
        if not pair or not pair.active:
            raise ValidationError("Pair not found.")
        if mode not in KEYWORD_MODES:
            raise ValidationError("Invalid keyword mode.")
        pair.keyword_mode = mode
        pair.keyword_values = values
        if not values:
            pair.keyword_mode = "off"
        await self.pairs.save(pair)
        return pair

    async def clear_selected_keywords(self, user_id: int, pair_no: int, values: list[str]) -> PairRecord:
        pair = await self.pairs.get(user_id, pair_no)
        if not pair or not pair.active:
            raise ValidationError("Pair not found.")
        lowered = {value.lower() for value in values}
        pair.keyword_values = [value for value in pair.keyword_values if value.lower() not in lowered]
        if not pair.keyword_values:
            pair.keyword_mode = "off"
        await self.pairs.save(pair)
        return pair

    async def update_ads(self, user_id: int, pair_no: int, ads: list[str]) -> PairRecord:
        pair = await self.pairs.get(user_id, pair_no)
        if not pair or not pair.active:
            raise ValidationError("Pair not found.")
        pair.ads = ads
        await self.pairs.save(pair)
        return pair

    async def update_rule(self, user_id: int, pair_no: int, *, field_name: str, value: bool) -> PairRecord:
        pair = await self.pairs.get(user_id, pair_no)
        if not pair or not pair.active:
            raise ValidationError("Pair not found.")
        if field_name == "post_rule":
            pair.post_rule = value
        elif field_name == "forward_rule":
            pair.forward_rule = value
        else:
            raise ValidationError("Unknown rule.")
        await self.pairs.save(pair)
        return pair
