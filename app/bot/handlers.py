from __future__ import annotations

import re
import time
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from app.bot.keyboards import (
    ads_action_keyboard,
    confirm_keyboard,
    hide_reply_keyboard,
    keyword_action_keyboard,
    language_keyboard,
    main_menu,
    pair_picker,
    restore_keyboard,
    rule_keyboard,
    target_admin_keyboard,
    text_step_keyboard,
)
from app.bot.states import (
    AddPairStates,
    AdsStates,
    CheckStates,
    DeletePairStates,
    EditSourceStates,
    EditTargetStates,
    KeywordStates,
    OtpStates,
    RuleStates,
)
from app.core.config import settings
from app.core.constants import BACK_TEXTS, CANCEL_TEXTS
from app.core.exceptions import ValidationError
from app.db.repositories import OtpRepo, PairRepo, SettingsRepo, SourceRepo, UserRepo
from app.domain.models import PairRecord
from app.i18n.translator import t
from app.services.access import AccessService
from app.services.pair import PairService
from app.services.runtime import RuntimeManager
from app.services.tutorial import build_tutorial

router = Router()
runtime_manager = RuntimeManager()
access_service = AccessService()
pair_service = PairService()
pair_repo = PairRepo()
user_repo = UserRepo()
settings_repo = SettingsRepo()
source_repo = SourceRepo()

STATE_BY_NAME = {
    state.state: state
    for state in [
        OtpStates.waiting_otp,
        OtpStates.waiting_restore_choice,
        AddPairStates.waiting_pair_no,
        AddPairStates.waiting_source,
        AddPairStates.waiting_scan,
        AddPairStates.waiting_target,
        AddPairStates.waiting_ads,
        AddPairStates.waiting_post_rule,
        AddPairStates.waiting_forward_rule,
        AddPairStates.waiting_confirm,
        DeletePairStates.waiting_pair_no,
        DeletePairStates.waiting_confirm,
        EditSourceStates.waiting_pair_no,
        EditSourceStates.waiting_source,
        EditSourceStates.waiting_scan,
        EditSourceStates.waiting_confirm,
        EditTargetStates.waiting_pair_no,
        EditTargetStates.waiting_target,
        EditTargetStates.waiting_confirm,
        KeywordStates.waiting_pair,
        KeywordStates.waiting_action,
        KeywordStates.waiting_add_values,
        KeywordStates.waiting_clear_values,
        AdsStates.waiting_action,
        AdsStates.waiting_pair_for_add,
        AdsStates.waiting_pair_for_delete,
        AdsStates.waiting_values,
        AdsStates.waiting_delete_confirm,
        RuleStates.waiting_pair,
        RuleStates.waiting_value,
        CheckStates.waiting_pair,
    ]
}


def _is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def _lang(user) -> str:
    return (getattr(user, "language", None) or settings.language_default or "en").lower()


def _now_ts() -> float:
    return time.time()


def _pair_line(pair: PairRecord) -> str:
    keyword_values = ", ".join(pair.keyword_values) if pair.keyword_values else "-"
    ads_values = ", ".join(pair.ads) if pair.ads else "-"
    scan = "all" if pair.scan_count is None else str(pair.scan_count)
    return (
        f"#{pair.pair_no} | {pair.source_input} -> {pair.target_input}\n"
        f"scan={scan} | keywords={pair.keyword_mode}:{keyword_values} | ads={ads_values}\n"
        f"post_rule={'ON' if pair.post_rule else 'OFF'} | forward_rule={'ON' if pair.forward_rule else 'OFF'}"
    )


def _normalize_target_for_bot(target_input: str) -> str | int:
    value = (target_input or "").strip()
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE)
    if value.lower().startswith("t.me/"):
        value = value[5:]
    value = value.strip("/")
    value = value.split("?", 1)[0]

    if value.startswith("@"):
        return value
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{3,}", value):
        return f"@{value}"
    return target_input.strip()


def _target_admin_warning_text(language: str, target_input: str, *, failed: bool = False) -> str:
    if language == "my":
        base = (
            "Target channel/group မှာ bot ကို admin ပေးဖို့လိုပါတယ်။\n\n"
            f"Target: {target_input}\n\n"
            "Bot ကို target မှာ admin ပေးပြီးမှသာ pair အတည်ပြု/target ပြင်ခြင်းကို ဆက်လုပ်နိုင်မယ်။\n"
            "Admin ပေးပြီးရင် အောက်က ခလုတ်ကိုနှိပ်ပါ။"
        )
        if failed:
            base += "\n\nသတိပေးချက်: Bot က target မှာ admin မဖြစ်သေးပါ။ Target မှာ bot ကို admin ပေးပြီး ထပ်နှိပ်ပါ။"
        return base

    base = (
        "You must give this bot admin rights in the target channel/group before continuing.\n\n"
        f"Target: {target_input}\n\n"
        "Only after the bot is admin in the target can the pair be confirmed or the target edit be confirmed.\n"
        "After giving bot admin, press the button below."
    )
    if failed:
        base += "\n\nWarning: the bot is still not admin in this target. Please give bot admin and try again."
    return base


async def _bot_has_target_admin(bot, target_input: str) -> bool:
    try:
        me = await bot.get_me()
        chat = _normalize_target_for_bot(target_input)
        member = await bot.get_chat_member(chat_id=chat, user_id=me.id)
        return getattr(member, "status", "") in {"administrator", "creator"}
    except Exception:
        return False


def _resolve_step_text(language: str, prompt_key: str | None, prompt_fmt: dict[str, Any] | None, markup_payload: dict[str, Any] | None, *, panel_text: str | None = None) -> str:
    if markup_payload and markup_payload.get("type") == "target_admin_gate":
        return _target_admin_warning_text(language, markup_payload.get("target_input", "-"), failed=bool(markup_payload.get("failed")))
    if panel_text:
        return panel_text
    if prompt_key:
        return t(language, prompt_key, **(prompt_fmt or {}))
    return ""


async def _status_text(user_id: int, language: str) -> str:
    user = await user_repo.get(user_id)
    assert user is not None
    pairs = await pair_repo.list_for_user(user_id)
    warnings: list[str] = []
    runtime_warning = runtime_manager.runtime_warning()
    if runtime_warning:
        warnings.append(runtime_warning)
    lines = [
        f"{t(language, 'summary_status')}: {user.status}",
        f"{t(language, 'summary_expiry')}: {user.activated_until or '-'}",
        f"{t(language, 'summary_pair_count')}: {len(pairs)}",
        f"{t(language, 'summary_pair_limit')}: {await pair_service.get_pair_limit(user_id)}",
        f"{t(language, 'status_warning_runtime')}: {warnings[0] if warnings else t(language, 'status_warning_none')}",
    ]
    if not pairs:
        lines.append(t(language, "status_no_pairs"))
    else:
        for pair in pairs:
            lines.append("")
            lines.append(_pair_line(pair))
    return "\n".join(lines)


async def _send(target: Message | CallbackQuery, text: str, reply_markup=None) -> None:
    if isinstance(target, Message):
        await target.answer(text, reply_markup=reply_markup)
    else:
        await target.message.answer(text, reply_markup=reply_markup)


