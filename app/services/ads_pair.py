from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from app.core.exceptions import ValidationError
from app.db.repositories import AdsPairRepo
from app.domain.models import AdsPairRecord
from app.services.repost_logic import runtime_cache
from app.core.constants import SOURCE_KIND_ID, SOURCE_KIND_PRIVATE, SOURCE_KIND_PUBLIC
from app.telegram.entity import (
    build_source_key,
    describe_target,
    extract_invite_hash,
    normalize_public_source,
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AdsPairService:
    def __init__(self) -> None:
        self.ads_pairs = AdsPairRepo()

    def parse_delay_seconds(self, raw: str | None) -> int:
        value = (raw or "1h").strip().lower()
        match = re.fullmatch(r"(\d+)([hm])", value)
        if not match:
            raise ValidationError("Delay format မှားနေပါတယ်။ ဥပမာ 1h / 30m / 1m")
        amount = int(match.group(1))
        unit = match.group(2)
        seconds = amount * 3600 if unit == "h" else amount * 60
        if seconds < 60:
            raise ValidationError("Delay အနည်းဆုံး 1m ဖြစ်ရမယ်။")
        return seconds

    def parse_scan_count(self, raw: str | None) -> int:
        if raw is None or raw.strip() == "":
            return 0
        try:
            value = int(raw.strip())
        except ValueError as exc:
            raise ValidationError("Scan count သည် 0 သို့မဟုတ် positive number ဖြစ်ရမယ်။") from exc
        if value < 0:
            raise ValidationError("Scan count သည် 0 သို့မဟုတ် positive number ဖြစ်ရမယ်။")
        return value

    def format_delay(self, seconds: int) -> str:
        if seconds % 3600 == 0:
            return f"{seconds // 3600}h"
        if seconds % 60 == 0:
            return f"{seconds // 60}m"
        return f"{seconds}s"

    async def create_ads_pair(
        self,
        *,
        user_id: int,
        pair_no: int,
        delay_seconds: int,
        scan_count: int,
        source_input: str,
        target_input: str,
    ) -> AdsPairRecord:
        existing = await self.ads_pairs.get(user_id, pair_no)
        if existing and existing.active:
            raise ValidationError(f"Ads Pair #{pair_no} ရှိပြီးသားပါ။ Ads pair ချင်း pair number တူလို့မရပါ။")

        raw_source = source_input.strip()
        invite_hash = extract_invite_hash(raw_source)

        if invite_hash:
            source_kind = SOURCE_KIND_PRIVATE
            normalized_source = invite_hash
        elif raw_source.lstrip("-").isdigit():
            source_kind = SOURCE_KIND_ID
            normalized_source = raw_source
        else:
            normalized_source = normalize_public_source(raw_source)
            if not normalized_source:
                raise ValidationError("Source link မှားနေပါတယ်။")
            source_kind = SOURCE_KIND_PUBLIC

        source_key = build_source_key(source_kind, normalized_source)
        target_ref = describe_target(target_input)

        pair = AdsPairRecord(
            user_id=user_id,
            pair_no=pair_no,
            source_input=source_input,
            source_key=source_key,
            source_kind=source_kind,
            target_input=target_input,
            target_key=target_ref.target_key,
            target_chat_id=None,
            target_title=None,
            delay_seconds=delay_seconds,
            scan_count=scan_count,
            last_processed_id=0,
            recent_sent_ids=[],
            next_send_at=utcnow(),
            active=True,
        )
        await self.ads_pairs.save(pair)
        runtime_cache.clear_ads_pair(user_id, pair_no)
        return pair

    async def delete_ads_pair(self, user_id: int, pair_no: int) -> AdsPairRecord:
        pair = await self.ads_pairs.get(user_id, pair_no)
        if not pair or not pair.active:
            raise ValidationError(f"Ads Pair #{pair_no} မတွေ့ပါ။")
        await self.ads_pairs.deactivate(user_id, pair_no)
        runtime_cache.clear_ads_pair(user_id, pair_no)
        return pair

    async def update_delay(self, user_id: int, pair_no: int, delay_seconds: int) -> AdsPairRecord:
        pair = await self.ads_pairs.get(user_id, pair_no)
        if not pair or not pair.active:
            raise ValidationError(f"Ads Pair #{pair_no} မတွေ့ပါ။ ဒီ pair သည် Ads Pair မဟုတ်ပါ။")
        pair.delay_seconds = delay_seconds
        pair.next_send_at = utcnow()
        await self.ads_pairs.save(pair)
        runtime_cache.clear_ads_pair(user_id, pair_no)
        return pair