
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ...core.runtime import cache_user, get_runtime, get_user, list_user_pairs
from ...db.repositories import Repository
from ...services.user_actions import ensure_user_profile
from ...utils.parsing import parse_duration_token

router = Router()


def _is_admin(user_id: int) -> bool:
    return int(user_id) in get_runtime().settings.admin_ids


async def _ensure_admin(message: Message):
    user = await ensure_user_profile(message.from_user)
    if not _is_admin(user.telegram_user_id):
        await message.answer("Admin only.")
        return None
    return user


def _chunk_lines(lines: list[str], limit: int = 3500) -> list[str]:
    chunks: list[str] = []
    current = ""
    for line in lines:
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}".strip()
    if current:
        chunks.append(current)
    return chunks


@router.message(Command("otp"))
async def otp_command(message: Message) -> None:
    admin = await _ensure_admin(message)
    if not admin:
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Usage: /otp 1m somekey")
        return
    try:
        duration_value, duration_unit = parse_duration_token(parts[1])
    except Exception as exc:
        await message.answer(str(exc))
        return
    key = parts[2].strip()
    repo = Repository(get_runtime().db)
    try:
        otp = await repo.create_otp(
            key=key,
            duration_value=duration_value,
            duration_unit=duration_unit,
            created_by_admin=admin.telegram_user_id,
        )
    except Exception as exc:
        await message.answer(f"Failed to create OTP: {exc}")
        return
    await repo.log_admin_action(admin.telegram_user_id, "otp_create", f"{otp.key} {otp.duration_value}{otp.duration_unit}")
    await message.answer(f"OTP created: {otp.key} ({otp.duration_value}{otp.duration_unit})")

@router.message(Command("ban"))
async def ban_command(message: Message) -> None:
    admin = await _ensure_admin(message)
    if not admin:
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /ban <user_id>")
        return
    repo = Repository(get_runtime().db)
    user = await repo.set_user_ban_state(int(parts[1]), True)
    if not user:
        await message.answer("User not found.")
        return
    cache_user(user)
    await repo.log_admin_action(admin.telegram_user_id, "ban", parts[1])
    await message.answer(f"User {parts[1]} banned.")

@router.message(Command("unban"))
async def unban_command(message: Message) -> None:
    admin = await _ensure_admin(message)
    if not admin:
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer("Usage: /unban <user_id>")
        return
    repo = Repository(get_runtime().db)
    user = await repo.set_user_ban_state(int(parts[1]), False)
    if not user:
        await message.answer("User not found.")
        return
    cache_user(user)
    await repo.log_admin_action(admin.telegram_user_id, "unban", parts[1])
    await message.answer(f"User {parts[1]} unbanned.")

@router.message(Command("pair_limit"))
async def pair_limit_command(message: Message) -> None:
    admin = await _ensure_admin(message)
    if not admin:
        return
    parts = (message.text or "").split()
    repo = Repository(get_runtime().db)
    if len(parts) == 2 and parts[1].isdigit():
        value = int(parts[1])
        await repo.set_global_pair_limit(value)
        get_runtime().default_pair_limit = value
        await repo.log_admin_action(admin.telegram_user_id, "pair_limit_global", str(value))
        await message.answer(f"Global default pair limit set to {value}.")
        return
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
        user = await repo.set_user_pair_limit(int(parts[1]), int(parts[2]))
        cache_user(user)
        await repo.log_admin_action(admin.telegram_user_id, "pair_limit_user", f"{parts[1]}={parts[2]}")
        await message.answer(f"User {parts[1]} pair limit set to {parts[2]}.")
        return
    await message.answer("Usage: /pair_limit <limit> OR /pair_limit <user_id> <limit>")

@router.message(Command("info"))
async def info_command(message: Message) -> None:
    admin = await _ensure_admin(message)
    if not admin:
        return
    repo = Repository(get_runtime().db)
    users = await repo.list_users()
    lines = ["Users:"]
    for user in users:
        pair_count = len(list_user_pairs(user.telegram_user_id))
        lines.append(
            f"@{user.username or '-'} | {user.telegram_user_id} | "
            f"db={user.database_channel_link or '-'} | pairs={pair_count} | "
            f"access={'active' if user.has_access() else 'expired'} | "
            f"banned={'yes' if user.is_banned else 'no'}"
        )
    for chunk in _chunk_lines(lines):
        await message.answer(chunk)

@router.message(Command("noti"))
async def noti_command(message: Message) -> None:
    admin = await _ensure_admin(message)
    if not admin:
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage: /noti <message>")
        return
    text = parts[1].strip()
    sent = 0
    failed = 0
    runtime = get_runtime()
    for user in runtime.users.values():
        if user.is_banned:
            continue
        try:
            await runtime.bot.send_message(user.telegram_user_id, text)
            sent += 1
        except Exception:
            failed += 1
    repo = Repository(runtime.db)
    await repo.log_admin_action(admin.telegram_user_id, "broadcast", f"sent={sent},failed={failed}")
    await message.answer(f"Broadcast finished. Sent: {sent}, Failed: {failed}")