def _editable_markup(reply_markup) -> bool:
    return reply_markup is None or isinstance(reply_markup, InlineKeyboardMarkup)


async def _create_panel(target: Message | CallbackQuery, text: str, reply_markup=None) -> tuple[int, int]:
    if isinstance(target, Message):
        sent = await target.answer(text, reply_markup=reply_markup, disable_web_page_preview=True)
    else:
        sent = await target.message.answer(text, reply_markup=reply_markup, disable_web_page_preview=True)
    return sent.chat.id, sent.message_id


async def _edit_panel(bot, chat_id: int, message_id: int, text: str, reply_markup=None) -> bool:
    if not _editable_markup(reply_markup):
        return False
    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )
        return True
    except Exception:
        return False


async def _show_step(target: Message | CallbackQuery, state: FSMContext, text: str, reply_markup=None, *, reset_panel: bool = False) -> None:
    if reset_panel:
        await state.update_data(panel_chat_id=None, panel_message_id=None)
    data = await state.get_data()
    chat_id = data.get('panel_chat_id')
    message_id = data.get('panel_message_id')

    bot = target.bot if isinstance(target, Message) else target.message.bot
    if chat_id and message_id and _editable_markup(reply_markup):
        if await _edit_panel(bot, chat_id, message_id, text, reply_markup):
            return

    chat_id, message_id = await _create_panel(target, text, reply_markup)
    await state.update_data(panel_chat_id=chat_id, panel_message_id=message_id)


async def _cleanup_user_message(message: Message) -> None:
    try:
        await message.delete()
    except Exception:
        pass


async def _sync_reply_keyboard(target: Message | CallbackQuery, reply_markup) -> None:
    if isinstance(target, Message):
        await target.answer(" ", reply_markup=reply_markup)
    else:
        await target.message.answer(" ", reply_markup=reply_markup)


async def _remove_main_menu(target: Message | CallbackQuery) -> None:
    await _sync_reply_keyboard(target, hide_reply_keyboard())


async def _show_main_menu(target: Message | CallbackQuery, language: str) -> None:
    text = t(language, "main_menu_ready")
    if isinstance(target, Message):
        await target.answer(text, reply_markup=main_menu(language))
    else:
        await target.message.answer(text, reply_markup=main_menu(language))


async def _restore_main_menu(target: Message | CallbackQuery, language: str) -> None:
    text = "Main menu restored." if language != "my" else "Main menu ပြန်ပေါ်ပါပြီ။"
    if isinstance(target, Message):
        await target.answer(text, reply_markup=main_menu(language))
    else:
        await target.message.answer(text, reply_markup=main_menu(language))


async def _sync_idle_keyboard_for_user(target: Message | CallbackQuery, user_id: int, language: str) -> None:
    user = await user_repo.get(user_id)
    if user and user.status == "activated" and not user.is_banned:
        await _show_main_menu(target, language)
    else:
        await _remove_main_menu(target)


async def _render_markup(user_id: int, language: str, payload: dict[str, Any] | None):
    payload = payload or {"type": "main"}
    kind = payload.get("type")

    if kind == "main":
        return None
    if kind == "language":
        return language_keyboard()
    if kind == "restore":
        return restore_keyboard(language)
    if kind == "flow_nav":
        return text_step_keyboard(payload.get("prefix", "flow"), language)
    if kind == "add_post_rule":
        return rule_keyboard("add_post", language)
    if kind == "add_forward_rule":
        return rule_keyboard("add_forward", language)
    if kind == "target_admin_gate":
        return target_admin_keyboard(payload.get("prefix", "target_admin"), language)
    if kind == "pair_confirm":
        return confirm_keyboard("pair_confirm", language)
    if kind == "delete_confirm":
        return confirm_keyboard("pair_delete", language)
    if kind == "edit_source_confirm":
        return confirm_keyboard("edit_source_confirm", language)
    if kind == "edit_target_confirm":
        return confirm_keyboard("edit_target_confirm", language)
    if kind == "keyword_actions":
        return keyword_action_keyboard(language)
    if kind == "ads_actions":
        return ads_action_keyboard(language)
    if kind == "rule_value":
        prefix = payload.get("prefix", "set_rule")
        return rule_keyboard(prefix, language)
    if kind == "pair_picker":
        pairs = await pair_repo.list_for_user(user_id)
        return pair_picker(payload["prefix"], pairs, language, include_all=bool(payload.get("include_all")))
    if kind == "ads_delete_confirm":
        return confirm_keyboard("ads_delete_confirm", language)
    return None


async def _set_step(
    state: FSMContext,
    state_obj,
    *,
    prompt_key: str,
    markup_payload: dict[str, Any] | None,
    remember: bool = True,
    panel_text: str | None = None,
    **fmt,
) -> None:
    current_state = await state.get_state()
    data = await state.get_data()
    history = data.get("history", [])

    if remember and current_state and data.get("current_prompt_key"):
        history.append(
            {
                "state": current_state,
                "prompt_key": data.get("current_prompt_key"),
                "prompt_fmt": data.get("current_prompt_fmt", {}),
                "markup_payload": data.get("current_markup_payload", {"type": "main"}),
                "panel_text": data.get("current_panel_text"),
            }
        )

    await state.set_state(state_obj)
    await state.update_data(
        history=history,
        current_prompt_key=prompt_key,
        current_prompt_fmt=fmt,
        current_markup_payload=markup_payload or {"type": "main"},
        current_panel_text=panel_text,
        last_activity=_now_ts(),
    )


async def _go_back(target: Message | CallbackQuery, state: FSMContext, language: str, user_id: int) -> None:
    data = await state.get_data()
    history = data.get("history", [])

    if not history:
        await state.clear()
        await _sync_idle_keyboard_for_user(target, user_id, language)
        await _show_step(target, state, t(language, "cancelled"), reply_markup=None, reset_panel=True)
        return

    previous = history.pop()
    state_name = previous["state"]
    state_obj = STATE_BY_NAME.get(state_name)

    if not state_obj:
        await state.clear()
        await _sync_idle_keyboard_for_user(target, user_id, language)
        await _show_step(target, state, t(language, "cancelled"), reply_markup=None, reset_panel=True)
        return

    await state.set_state(state_obj)
    await state.update_data(
        history=history,
        current_prompt_key=previous.get("current_prompt_key") or previous.get("prompt_key"),
        current_prompt_fmt=previous.get("prompt_fmt", {}),
        current_markup_payload=previous.get("markup_payload", {"type": "main"}),
        last_activity=_now_ts(),
    )

    markup = await _render_markup(user_id, language, previous.get("markup_payload"))
    await _show_step(
        target,
        state,
        t(language, previous.get("prompt_key") or previous.get("current_prompt_key"), **previous.get("prompt_fmt", {})),
        reply_markup=markup,
    )


async def _cancel_flow(target: Message | CallbackQuery, state: FSMContext, language: str, user_id: int) -> None:
    await state.clear()
    await _show_step(target, state, t(language, "cancelled"), reply_markup=None, reset_panel=True)
    user = await user_repo.get(user_id)
    if user and user.status == "activated" and not user.is_banned:
        await _restore_main_menu(target, language)
    else:
        await _remove_main_menu(target)


