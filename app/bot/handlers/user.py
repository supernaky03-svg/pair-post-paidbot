
from __future__ import annotations

from typing import Iterable

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from ...keyboards import (
    ads_menu_keyboard,
    back_cancel_inline,
    confirm_cancel_keyboard,
    keyword_edit_keyboard,
    keyword_menu_keyboard,
    language_keyboard,
    main_menu,
    on_off_cancel_keyboard,
    pair_selection_keyboard,
    restore_choice_keyboard,
    single_back_keyboard,
)
from ...localization import label, resolve_menu_action, t
from ...models import UserRecord
from ...services.user_actions import (
    ActionError,
    add_pair,
    apply_restore_option,
    build_ads_list_text,
    build_keyword_list_text,
    build_status_text,
    change_language,
    delete_pair_action,
    edit_source_action,
    edit_target_action,
    ensure_user_profile,
    get_fresh_user,
    redeem_otp_for_user,
    run_check_action,
    save_database_channel,
    set_ads_action,
    toggle_rule_action,
    update_keywords_action,
)
from ...states import (
    AddPairStates,
    AdsStates,
    CheckStates,
    DeletePairStates,
    EditSourceStates,
    EditTargetStates,
    KeywordStates,
    SetupStates,
)
from ...utils.parsing import ParseError, parse_id_or_all, parse_pair_number, parse_scan_amount
from ...core.runtime import get_runtime, list_user_pairs

router = Router()


def _text_wants_cancel_or_back(text: str | None) -> str | None:
    action = resolve_menu_action(text or "")
    if action in {"cancel", "back"}:
        return action
    lowered = (text or "").strip().lower()
    if lowered in {"cancel", "back"}:
        return lowered
    return None


async def _show_main_menu(message: Message, user: UserRecord, extra: str | None = None) -> None:
    text = extra or t(user, "main_menu_title")
    await message.answer(text, reply_markup=main_menu(user.language))


async def _show_main_menu_callback(callback: CallbackQuery, user: UserRecord, extra: str | None = None) -> None:
    await callback.answer()
    await callback.message.answer(extra or t(user, "main_menu_title"), reply_markup=main_menu(user.language))


async def _cancel_state(message: Message, state: FSMContext, user: UserRecord) -> None:
    await state.clear()
    await _show_main_menu(message, user, t(user, "cancelled"))


async def _cancel_callback(callback: CallbackQuery, state: FSMContext, user: UserRecord) -> None:
    await state.clear()
    await _show_main_menu_callback(callback, user, t(user, "cancelled"))


async def _require_user(message: Message) -> UserRecord:
    return await ensure_user_profile(message.from_user)


async def _require_active_user(message: Message, state: FSMContext) -> UserRecord | None:
    user = await _require_user(message)
    if user.is_banned:
        await message.answer(t(user, "banned"))
        return None
    if not user.has_access():
        await state.set_state(SetupStates.waiting_for_otp)
        await message.answer(t(user, "otp_prompt"))
        return None
    if not user.database_channel_id:
        await state.set_state(SetupStates.waiting_for_database_channel)
        await message.answer(t(user, "setup_guide"))
        return None
    return user


def _pair_choice_keyboard(user: UserRecord, prefix: str) -> InlineKeyboardMarkup:
    pair_ids = [pair.pair_id for pair in list_user_pairs(user.telegram_user_id)]
    return pair_selection_keyboard(user.language, pair_ids, prefix)


@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    user = await _require_user(message)
    await state.clear()
    if user.is_banned:
        await message.answer(t(user, "banned"))
        return
    if not user.has_access():
        await state.set_state(SetupStates.waiting_for_otp)
        await message.answer(t(user, "otp_prompt"))
        return
    if not user.database_channel_id:
        await state.set_state(SetupStates.waiting_for_database_channel)
        await message.answer(t(user, "setup_guide"))
        return
    await _show_main_menu(message, user)


