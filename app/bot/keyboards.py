from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from app.domain.models import PairRecord
from app.i18n.translator import t


def main_menu(language: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=t(language, "menu_help")),
                KeyboardButton(text=t(language, "menu_add_pair")),
                KeyboardButton(text=t(language, "menu_delete_pair")),
            ],
            [
                KeyboardButton(text=t(language, "menu_edit_source")),
                KeyboardButton(text=t(language, "menu_edit_target")),
                KeyboardButton(text=t(language, "menu_keyword")),
            ],
            [
                KeyboardButton(text=t(language, "menu_ads")),
                KeyboardButton(text=t(language, "menu_status")),
                KeyboardButton(text=t(language, "menu_check")),
            ],
            [
                KeyboardButton(text=t(language, "menu_forward_rule")),
                KeyboardButton(text=t(language, "menu_post_rule")),
                KeyboardButton(text=t(language, "menu_remove_url_rule")),
            ],
            [
                KeyboardButton(text=t(language, "menu_contact")),
                KeyboardButton(text=t(language, "menu_language")),
            ],
        ],
        resize_keyboard=True,
    )


def hide_reply_keyboard() -> ReplyKeyboardRemove:
    return ReplyKeyboardRemove(remove_keyboard=True)


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="English", callback_data="lang:en")],
            [InlineKeyboardButton(text="မြန်မာ", callback_data="lang:my")],
        ]
    )


def restore_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "restore_reuse"), callback_data="restore:reuse")],
            [InlineKeyboardButton(text=t(language, "restore_fresh"), callback_data="restore:fresh")],
        ]
    )


def confirm_keyboard(prefix: str, language: str, include_back: bool = True) -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text=t(language, "confirm"), callback_data=f"{prefix}:yes"),
        InlineKeyboardButton(text=t(language, "menu_cancel"), callback_data=f"{prefix}:cancel"),
    ]

    rows = [row]
    if include_back:
        rows.append([InlineKeyboardButton(text=t(language, "menu_back"), callback_data=f"{prefix}:back")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def rule_keyboard(prefix: str, language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(language, "rule_on"), callback_data=f"{prefix}:on"),
                InlineKeyboardButton(text=t(language, "rule_off"), callback_data=f"{prefix}:off"),
            ],
            [
                InlineKeyboardButton(text=t(language, "menu_back"), callback_data=f"{prefix}:back"),
                InlineKeyboardButton(text=t(language, "menu_cancel"), callback_data=f"{prefix}:cancel"),
            ],
        ]
    )


def text_step_keyboard(prefix: str, language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=t(language, "menu_back"), callback_data=f"{prefix}:back"),
                InlineKeyboardButton(text=t(language, "menu_cancel"), callback_data=f"{prefix}:cancel"),
            ],
        ]
    )


def keyword_action_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "keyword_mode_ban"), callback_data="kw_action:set_ban")],
            [InlineKeyboardButton(text=t(language, "keyword_mode_post"), callback_data="kw_action:set_post")],
            [InlineKeyboardButton(text=t(language, "keyword_clear"), callback_data="kw_action:clear")],
            [
                InlineKeyboardButton(text=t(language, "menu_back"), callback_data="kw_action:back"),
                InlineKeyboardButton(text=t(language, "menu_cancel"), callback_data="kw_action:cancel"),
            ],
        ]
    )


def ads_action_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(language, "ads_add"), callback_data="ads_action:add")],
            [InlineKeyboardButton(text=t(language, "ads_delete"), callback_data="ads_action:delete")],
            [InlineKeyboardButton(text=t(language, "ads_list"), callback_data="ads_action:list")],
            [
                InlineKeyboardButton(text=t(language, "menu_back"), callback_data="ads_action:back"),
                InlineKeyboardButton(text=t(language, "menu_cancel"), callback_data="ads_action:cancel"),
            ],
        ]
    )


def pair_picker(prefix: str, pairs: list[PairRecord], language: str, *, include_all: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"#{pair.pair_no}", callback_data=f"{prefix}:{pair.pair_no}")]
        for pair in pairs
    ]

    if include_all:
        rows.append([InlineKeyboardButton(text=t(language, "all_pairs"), callback_data=f"{prefix}:all")])

    rows.append(
        [
            InlineKeyboardButton(text=t(language, "menu_back"), callback_data=f"{prefix}:back"),
            InlineKeyboardButton(text=t(language, "menu_cancel"), callback_data=f"{prefix}:cancel"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)



def target_admin_keyboard(prefix: str, language: str) -> InlineKeyboardMarkup:
    done_text = "Admin ပေးပြီးပါပြီ" if language == "my" else "I gave bot admin"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=done_text, callback_data=f"{prefix}:done")],
            [
                InlineKeyboardButton(text=t(language, "menu_back"), callback_data=f"{prefix}:back"),
                InlineKeyboardButton(text=t(language, "menu_cancel"), callback_data=f"{prefix}:cancel"),
            ],
        ]
    )