async def _ensure_timeout(target: Message | CallbackQuery, state: FSMContext, language: str) -> bool:
    current_state = await state.get_state()
    if not current_state:
        return True

    data = await state.get_data()
    last_activity = data.get("last_activity")

    if last_activity and (_now_ts() - float(last_activity)) > settings.flow_timeout_minutes * 60:
        await state.clear()
        await _sync_idle_keyboard_for_user(target, target.from_user.id, language)
        await _show_step(target, state, t(language, "flow_timeout"), reply_markup=None, reset_panel=True)
        return False

    await state.update_data(last_activity=_now_ts())
    return True


async def _ensure_access_message(message: Message, state: FSMContext):
    user = await access_service.ensure_user(message.from_user)
    if not await _ensure_timeout(message, state, _lang(user)):
        return None

    allowed, reason = await access_service.can_use_features(user)
    if allowed:
        return user

    await state.clear()

    if user.status != "activated":
        await _remove_main_menu(message)
        await _show_step(message, state, reason, reply_markup=language_keyboard(), reset_panel=True)
        await state.set_state(OtpStates.waiting_otp)
        await state.update_data(last_activity=_now_ts(), current_prompt_key="otp_required", current_markup_payload={"type": "language"}, history=[])
        return None

    await _show_main_menu(message, _lang(user))
    await _show_step(message, state, reason, reply_markup=None, reset_panel=True)
    return None


async def _ensure_access_callback(call: CallbackQuery, state: FSMContext, user=None):
    user = user or await access_service.ensure_user(call.from_user)
    if not await _ensure_timeout(call, state, _lang(user)):
        await call.answer()
        return None

    allowed, reason = await access_service.can_use_features(user)
    if allowed:
        return user

    await state.clear()

    if user.status != "activated":
        await _remove_main_menu(call)
        await _show_step(call, state, reason, reply_markup=language_keyboard(), reset_panel=True)
        await state.set_state(OtpStates.waiting_otp)
        await state.update_data(
            last_activity=_now_ts(),
            current_prompt_key="otp_required",
            current_markup_payload={"type": "language"},
            history=[],
        )
        await call.answer()
        return None

    await _show_main_menu(call, _lang(user))
    await _show_step(call, state, reason, reply_markup=None, reset_panel=True)
    await call.answer()
    return None


def _menu_action(text: str | None) -> str | None:
    normalized = (text or "").strip().lower()
    candidates = {
        "help": {"help", "အကူအညီ"},
        "add_pair": {"add pair", "pair ထည့်မယ်"},
        "delete_pair": {"delete pair", "pair ဖျက်မယ်"},
        "edit_source": {"edit source", "source ပြင်မယ်"},
        "edit_target": {"edit target", "target ပြင်မယ်"},
        "keyword": {"keyword"},
        "ads": {"ads", "ကြော်ငြာ"},
        "status": {"status", "အခြေအနေ"},
        "check": {"check", "စစ်မယ်"},
        "forward_rule": {"forward rule"},
        "post_rule": {"post rule"},
        "contact": {"contact", "ဆက်သွယ်ရန်"},
        "language": {"language", "ဘာသာစကား"},
    }
    for action, values in candidates.items():
        if normalized in {value.lower() for value in values}:
            return action
    return None


@router.message(Command("start"))
async def start_cmd(message: Message, state: FSMContext) -> None:
    await state.clear()

    user = await access_service.ensure_user(message.from_user)
    language = _lang(user)

    if user.is_banned:
        await message.answer(
            t(language, "access_blocked"),
            reply_markup=hide_reply_keyboard(),
        )
        return

    if user.status != "activated":
        await _remove_main_menu(message)
        await state.set_state(OtpStates.waiting_otp)
        await state.update_data(
            last_activity=_now_ts(),
            current_prompt_key="otp_required",
            current_prompt_fmt={},
            current_markup_payload={"type": "language"},
            history=[],
        )
        await message.answer(
            t(language, "otp_required"),
            reply_markup=language_keyboard(),
        )
        return

    # Admin / activated users must get a fresh message with main_menu(...)
    await message.answer(build_tutorial(language))
    await message.answer(
        t(language, "main_menu_ready"),
        reply_markup=main_menu(language),
    )


@router.message(Command("otp"))
async def admin_otp(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) != 3:
        await message.answer("Usage: /otp 7d mykey")
        return
    duration, key = parts[1], parts[2]
    await OtpRepo().create(duration, key, message.from_user.id)
    await message.answer(t(settings.language_default, "otp_saved", duration=duration, otp_key=key))