@router.callback_query(F.data == "nav:menu")
async def nav_menu(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    await state.clear()
    if not user.has_access():
        await state.set_state(SetupStates.waiting_for_otp)
        await callback.message.answer(t(user, "otp_prompt"))
        await callback.answer()
        return
    if not user.database_channel_id:
        await state.set_state(SetupStates.waiting_for_database_channel)
        await callback.message.answer(t(user, "setup_guide"))
        await callback.answer()
        return
    await _show_main_menu_callback(callback, user)


@router.callback_query(F.data == "nav:cancel")
async def nav_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    await _cancel_callback(callback, state, user)


@router.message(SetupStates.waiting_for_otp)
async def otp_input(message: Message, state: FSMContext) -> None:
    user = await _require_user(message)
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        user, expiry, needs_restore = await redeem_otp_for_user(user, (message.text or "").strip())
    except ActionError as exc:
        await message.answer(str(exc))
        return

    await message.answer(t(user, "otp_success", expiry=expiry.strftime("%Y-%m-%d %H:%M UTC")))
    if needs_restore:
        await state.set_state(SetupStates.waiting_for_restore_choice)
        await message.answer(
            t(user, "restore_choice"),
            reply_markup=restore_choice_keyboard(user.language),
        )
        return
    if not user.database_channel_id:
        await state.set_state(SetupStates.waiting_for_database_channel)
        await message.answer(t(user, "setup_guide"))
        return
    await state.clear()
    await _show_main_menu(message, user)

@router.callback_query(F.data.startswith("restore:"))
async def restore_choice(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    mode = callback.data.split(":", 1)[1]
    user = await apply_restore_option(user, mode)
    await callback.answer()
    if mode == "reset":
        await state.set_state(SetupStates.waiting_for_database_channel)
        await callback.message.answer(t(user, "reset_done"))
        await callback.message.answer(t(user, "setup_guide"))
        return
    await state.clear()
    await callback.message.answer(t(user, "reuse_done"))
    await _show_main_menu_callback(callback, user)

@router.message(SetupStates.waiting_for_database_channel)
async def database_channel_input(message: Message, state: FSMContext) -> None:
    user = await _require_user(message)
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        channel_id = int((message.text or "").strip())
        user = await save_database_channel(user, channel_id)
    except Exception:
        await message.answer(t(user, "db_channel_invalid"))
        return
    await state.clear()
    await message.answer(t(user, "setup_saved"))
    await _show_main_menu(message, user)

@router.message(F.text)
async def main_menu_dispatcher(message: Message, state: FSMContext) -> None:
    action = resolve_menu_action(message.text or "")
    if not action:
        return
    user = await _require_active_user(message, state)
    if not user:
        return

    if action == "help":
        await message.answer(t(user, "help_text"), reply_markup=single_back_keyboard(user.language))
        return
    if action == "contact":
        await message.answer(t(user, "contact_text"), reply_markup=single_back_keyboard(user.language))
        return
    if action == "status":
        await message.answer(build_status_text(user), reply_markup=single_back_keyboard(user.language))
        return
    if action == "language":
        await message.answer("Choose language / ဘာသာစကားရွေးပါ", reply_markup=language_keyboard())
        return
    if action == "keyword":
        await message.answer("Keyword menu", reply_markup=keyword_menu_keyboard(user.language))
        return
    if action == "ads":
        await message.answer("Ads menu", reply_markup=ads_menu_keyboard(user.language))
        return
    if action == "check":
        await state.set_state(CheckStates.waiting_for_pair_or_all)
        await message.answer(
            "Type a pair number or all. Recheck starts from that pair's last_processed_id.",
            reply_markup=back_cancel_inline(user.language, "nav:menu"),
        )
        return
    if action == "forward_rule":
        await message.answer(
            t(user, "forward_rule_help"),
            reply_markup=_pair_choice_keyboard(user, "rulemenu:forward"),
        )
        return
    if action == "post_rule":
        await message.answer(
            t(user, "post_rule_help"),
            reply_markup=_pair_choice_keyboard(user, "rulemenu:post"),
        )
        return
    if action == "addpair":
        await state.clear()
        await state.set_state(AddPairStates.waiting_for_pair_number)
        await message.answer(
            "Send pair number or auto.",
            reply_markup=back_cancel_inline(user.language, "nav:menu"),
        )
        return
    if action == "deletepair":
        await state.clear()
        await state.set_state(DeletePairStates.waiting_for_pair_number)
        await message.answer("Send pair number to delete.", reply_markup=back_cancel_inline(user.language, "nav:menu"))
        return
    if action == "edit_source":
        await state.clear()
        await state.set_state(EditSourceStates.waiting_for_pair_number)
        await message.answer("Send pair number.", reply_markup=back_cancel_inline(user.language, "nav:menu"))
        return
    if action == "edit_target":
        await state.clear()
        await state.set_state(EditTargetStates.waiting_for_pair_number)
        await message.answer("Send pair number.", reply_markup=back_cancel_inline(user.language, "nav:menu"))
        return

@router.callback_query(F.data.startswith("lang:"))
async def language_callback(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    language = callback.data.split(":", 1)[1]
    user = await change_language(user, language)
    await callback.answer()
    await callback.message.answer(t(user, "language_saved"))
    await _show_main_menu_callback(callback, user)

# Addpair flow
@router.message(AddPairStates.waiting_for_pair_number)
async def addpair_pair_number(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        pair_number = parse_pair_number(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(pair_id_input=pair_number)
    await state.set_state(AddPairStates.waiting_for_source)
    await message.answer("Send source channel link / username / invite / ID.")

@router.message(AddPairStates.waiting_for_source)
async def addpair_source(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    await state.update_data(source_id=(message.text or "").strip())
    await state.set_state(AddPairStates.waiting_for_scan_amount)
    await message.answer(
        "Send scan post amount from source. Default = 100. Type a number or all."
    )

@router.message(AddPairStates.waiting_for_scan_amount)
async def addpair_scan(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        scan_amount = parse_scan_amount(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(scan_amount=scan_amount)
    await state.set_state(AddPairStates.waiting_for_target)
    await message.answer("Send target channel link / username / invite / ID.")

@router.message(AddPairStates.waiting_for_target)
async def addpair_target(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    await state.update_data(target_id=(message.text or "").strip())
    await state.set_state(AddPairStates.waiting_for_ads)
    await message.answer(
        "Send ads link(s), separated by comma, or type Skip.",
        reply_markup=back_cancel_inline(user.language, "nav:menu"),
    )

@router.message(AddPairStates.waiting_for_ads)
async def addpair_ads(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    text = (message.text or "").strip()
    ads_links = [] if text.lower() == "skip" or text == label("skip", user.language) else [item.strip() for item in text.split(",") if item.strip()]
    await state.update_data(ads_links=ads_links)
    await message.answer(
        "Post rule:",
        reply_markup=on_off_cancel_keyboard(user.language, "addpair:post"),
    )

@router.callback_query(F.data.startswith("addpair:post:"))
async def addpair_post_rule(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    value = callback.data.split(":")[-1]
    await state.update_data(post_rule=value == "on")
    await callback.answer()
    await callback.message.answer(
        "Forward rule:",
        reply_markup=on_off_cancel_keyboard(user.language, "addpair:forward"),
    )

@router.callback_query(F.data.startswith("addpair:forward:"))
async def addpair_forward_rule(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    value = callback.data.split(":")[-1]
    await state.update_data(forward_rule=value == "on")
    data = await state.get_data()
    summary = (
        f"Pair: {data.get('pair_id_input') or 'auto'}\n"
        f"Source: {data.get('source_id')}\n"
        f"Scan: {data.get('scan_amount')}\n"
        f"Target: {data.get('target_id')}\n"
        f"Ads: {', '.join(data.get('ads_links', [])) or '-'}\n"
        f"Post rule: {'On' if data.get('post_rule') else 'Off'}\n"
        f"Forward rule: {'On' if value == 'on' else 'Off'}"
    )
    await state.set_state(AddPairStates.waiting_for_confirm)
    await callback.answer()
    await callback.message.answer(
        summary,
        reply_markup=confirm_cancel_keyboard(user.language, "addpair:confirm"),
    )

@router.callback_query(F.data == "addpair:confirm")
async def addpair_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    data = await state.get_data()
    try:
        pair = await add_pair(
            user,
            pair_id_input=int(data.get("pair_id_input", 0) or 0),
            source_id=data["source_id"],
            scan_amount=int(data["scan_amount"]),
            target_id=data["target_id"],
            ads_links=list(data.get("ads_links", [])),
            post_rule=bool(data.get("post_rule", True)),
            forward_rule=bool(data.get("forward_rule", False)),
        )
    except (ActionError, KeyError) as exc:
        await callback.answer()
        await callback.message.answer(str(exc))
        return
    await state.clear()
    await callback.answer("Saved")
    await callback.message.answer(f"Pair {pair.pair_id} created. Initial scan started.")
    await _show_main_menu_callback(callback, user)

# Delete pair
@router.message(DeletePairStates.waiting_for_pair_number)
async def deletepair_number(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        pair_id = int(parse_id_or_all(message.text or ""))
    except Exception:
        await message.answer("Send a valid pair number.")
        return
    await state.update_data(pair_id=pair_id)
    await state.set_state(DeletePairStates.waiting_for_confirm)
    await message.answer(
        f"Delete pair {pair_id}?",
        reply_markup=confirm_cancel_keyboard(user.language, "deletepair:confirm"),
    )

@router.callback_query(F.data == "deletepair:confirm")
async def deletepair_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    data = await state.get_data()
    pair_id = int(data["pair_id"])
    try:
        await delete_pair_action(user, pair_id)
    except ActionError as exc:
        await callback.answer()
        await callback.message.answer(str(exc))
        return
    await state.clear()
    await callback.answer("Deleted")
    await callback.message.answer(f"Pair {pair_id} deleted.")
    await _show_main_menu_callback(callback, user)

# Edit source
@router.message(EditSourceStates.waiting_for_pair_number)
async def editsource_pair(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        pair_id = int(parse_id_or_all(message.text or ""))
    except Exception:
        await message.answer("Send a valid pair number.")
        return
    await state.update_data(pair_id=pair_id)
    await state.set_state(EditSourceStates.waiting_for_source)
    await message.answer("Send new source.")

@router.message(EditSourceStates.waiting_for_source)
async def editsource_source(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    await state.update_data(new_source=(message.text or "").strip())
    await state.set_state(EditSourceStates.waiting_for_scan_amount)
    await message.answer("Send new scan amount. Default = 100, or all.")

@router.message(EditSourceStates.waiting_for_scan_amount)
async def editsource_scan(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        scan_amount = parse_scan_amount(message.text or "")
    except ParseError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(scan_amount=scan_amount)
    data = await state.get_data()
    await state.set_state(EditSourceStates.waiting_for_confirm)
    await message.answer(
        f"Pair {data['pair_id']}\nSource: {data['new_source']}\nScan: {scan_amount}",
        reply_markup=confirm_cancel_keyboard(user.language, "editsource:confirm"),
    )

@router.callback_query(F.data == "editsource:confirm")
async def editsource_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    data = await state.get_data()
    try:
        pair = await edit_source_action(
            user,
            int(data["pair_id"]),
            data["new_source"],
            int(data["scan_amount"]),
        )
    except (ActionError, KeyError) as exc:
        await callback.answer()
        await callback.message.answer(str(exc))
        return
    await state.clear()
    await callback.answer("Saved")
    await callback.message.answer(f"Pair {pair.pair_id} source updated. Rescan started.")
    await _show_main_menu_callback(callback, user)

# Edit target
@router.message(EditTargetStates.waiting_for_pair_number)
async def edittarget_pair(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        pair_id = int(parse_id_or_all(message.text or ""))
    except Exception:
        await message.answer("Send a valid pair number.")
        return
    await state.update_data(pair_id=pair_id)
    await state.set_state(EditTargetStates.waiting_for_target)
    await message.answer("Send new target.")

@router.message(EditTargetStates.waiting_for_target)
async def edittarget_target(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    await state.update_data(new_target=(message.text or "").strip())
    data = await state.get_data()
    await state.set_state(EditTargetStates.waiting_for_confirm)
    await message.answer(
        f"Pair {data['pair_id']}\nTarget: {data['new_target']}",
        reply_markup=confirm_cancel_keyboard(user.language, "edittarget:confirm"),
    )

@router.callback_query(F.data == "edittarget:confirm")
async def edittarget_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    data = await state.get_data()
    try:
        pair = await edit_target_action(user, int(data["pair_id"]), data["new_target"])
    except (ActionError, KeyError) as exc:
        await callback.answer()
        await callback.message.answer(str(exc))
        return
    await state.clear()
    await callback.answer("Saved")
    await callback.message.answer(f"Pair {pair.pair_id} target updated.")
    await _show_main_menu_callback(callback, user)

# Keyword flow
@router.callback_query(F.data == "keyword:back")
async def keyword_back(callback: CallbackQuery) -> None:
    user = await ensure_user_profile(callback.from_user)
    await callback.answer()
    await callback.message.answer("Keyword menu", reply_markup=keyword_menu_keyboard(user.language))

@router.callback_query(F.data.startswith("keyword:mode:"))
async def keyword_mode(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    mode = callback.data.split(":")[-1]
    await state.update_data(keyword_mode=mode)
    await callback.answer()
    await callback.message.answer(
        "Choose pair",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=str(pair.pair_id), callback_data=f"keyword:pair:{mode}:{pair.pair_id}")]
                for pair in list_user_pairs(user.telegram_user_id)
            ] + [[InlineKeyboardButton(text=label("back", user.language), callback_data="keyword:back")]]
        ),
    )

@router.callback_query(F.data.startswith("keyword:pair:"))
async def keyword_pair(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    _, _, mode, pair_id_text = callback.data.split(":")
    pair_id = int(pair_id_text)
    await state.update_data(keyword_mode=mode, pair_id=pair_id)
    await callback.answer()
    await callback.message.answer(
        build_keyword_list_text(user, pair_id, mode),
        reply_markup=keyword_edit_keyboard(user.language, mode, pair_id),
    )

@router.callback_query(F.data.startswith("keyword:add:"))
async def keyword_add(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    _, _, mode, pair_id_text = callback.data.split(":")
    await state.update_data(keyword_mode=mode, pair_id=int(pair_id_text))
    await state.set_state(KeywordStates.waiting_for_add_keywords)
    await callback.answer()
    await callback.message.answer("Type new keyword(s). Separate multiple items with comma.")

@router.message(KeywordStates.waiting_for_add_keywords)
async def keyword_add_input(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    data = await state.get_data()
    try:
        pair = await update_keywords_action(
            user,
            int(data["pair_id"]),
            mode=data["keyword_mode"],
            add_values=message.text or "",
        )
    except (ActionError, KeyError) as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer("Keyword saved.")
    await _show_main_menu(message, user)

@router.callback_query(F.data.startswith("keyword:clear:"))
async def keyword_clear(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    _, _, mode, pair_id_text = callback.data.split(":")
    await state.update_data(keyword_mode=mode, pair_id=int(pair_id_text))
    await state.set_state(KeywordStates.waiting_for_clear_keywords)
    await callback.answer()
    await callback.message.answer("Type keyword(s) to remove, separated by comma, or type all.")

@router.message(KeywordStates.waiting_for_clear_keywords)
async def keyword_clear_input(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    data = await state.get_data()
    try:
        if (message.text or "").strip().lower() == "all":
            await update_keywords_action(
                user,
                int(data["pair_id"]),
                mode=data["keyword_mode"],
                clear_all=True,
            )
        else:
            await update_keywords_action(
                user,
                int(data["pair_id"]),
                mode=data["keyword_mode"],
                remove_values=message.text or "",
            )
    except (ActionError, KeyError) as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer("Keyword updated.")
    await _show_main_menu(message, user)

# Ads flow
@router.callback_query(F.data == "ads:list")
async def ads_list(callback: CallbackQuery) -> None:
    user = await ensure_user_profile(callback.from_user)
    await callback.answer()
    await callback.message.answer(
        build_ads_list_text(user),
        reply_markup=single_back_keyboard(user.language),
    )

@router.callback_query(F.data == "ads:add")
async def ads_add(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    await state.set_state(AdsStates.waiting_for_pair_number_add)
    await callback.answer()
    await callback.message.answer("Send pair number for ads.")

@router.message(AdsStates.waiting_for_pair_number_add)
async def ads_pair_number(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        pair_id = int(parse_id_or_all(message.text or ""))
    except Exception:
        await message.answer("Send a valid pair number.")
        return
    await state.update_data(pair_id=pair_id)
    await state.set_state(AdsStates.waiting_for_ads_links)
    await message.answer("Send ads link(s), separated by comma.")

@router.message(AdsStates.waiting_for_ads_links)
async def ads_links_input(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    data = await state.get_data()
    ads_links = [item.strip() for item in (message.text or "").split(",") if item.strip()]
    try:
        await set_ads_action(user, int(data["pair_id"]), ads_links)
    except (ActionError, KeyError) as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer("Ads saved.")
    await _show_main_menu(message, user)

@router.callback_query(F.data == "ads:delete")
async def ads_delete(callback: CallbackQuery, state: FSMContext) -> None:
    user = await ensure_user_profile(callback.from_user)
    await state.set_state(AdsStates.waiting_for_pair_number_delete)
    await callback.answer()
    await callback.message.answer(build_ads_list_text(user))
    await callback.message.answer("Send pair number to remove ads from.")

@router.message(AdsStates.waiting_for_pair_number_delete)
async def ads_delete_input(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        pair_id = int(parse_id_or_all(message.text or ""))
        await set_ads_action(user, pair_id, [])
    except Exception as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(f"Ads deleted from pair {pair_id}.")
    await _show_main_menu(message, user)

# Check
@router.message(CheckStates.waiting_for_pair_or_all)
async def check_pair_input(message: Message, state: FSMContext) -> None:
    user = await _require_active_user(message, state)
    if not user:
        return
    maybe = _text_wants_cancel_or_back(message.text)
    if maybe:
        await _cancel_state(message, state, user)
        return
    try:
        pair_choice = parse_id_or_all(message.text or "")
        count = await run_check_action(user, pair_choice)
    except (ParseError, ActionError) as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(t(user, "check_started") + f" ({count})")
    await _show_main_menu(message, user)

# Rule menus
@router.callback_query(F.data.startswith("rulemenu:"))
async def rule_menu_select(callback: CallbackQuery) -> None:
    user = await ensure_user_profile(callback.from_user)
    _, rule_name, pair_id_text = callback.data.split(":")
    pair_id = int(pair_id_text)
    await callback.answer()
    await callback.message.answer(
        f"Pair {pair_id}",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="On", callback_data=f"rule:{rule_name}:{pair_id}:on"),
                    InlineKeyboardButton(text="Off", callback_data=f"rule:{rule_name}:{pair_id}:off"),
                ],
                [InlineKeyboardButton(text=label("back", user.language), callback_data="nav:menu")],
            ]
        ),
    )

@router.callback_query(F.data.startswith("rule:"))
async def rule_toggle(callback: CallbackQuery) -> None:
    user = await ensure_user_profile(callback.from_user)
    _, rule_name, pair_id_text, value = callback.data.split(":")
    try:
        await toggle_rule_action(user, int(pair_id_text), rule_name, value == "on")
    except ActionError as exc:
        await callback.answer()
        await callback.message.answer(str(exc))
        return
    await callback.answer("Saved")
    await callback.message.answer(f"Pair {pair_id_text} {rule_name} set to {value.upper()}.")
    await _show_main_menu_callback(callback, user)