@router.message(Command("info"))
async def admin_info(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    parts = message.text.split(maxsplit=1)
    user_id = int(parts[1]) if len(parts) == 2 else message.from_user.id
    user = await user_repo.get(user_id)
    if not user:
        await message.answer("User not found.")
        return
    await message.answer(await _status_text(user_id, _lang(user)))


@router.message(Command("ban"))
async def admin_ban(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage: /ban user_id")
        return
    await user_repo.set_ban(int(parts[1]), True)
    await message.answer(t(settings.language_default, "user_banned"))


@router.message(Command("unban"))
async def admin_unban(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage: /unban user_id")
        return
    await user_repo.set_ban(int(parts[1]), False)
    await message.answer(t(settings.language_default, "user_unbanned"))


@router.message(Command("pair_limit"))
async def admin_pair_limit(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    parts = message.text.split()
    if len(parts) == 2:
        value = int(parts[1])
        await settings_repo.set_json("pair_limit", {"value": value})
        await message.answer(t(settings.language_default, "pair_limit_set_global", value=value))
        return
    if len(parts) == 3:
        user_id, value = int(parts[1]), int(parts[2])
        await user_repo.set_pair_limit(user_id, value)
        await message.answer(t(settings.language_default, "pair_limit_set_user", user_id=user_id, value=value))
        return
    await message.answer("Usage: /pair_limit 20 OR /pair_limit user_id 10")


@router.message(Command("noti"))
async def admin_noti(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Usage: /noti message")
        return
    users = await user_repo.list_active_non_banned()
    sent = 0
    for user in users:
        try:
            await message.bot.send_message(user.user_id, text)
            sent += 1
        except Exception:
            continue
    await message.answer(t(settings.language_default, "broadcast_done", count=sent))


@router.message(Command("list_active"))
async def admin_list_active(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    users = await user_repo.list_active_non_banned()
    if not users:
        await message.answer(t(settings.language_default, "no_active_users"))
        return
    await message.answer("\n".join(f"{user.user_id} | @{user.username or '-'} | until={user.activated_until}" for user in users))


@router.message(Command("list_expired"))
async def admin_list_expired(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    users = await user_repo.list_expired()
    if not users:
        await message.answer(t(settings.language_default, "no_expired_users"))
        return
    await message.answer("\n".join(f"{user.user_id} | @{user.username or '-'} | until={user.activated_until}" for user in users))


@router.message(Command("reset_user"))
async def admin_reset_user(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer("Usage: /reset_user user_id")
        return
    user_id = int(parts[1])
    pairs = await pair_repo.list_for_user(user_id)
    for pair in pairs:
        await pair_service.delete_pair(user_id, pair.pair_no)
    await user_repo.reset_user_setup(user_id)
    runtime_manager.clear_cache()
    await message.answer(t(settings.language_default, "reset_user_done"))


@router.message(Command("runtime_reload"))
async def admin_runtime_reload(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    runtime_manager.clear_cache()
    await message.answer(t(settings.language_default, "runtime_reloaded"))


@router.message(Command("source_debug"))
async def admin_source_debug(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    items = await source_repo.list_all()
    if not items:
        await message.answer(t(settings.language_default, "source_debug_empty"))
        return
    await message.answer(
        "\n\n".join(
            f"{item.source_kind} | {item.source_input}\njoined={item.joined_by_shared_session} | refs={item.active_pair_reference_count} | chat_id={item.chat_id}"
            for item in items
        )
    )


@router.message(Command("joined_sources"))
async def admin_joined_sources(message: Message) -> None:
    if not _is_admin(message.from_user.id):
        await message.answer(t(settings.language_default, "admin_only"))
        return
    items = await source_repo.list_joined_private()
    if not items:
        await message.answer(t(settings.language_default, "joined_sources_empty"))
        return
    await message.answer("\n".join(f"{item.source_input} | refs={item.active_pair_reference_count}" for item in items))

@router.callback_query()
async def callback_router(call: CallbackQuery, state: FSMContext) -> None:
    user = user or await access_service.ensure_user(call.from_user)
    language = _lang(user)

    data = call.data or ""

    current_state = await state.get_state()

    if data.startswith("lang:"):
        new_language = data.split(":", 1)[1]
        await user_repo.set_language(call.from_user.id, new_language)
        state_data = await state.get_data()
        current_user = await user_repo.get(call.from_user.id)
        is_activated = bool(current_user and current_user.status == "activated" and not current_user.is_banned)

        state_data = await state.get_data()
        if await state.get_state() and state_data.get("current_prompt_key"):
            prompt_key = state_data["current_prompt_key"]
            prompt_fmt = state_data.get("current_prompt_fmt", {})
            markup_payload = state_data.get("current_markup_payload")
            markup = await _render_markup(call.from_user.id, new_language, markup_payload)
            step_text = _resolve_step_text(
                new_language,
                prompt_key,
                prompt_fmt,
                markup_payload,
                panel_text=state_data.get("current_panel_text"),
            )
            await _show_step(call, state, step_text, reply_markup=markup)
        else:
            if is_activated:
                await _show_main_menu(call, new_language)
            else:
                await _remove_main_menu(call)
            await _show_step(call, state, t(new_language, "language_set"), reply_markup=None, reset_panel=True)
        return

    if current_state and not await _ensure_timeout(call, state, language):
        return

    if data.startswith("restore:"):
        action = data.split(":", 1)[1]
        active_pairs = await pair_repo.list_for_user(call.from_user.id)
        if action == "fresh":
            for pair in active_pairs:
                await pair_service.delete_pair(call.from_user.id, pair.pair_no)
            await _show_step(call, state, t(language, "fresh_done"), reply_markup=None)
            await _restore_main_menu(call, language)
        else:
            await _show_step(call, state, t(language, "restore_done"), reply_markup=None)
            await _restore_main_menu(call, language)
        await user_repo.clear_restore_choice(call.from_user.id)
        await state.clear()
        return

    if not await _ensure_access_callback(call, state, user=user):
        return

    late_alert_callback = (
        (data.startswith("add_target_admin:") and current_state == AddPairStates.waiting_confirm.state)
        or
        (data.startswith("edit_target_admin:") and current_state == EditTargetStates.waiting_confirm.state)
    )

    if not late_alert_callback:
        try:
            await call.answer()
        except Exception:
            pass

    if data.endswith(":back") or data in {"kw_action:back", "ads_action:back"}:
        await _go_back(call, state, language, call.from_user.id)
        return

    if data.endswith(":cancel") or data in {"kw_action:cancel", "ads_action:cancel"}:
        await _cancel_flow(call, state, language, call.from_user.id)
        return

    if data.startswith("add_post:") and current_state == AddPairStates.waiting_post_rule.state:
        value = data.split(":", 1)[1]
        await state.update_data(post_rule=(value == "on"))
        await _set_step(
            state,
            AddPairStates.waiting_forward_rule,
            prompt_key="rule_forward_explain",
            markup_payload={"type": "add_forward_rule"},
        )
        await _show_step(call, state, t(language, "rule_forward_explain"), reply_markup=rule_keyboard("add_forward", language))
        return

    if data.startswith("add_forward:") and current_state == AddPairStates.waiting_forward_rule.state:
        value = data.split(":", 1)[1]
        await state.update_data(forward_rule=(value == "on"))
        info = await state.get_data()
        scan = "all" if info["scan_count"] is None else str(info["scan_count"])
        summary = (
            f"{t(language, 'pair_summary_title')}\n"
            f"#{info['pair_no']}\n"
            f"{t(language, 'summary_source')}: {info['source_input']}\n"
            f"{t(language, 'summary_scan')}: {scan}\n"
            f"{t(language, 'summary_target')}: {info['target_input']}\n"
            f"{t(language, 'summary_ads')}: {', '.join(info['ads']) or '-'}\n"
            f"{t(language, 'summary_post_rule')}: {'ON' if info['post_rule'] else 'OFF'}\n"
            f"{t(language, 'summary_forward_rule')}: {'ON' if info['forward_rule'] else 'OFF'}"
        )
        warning_text = _target_admin_warning_text(language, info["target_input"])
        gate_payload = {
            "type": "target_admin_gate",
            "prefix": "add_target_admin",
            "target_input": info["target_input"],
            "failed": False,
        }
        await _set_step(
            state,
            AddPairStates.waiting_confirm,
            prompt_key="target_prompt",
            markup_payload=gate_payload,
            panel_text=warning_text,
        )
        await state.update_data(summary_text=summary)
        await _show_step(call, state, warning_text, reply_markup=target_admin_keyboard("add_target_admin", language))
        return

    if data.startswith("add_target_admin:") and current_state == AddPairStates.waiting_confirm.state:
        action = data.split(":", 1)[1]
        if action == "done":
            info = await state.get_data()
            has_admin = await _bot_has_target_admin(call.bot, info["target_input"])
            if not has_admin:
                failed_payload = {
                    "type": "target_admin_gate",
                    "prefix": "add_target_admin",
                    "target_input": info["target_input"],
                    "failed": True,
                }
                await state.update_data(current_markup_payload=failed_payload)
                await _show_step(
                    call,
                    state,
                    _target_admin_warning_text(language, info["target_input"], failed=True),
                    reply_markup=target_admin_keyboard("add_target_admin", language),
                )
                await call.answer(
                    "Bot is not admin in target yet." if language != "my" else "Bot က target မှာ admin မဖြစ်သေးပါ။",
                    show_alert=True,
                )
                return

            summary = info.get("summary_text") or ""
            await _set_step(
                state,
                AddPairStates.waiting_confirm,
                prompt_key="pair_summary_title",
                markup_payload={"type": "pair_confirm"},
                remember=False,
                panel_text=summary,
            )
            await _show_step(call, state, summary, reply_markup=confirm_keyboard("pair_confirm", language))
        return

    if data.startswith("pair_confirm:") and current_state == AddPairStates.waiting_confirm.state:
        action = data.split(":", 1)[1]
        if action == "yes":
            info = await state.get_data()
            try:
                await pair_service.build_pair(
                    user_id=call.from_user.id,
                    pair_no=info["pair_no"],
                    source_input=info["source_input"],
                    scan_count=info["scan_count"],
                    target_input=info["target_input"],
                    ads=info["ads"],
                    post_rule=info["post_rule"],
                    forward_rule=info["forward_rule"],
                )
            except Exception as exc:
                await _show_step(call, state, f"Create failed: {exc}", reply_markup=None)
            else:
                await _show_step(call, state, t(language, "pair_created"), reply_markup=None)
            await state.clear()
            await _restore_main_menu(call, language)
        return

    if data.startswith("pair_delete:") and current_state == DeletePairStates.waiting_confirm.state:
        action = data.split(":", 1)[1]
        if action == "yes":
            info = await state.get_data()
            try:
                await pair_service.delete_pair(call.from_user.id, info["pair_no"])
            except Exception as exc:
                await _show_step(call, state, f"Delete failed: {exc}", reply_markup=None)
            else:
                await _show_step(call, state, t(language, "pair_deleted"), reply_markup=None)
            await state.clear()
            await _restore_main_menu(call, language)
        return

    if data.startswith("edit_source_confirm:") and current_state == EditSourceStates.waiting_confirm.state:
        action = data.split(":", 1)[1]
        if action == "yes":
            info = await state.get_data()
            try:
                await pair_service.update_source(call.from_user.id, info["pair_no"], info["source_input"], info["scan_count"])
            except Exception as exc:
                await _show_step(call, state, f"Update failed: {exc}", reply_markup=None)
            else:
                runtime_manager.clear_cache()
                await _show_step(call, state, t(language, "pair_updated"), reply_markup=None)
            await state.clear()
            await _restore_main_menu(call, language)
        return

    if data.startswith("edit_target_admin:") and current_state == EditTargetStates.waiting_confirm.state:
        action = data.split(":", 1)[1]
        if action == "done":
            info = await state.get_data()
            has_admin = await _bot_has_target_admin(call.bot, info["target_input"])
            if not has_admin:
                failed_payload = {
                    "type": "target_admin_gate",
                    "prefix": "edit_target_admin",
                    "target_input": info["target_input"],
                    "failed": True,
                }
                await state.update_data(current_markup_payload=failed_payload)
                await _show_step(
                    call,
                    state,
                    _target_admin_warning_text(language, info["target_input"], failed=True),
                    reply_markup=target_admin_keyboard("edit_target_admin", language),
                )
                await call.answer(
                    "Bot is not admin in target yet." if language != "my" else "Bot က target မှာ admin မဖြစ်သေးပါ။",
                    show_alert=True,
                )
                return

            summary = info.get("summary_text") or ""
            await _set_step(
                state,
                EditTargetStates.waiting_confirm,
                prompt_key="edit_target_confirm",
                markup_payload={"type": "edit_target_confirm"},
                remember=False,
                panel_text=summary,
            )
            await _show_step(call, state, summary, reply_markup=confirm_keyboard("edit_target_confirm", language))
        return

    if data.startswith("edit_target_confirm:") and current_state == EditTargetStates.waiting_confirm.state:
        action = data.split(":", 1)[1]
        if action == "yes":
            info = await state.get_data()
            try:
                await pair_service.update_target(call.from_user.id, info["pair_no"], info["target_input"])
            except Exception as exc:
                await _show_step(call, state, f"Update failed: {exc}", reply_markup=None)
            else:
                runtime_manager.clear_cache()
                await _show_step(call, state, t(language, "pair_updated"), reply_markup=None)
            await state.clear()
            await _restore_main_menu(call, language)
        return

    if data.startswith("kw_pair:") and current_state == KeywordStates.waiting_pair.state:
        choice = data.split(":", 1)[1]
        if choice.isdigit():
            pair = await pair_repo.get(call.from_user.id, int(choice))
            if not pair or not pair.active:
                await _show_step(call, state, t(language, "pair_not_found"), reply_markup=None)
                return
            await state.update_data(pair_no=pair.pair_no)
            ban_values = ", ".join(pair.keyword_values) if pair.keyword_mode == "ban" and pair.keyword_values else "-"
            post_values = ", ".join(pair.keyword_values) if pair.keyword_mode == "post" and pair.keyword_values else "-"
            await _set_step(
                state,
                KeywordStates.waiting_action,
                prompt_key="keyword_pair_menu",
                markup_payload={"type": "keyword_actions"},
            )
            await await _show_step(
                call,
                state,t(
                language,
                "keyword_pair_menu",
                pair_no=pair.pair_no,
                ban_values=ban_values,
                post_values=post_values,
            ),reply_markup=keyword_action_keyboard(language),)
        return

    if data.startswith("kw_action:") and current_state == KeywordStates.waiting_action.state:
        action = data.split(":", 1)[1]
        info = await state.get_data()
        pair = await pair_repo.get(call.from_user.id, info["pair_no"])
        if not pair:
            await _show_step(call, state, t(language, "pair_not_found"), reply_markup=None)
            await state.clear()
            return
        if action == "set_ban":
            await state.update_data(pending_keyword_mode="ban")
            await _set_step(
                state,
                KeywordStates.waiting_add_values,
                prompt_key="keyword_send_ban",
                markup_payload={"type": "flow_nav", "prefix": "kw_text"},
            )
            await _show_step(call,state,
                t(language, "keyword_send_ban", pair_no=pair.pair_no),
                reply_markup=text_step_keyboard("kw_text", language),
            )
        elif action == "set_post":
            await state.update_data(pending_keyword_mode="post")
            await _set_step(
                state,
                KeywordStates.waiting_add_values,
                prompt_key="keyword_send_post",
                markup_payload={"type": "flow_nav", "prefix": "kw_text"},
            )
            await _show_step(call,state,
                t(language, "keyword_send_post", pair_no=pair.pair_no),
                reply_markup=text_step_keyboard("kw_text", language),
            )
        elif action == "clear":
            ban_values = ", ".join(pair.keyword_values) if pair.keyword_mode == "ban" and pair.keyword_values else "-"
            post_values = ", ".join(pair.keyword_values) if pair.keyword_mode == "post" and pair.keyword_values else "-"
            await _set_step(
                state,
                KeywordStates.waiting_clear_values,
                prompt_key="keyword_remove_detail",
                markup_payload={"type": "flow_nav", "prefix": "kw_text"},
            )
            await _show_step(call,state,
                t(
                    language,
                    "keyword_remove_detail",
                    pair_no=pair.pair_no,
                    ban_values=ban_values,
                    post_values=post_values,
                ),
                reply_markup=text_step_keyboard("kw_text", language),
            )

    if data.startswith("ads_action:") and current_state == AdsStates.waiting_action.state:
        action = data.split(":", 1)[1]
        if action == "list":
            pairs = [pair for pair in await pair_repo.list_for_user(call.from_user.id) if pair.ads]
            if not pairs:
                await _show_step(call, state, t(language, "ads_empty"), reply_markup=None)
                await state.clear()
                await _show_main_menu(call, language)
            else:
                await _show_step(call, state, "\n\n".join(_pair_line(pair) for pair in pairs), reply_markup=None)
                await state.clear()
                await _show_main_menu(call, language)
        elif action == "add":
            await _set_step(
                state,
                AdsStates.waiting_pair_for_add,
                prompt_key="choose_pair",
                markup_payload={"type": "pair_picker", "prefix": "ads_pair_add", "include_all": False},
            )
            pairs = await pair_repo.list_for_user(call.from_user.id)
            await _show_step(call, state, t(language, "choose_pair"), reply_markup=pair_picker("ads_pair_add", pairs, language))
        elif action == "delete":
            pairs = [pair for pair in await pair_repo.list_for_user(call.from_user.id) if pair.ads]
            if not pairs:
                await _show_step(call, state, t(language, "ads_empty"), reply_markup=None)
                await state.clear()
                await _show_main_menu(call, language)
            else:
                await _set_step(
                    state,
                    AdsStates.waiting_pair_for_delete,
                    prompt_key="ads_delete_choose",
                    markup_payload={"type": "pair_picker", "prefix": "ads_pair_del", "include_all": False},
                )
                await _show_step(call, state, t(language, "ads_delete_choose"), reply_markup=pair_picker("ads_pair_del", pairs, language))
        return

    if data.startswith("ads_pair_add:") and current_state == AdsStates.waiting_pair_for_add.state:
        choice = data.split(":", 1)[1]
        if choice.isdigit():
            await state.update_data(pair_no=int(choice))
            await _set_step(state, AdsStates.waiting_values, prompt_key="ads_send", markup_payload={"type": "flow_nav", "prefix": "ads_text"})
            await _show_step(call, state, t(language, "ads_send"), reply_markup=text_step_keyboard("ads_text", language))
        return

    if data.startswith("ads_pair_del:") and current_state == AdsStates.waiting_pair_for_delete.state:
        choice = data.split(":", 1)[1]
        if choice.isdigit():
            pair = await pair_repo.get(call.from_user.id, int(choice))
            if not pair:
                await _show_step(call, state, t(language, "pair_not_found"), reply_markup=None)
            else:
                await state.update_data(pair_no=pair.pair_no)
                await _set_step(state, AdsStates.waiting_delete_confirm, prompt_key="ads_delete_choose", markup_payload={"type": "ads_delete_confirm"})
                await _show_step(call, state, _pair_line(pair), reply_markup=confirm_keyboard("ads_delete_confirm", language))
            return

    if data.startswith("ads_delete_confirm:") and current_state == AdsStates.waiting_delete_confirm.state:
        action = data.split(":", 1)[1]
        if action == "yes":
            info = await state.get_data()
            await pair_service.update_ads(call.from_user.id, info["pair_no"], [])
            await _show_step(call, state, t(language, "ads_deleted"), reply_markup=None)
            await state.clear()
            await _restore_main_menu(call, language)
        return

    if data.startswith("rule_pair:") and current_state == RuleStates.waiting_pair.state:
        choice = data.split(":", 1)[1]
        if choice.isdigit():
            await state.update_data(pair_no=int(choice))
            info = await state.get_data()
            prefix = "set_forward" if info["field_name"] == "forward_rule" else "set_post"
            await _set_step(state, RuleStates.waiting_value, prompt_key="rule_choose_value", markup_payload={"type": "rule_value", "prefix": prefix})
            await _show_step(call, state, t(language, "rule_choose_value"), reply_markup=rule_keyboard(prefix, language))
        return

    if (data.startswith("set_forward:") or data.startswith("set_post:")) and current_state == RuleStates.waiting_value.state:
        action = data.split(":", 1)[1]
        info = await state.get_data()
        await pair_service.update_rule(call.from_user.id, info["pair_no"], field_name=info["field_name"], value=(action == "on"))
        await _show_step(call, state, t(language, "rule_updated"), reply_markup=None)
        await state.clear()
        await _show_main_menu(call, language)
        return

    if data.startswith("check_pair:") and current_state == CheckStates.waiting_pair.state:
        choice = data.split(":", 1)[1]
        pairs: list[PairRecord]
        if choice == "all":
            pairs = await pair_repo.list_for_user(call.from_user.id)
        elif choice.isdigit():
            pair = await pair_repo.get(call.from_user.id, int(choice))
            pairs = [pair] if pair else []
        else:
            pairs = []
            
        await _show_step(call, state, "Checking...", reply_markup=None)
        for pair in pairs:
            if pair:
                await runtime_manager.scan_pair(pair)
        await _show_step(call, state, t(language, "check_done", count=len([p for p in pairs if p])), reply_markup=None)
        await state.clear()
        await _restore_main_menu(call, language)
        return


@router.message(F.text)
async def message_router(message: Message, state: FSMContext) -> None:
    user = await access_service.ensure_user(message.from_user)
    language = _lang(user)
    current_state = await state.get_state()

    if not await _ensure_timeout(message, state, language):
        return

    normalized = (message.text or "").strip().lower()
    if normalized in {text.lower() for text in CANCEL_TEXTS}:
        await _cancel_flow(message, state, language, message.from_user.id)
        return
    if normalized in {text.lower() for text in BACK_TEXTS}:
        await _go_back(message, state, language, message.from_user.id)
        return

    action = _menu_action(message.text)
    if action and action != "language":
        allowed_user = await _ensure_access_message(message, state)
        if not allowed_user:
            return
    if action == "language":
        await state.clear()
        await _remove_main_menu(message)
        await _show_step(message, state, t(language, "language_choose"), reply_markup=language_keyboard(), reset_panel=True)
        return
    if action == "help":
        await state.clear()
        await _show_main_menu(message, language)
        await _show_step(message, state, build_tutorial(language), reply_markup=None, reset_panel=True)
        return
    if action == "status":
        await state.clear()
        await _show_main_menu(message, language)
        await _show_step(message, state, await _status_text(message.from_user.id, language), reply_markup=None, reset_panel=True)
        return
    if action == "contact":
        await state.clear()
        await _show_main_menu(message, language)
        await _show_step(message, state, t(language, "contact"), reply_markup=None, reset_panel=True)
        return
    if action == "add_pair":
        await state.clear()
        await _remove_main_menu(message)
        await _set_step(state, AddPairStates.waiting_pair_no, prompt_key="pair_no_prompt", markup_payload={"type": "flow_nav", "prefix": "flow"}, remember=False)
        await _show_step(message, state, t(language, "pair_no_prompt"), reply_markup=text_step_keyboard("flow", language), reset_panel=True)
        return
    if action == "delete_pair":
        await state.clear()
        await _remove_main_menu(message)
        await _set_step(state, DeletePairStates.waiting_pair_no, prompt_key="send_pair_number", markup_payload={"type": "flow_nav", "prefix": "flow"}, remember=False)
        await _show_step(message, state, t(language, "send_pair_number"), reply_markup=text_step_keyboard("flow", language), reset_panel=True)
        return
    if action == "edit_source":
        await state.clear()
        await _remove_main_menu(message)
        await _set_step(state, EditSourceStates.waiting_pair_no, prompt_key="send_pair_number", markup_payload={"type": "flow_nav", "prefix": "flow"}, remember=False)
        await _show_step(message, state, t(language, "send_pair_number"), reply_markup=text_step_keyboard("flow", language), reset_panel=True)
        return
    if action == "edit_target":
        await state.clear()
        await _remove_main_menu(message)
        await _set_step(state, EditTargetStates.waiting_pair_no, prompt_key="send_pair_number", markup_payload={"type": "flow_nav", "prefix": "flow"}, remember=False)
        await _show_step(message, state, t(language, "send_pair_number"), reply_markup=text_step_keyboard("flow", language), reset_panel=True)
        return
    if action == "keyword":
        await state.clear()
        await _remove_main_menu(message)
        await _set_step(state, KeywordStates.waiting_pair, prompt_key="keyword_intro", markup_payload={"type": "pair_picker", "prefix": "kw_pair", "include_all": False}, remember=False)
        pairs = await pair_repo.list_for_user(message.from_user.id)
        await _show_step(message, state, t(language, "keyword_intro"), reply_markup=pair_picker("kw_pair", pairs, language), reset_panel=True)
        return
    if action == "ads":
        await state.clear()
        await _remove_main_menu(message)
        await _set_step(state, AdsStates.waiting_action, prompt_key="ads_intro", markup_payload={"type": "ads_actions"}, remember=False)
        await _show_step(message, state, t(language, "ads_intro"), reply_markup=ads_action_keyboard(language), reset_panel=True)
        return
    if action in {"forward_rule", "post_rule"}:
        field_name = "forward_rule" if action == "forward_rule" else "post_rule"
        await state.clear()
        await _remove_main_menu(message)
        await state.update_data(field_name=field_name)
        prompt_key = "rule_forward_explain" if field_name == "forward_rule" else "rule_post_explain"
        await _set_step(state, RuleStates.waiting_pair, prompt_key=prompt_key, markup_payload={"type": "pair_picker", "prefix": "rule_pair", "include_all": False}, remember=False)
        pairs = await pair_repo.list_for_user(message.from_user.id)
        await _show_step(message, state, t(language, prompt_key), reply_markup=pair_picker("rule_pair", pairs, language), reset_panel=True)
        return
    if action == "check":
        await state.clear()
        await _remove_main_menu(message)
        await _set_step(state, CheckStates.waiting_pair, prompt_key="choose_pair_or_all", markup_payload={"type": "pair_picker", "prefix": "check_pair", "include_all": True}, remember=False)
        pairs = await pair_repo.list_for_user(message.from_user.id)
        await _show_step(message, state, t(language, "choose_pair_or_all"), reply_markup=pair_picker("check_pair", pairs, language, include_all=True), reset_panel=True)
        return

    if current_state == OtpStates.waiting_otp.state:
        status, has_old_data = await access_service.redeem_otp(message.from_user.id, message.text.strip())
        if status == "invalid":
            await _show_step(message, state, t(language, "otp_invalid"), reply_markup=language_keyboard())
            return
        if status == "used":
            await _show_step(message, state, t(language, "otp_used"), reply_markup=language_keyboard())
            return
        if has_old_data:
            await state.set_state(OtpStates.waiting_restore_choice)
            await state.update_data(last_activity=_now_ts(), current_prompt_key="restore_choice", current_markup_payload={"type": "restore"}, history=[])
            await _show_step(message, state, t(language, "restore_choice"), reply_markup=restore_keyboard(language), reset_panel=True)
            return
        await state.clear()
        await _show_step(message, state, build_tutorial(language), reply_markup=None)
        await _restore_main_menu(message, language)
        return

    if current_state == AddPairStates.waiting_pair_no.state:
        await _cleanup_user_message(message)
        try:
            pair_no = int(message.text.strip()) if message.text.strip() else await pair_service.next_pair_no(message.from_user.id)
        except Exception:
            await _show_step(message, state, t(language, "invalid_number"), reply_markup=text_step_keyboard("flow", language))
            return
        try:
            await pair_service.validate_pair_no(message.from_user.id, pair_no, creating=True)
        except ValidationError as exc:
            await _show_step(message, state, str(exc), reply_markup=text_step_keyboard("flow", language))
            return
        await state.update_data(pair_no=pair_no)
        await _set_step(state, AddPairStates.waiting_source, prompt_key="source_prompt", markup_payload={"type": "flow_nav", "prefix": "flow"})
        await _show_step(message, state, t(language, "source_prompt"), reply_markup=text_step_keyboard("flow", language))
        return

    if current_state == AddPairStates.waiting_source.state:
        await _cleanup_user_message(message)
        await state.update_data(source_input=message.text.strip())
        await _set_step(state, AddPairStates.waiting_scan, prompt_key="scan_prompt", markup_payload={"type": "flow_nav", "prefix": "flow"})
        await _show_step(message, state, t(language, "scan_prompt"), reply_markup=text_step_keyboard("flow", language))
        return

    if current_state == AddPairStates.waiting_scan.state:
        await _cleanup_user_message(message)
        try:
            scan_count = pair_service.parse_scan_count(message.text.strip())
        except Exception:
            await _show_step(message, state, t(language, "invalid_scan"), reply_markup=text_step_keyboard("flow", language))
            return
        await state.update_data(scan_count=scan_count)
        await _set_step(state, AddPairStates.waiting_target, prompt_key="target_prompt", markup_payload={"type": "flow_nav", "prefix": "flow"})
        await _show_step(message, state, t(language, "target_prompt"), reply_markup=text_step_keyboard("flow", language))
        return

    if current_state == AddPairStates.waiting_target.state:
        await _cleanup_user_message(message)
        await state.update_data(target_input=message.text.strip())
        await _set_step(state, AddPairStates.waiting_ads, prompt_key="ads_prompt", markup_payload={"type": "flow_nav", "prefix": "flow"})
        await _show_step(message, state, t(language, "ads_prompt"), reply_markup=text_step_keyboard("flow", language))
        return

    if current_state == AddPairStates.waiting_ads.state:
        await _cleanup_user_message(message)
        await state.update_data(ads=pair_service.normalize_ads(message.text))
        await _set_step(state, AddPairStates.waiting_post_rule, prompt_key="rule_post_explain", markup_payload={"type": "add_post_rule"})
        await _show_step(message, state, t(language, "rule_post_explain"), reply_markup=rule_keyboard("add_post", language))
        return

    if current_state == DeletePairStates.waiting_pair_no.state:
        await _cleanup_user_message(message)
        try:
            pair_no = int(message.text.strip())
        except Exception:
            await _show_step(message, state, t(language, "invalid_number"), reply_markup=text_step_keyboard("flow", language))
            return
        pair = await pair_repo.get(message.from_user.id, pair_no)
        if not pair or not pair.active:
            await _show_step(message, state, t(language, "pair_not_found"), reply_markup=text_step_keyboard("flow", language))
            return
        await state.update_data(pair_no=pair_no)
        await _set_step(state, DeletePairStates.waiting_confirm, prompt_key="delete_confirm", markup_payload={"type": "delete_confirm"})
        await _show_step(message, state, _pair_line(pair), reply_markup=confirm_keyboard("pair_delete", language))
        return

    if current_state == EditSourceStates.waiting_pair_no.state:
        await _cleanup_user_message(message)
        try:
            pair_no = int(message.text.strip())
        except Exception:
            await _show_step(message, state, t(language, "invalid_number"), reply_markup=text_step_keyboard("flow", language))
            return
        pair = await pair_repo.get(message.from_user.id, pair_no)
        if not pair or not pair.active:
            await _show_step(message, state, t(language, "pair_not_found"), reply_markup=text_step_keyboard("flow", language))
            return
        await state.update_data(pair_no=pair_no)
        await _set_step(state, EditSourceStates.waiting_source, prompt_key="send_new_source", markup_payload={"type": "flow_nav", "prefix": "flow"})
        await _show_step(message, state, t(language, "send_new_source"), reply_markup=text_step_keyboard("flow", language))
        return

    if current_state == EditSourceStates.waiting_source.state:
        await _cleanup_user_message(message)
        await state.update_data(source_input=message.text.strip())
        await _set_step(state, EditSourceStates.waiting_scan, prompt_key="send_scan_again", markup_payload={"type": "flow_nav", "prefix": "flow"})
        await _show_step(message, state, t(language, "send_scan_again"), reply_markup=text_step_keyboard("flow", language))
        return

    if current_state == EditSourceStates.waiting_scan.state:
        await _cleanup_user_message(message)
        try:
            scan_count = pair_service.parse_scan_count(message.text.strip())
        except Exception:
            await _show_step(message, state, t(language, "invalid_scan"), reply_markup=text_step_keyboard("flow", language))
            return
        await state.update_data(scan_count=scan_count)
        info = await state.get_data()
        summary = f"#{info['pair_no']}\n{t(language, 'summary_source')}: {info['source_input']}\n{t(language, 'summary_scan')}: {'all' if scan_count is None else scan_count}"
        await _set_step(state, EditSourceStates.waiting_confirm, prompt_key="edit_source_confirm", markup_payload={"type": "edit_source_confirm"})
        await _show_step(message, state, summary, reply_markup=confirm_keyboard("edit_source_confirm", language))
        return

    if current_state == EditTargetStates.waiting_pair_no.state:
        await _cleanup_user_message(message)
        try:
            pair_no = int(message.text.strip())
        except Exception:
            await _show_step(message, state, t(language, "invalid_number"), reply_markup=text_step_keyboard("flow", language))
            return
        pair = await pair_repo.get(message.from_user.id, pair_no)
        if not pair or not pair.active:
            await _show_step(message, state, t(language, "pair_not_found"), reply_markup=text_step_keyboard("flow", language))
            return
        await state.update_data(pair_no=pair_no)
        await _set_step(state, EditTargetStates.waiting_target, prompt_key="send_new_target", markup_payload={"type": "flow_nav", "prefix": "flow"})
        await _show_step(message, state, t(language, "send_new_target"), reply_markup=text_step_keyboard("flow", language))
        return

    if current_state == EditTargetStates.waiting_target.state:
        await _cleanup_user_message(message)
        await state.update_data(target_input=message.text.strip())
        info = await state.get_data()
        summary = f"#{info['pair_no']}\n{t(language, 'summary_target')}: {info['target_input']}"
        warning_text = _target_admin_warning_text(language, info["target_input"])
        gate_payload = {
            "type": "target_admin_gate",
            "prefix": "edit_target_admin",
            "target_input": info["target_input"],
            "failed": False,
        }
        await _set_step(
            state,
            EditTargetStates.waiting_confirm,
            prompt_key="send_new_target",
            markup_payload=gate_payload,
            panel_text=warning_text,
        )
        await state.update_data(summary_text=summary)
        await _show_step(message, state, warning_text, reply_markup=target_admin_keyboard("edit_target_admin", language))
        return

    if current_state == KeywordStates.waiting_add_values.state:
        await _cleanup_user_message(message)
        info = await state.get_data()
        values = pair_service.normalize_keywords(message.text)
        pair = await pair_repo.get(message.from_user.id, info["pair_no"])
        if not pair:
            await _show_step(message, state, t(language, "pair_not_found"), reply_markup=None)
            await state.clear()
            return
        new_values = sorted({*pair.keyword_values, *values})
        await pair_service.update_keywords(message.from_user.id, pair.pair_no, info.get("pending_keyword_mode", pair.keyword_mode or "ban"), new_values)
        await _show_step(message, state, t(language, "keyword_updated"), reply_markup=None)
        await state.clear()
        await _restore_main_menu(message, language)
        return

    if current_state == KeywordStates.waiting_clear_values.state:
        await _cleanup_user_message(message)
        info = await state.get_data()
        pair = await pair_repo.get(message.from_user.id, info["pair_no"])
        if not pair:
            await _show_step(message, state, t(language, "pair_not_found"), reply_markup=None)
            await state.clear()
            return
        if message.text.strip().lower() == "all":
            await pair_service.update_keywords(message.from_user.id, pair.pair_no, "off", [])
            await _show_step(message, state, t(language, "keyword_cleared"), reply_markup=None)
            await state.clear()
            await _restore_main_menu(message, language)
            return
        values = pair_service.normalize_keywords(message.text)
        await pair_service.clear_selected_keywords(message.from_user.id, pair.pair_no, values)
        await _show_step(message, state, t(language, "keyword_updated"), reply_markup=None)
        await state.clear()
        await _restore_main_menu(message, language)
        return

    if current_state == AdsStates.waiting_values.state:
        await _cleanup_user_message(message)
        info = await state.get_data()
        ads = pair_service.normalize_ads(message.text)
        await pair_service.update_ads(message.from_user.id, info["pair_no"], ads)
        await _show_step(message, state, t(language, "ads_updated"), reply_markup=None)
        await state.clear()
        await _restore_main_menu(message, language)
        return

    callback_only_states = {
        OtpStates.waiting_restore_choice.state,
        AddPairStates.waiting_post_rule.state,
        AddPairStates.waiting_forward_rule.state,
        AddPairStates.waiting_confirm.state,
        DeletePairStates.waiting_confirm.state,
        EditSourceStates.waiting_confirm.state,
        EditTargetStates.waiting_confirm.state,
        KeywordStates.waiting_pair.state,
        KeywordStates.waiting_action.state,
        AdsStates.waiting_action.state,
        AdsStates.waiting_pair_for_add.state,
        AdsStates.waiting_pair_for_delete.state,
        AdsStates.waiting_delete_confirm.state,
        RuleStates.waiting_pair.state,
        RuleStates.waiting_value.state,
        CheckStates.waiting_pair.state,
    }
    if current_state in callback_only_states:
        await _show_step(message, state, t(language, "choose_from_buttons"), reply_markup=await _render_markup(message.from_user.id, language, (await state.get_data()).get("current_markup_payload")))
        return

    await _show_main_menu(message, language)
    await _show_step(message, state, t(language, "unknown_menu"), reply_markup=None, reset_panel=True)
