
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from .localization import label


def main_menu(language: str) -> ReplyKeyboardMarkup:
    rows = [
        [label("help", language), label("addpair", language)],
        [label("deletepair", language), label("edit_source", language)],
        [label("edit_target", language), label("keyword", language)],
        [label("ads", language), label("status", language)],
        [label("check", language), label("forward_rule", language)],
        [label("post_rule", language), label("contact", language)],
        [label("language", language)],
    ]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=text) for text in row] for row in rows],
        resize_keyboard=True,
    )


def single_back_keyboard(language: str, callback: str = "nav:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label("back", language), callback_data=callback)]
        ]
    )


def confirm_cancel_keyboard(language: str, confirm: str, cancel: str = "nav:cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Confirm", callback_data=confirm),
                InlineKeyboardButton(text=label("cancel", language), callback_data=cancel),
            ]
        ]
    )


def on_off_cancel_keyboard(language: str, prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="On", callback_data=f"{prefix}:on"),
                InlineKeyboardButton(text="Off", callback_data=f"{prefix}:off"),
            ],
            [
                InlineKeyboardButton(text=label("cancel", language), callback_data="nav:cancel")
            ],
        ]
    )


def restore_choice_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Reuse previous info", callback_data="restore:reuse")],
            [InlineKeyboardButton(text="Start from beginning", callback_data="restore:reset")],
            [InlineKeyboardButton(text=label("cancel", language), callback_data="nav:cancel")],
        ]
    )


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Myanmar", callback_data="lang:my")],
            [InlineKeyboardButton(text="English", callback_data="lang:en")],
        ]
    )


def keyword_menu_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Ban keyword", callback_data="keyword:mode:ban")],
            [InlineKeyboardButton(text="Post keyword", callback_data="keyword:mode:post")],
            [InlineKeyboardButton(text=label("cancel", language), callback_data="nav:cancel")],
            [InlineKeyboardButton(text=label("back", language), callback_data="nav:menu")],
        ]
    )


def keyword_edit_keyboard(language: str, mode: str, pair_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Add keyword", callback_data=f"keyword:add:{mode}:{pair_id}")],
            [InlineKeyboardButton(text="Clear keyword", callback_data=f"keyword:clear:{mode}:{pair_id}")],
            [InlineKeyboardButton(text=label("cancel", language), callback_data="nav:cancel")],
            [InlineKeyboardButton(text=label("back", language), callback_data="keyword:back")],
        ]
    )


def ads_menu_keyboard(language: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Add ads", callback_data="ads:add")],
            [InlineKeyboardButton(text="Delete ads", callback_data="ads:delete")],
            [InlineKeyboardButton(text="List", callback_data="ads:list")],
            [InlineKeyboardButton(text=label("back", language), callback_data="nav:menu")],
        ]
    )


def back_cancel_inline(language: str, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label("back", language), callback_data=back_callback)],
            [InlineKeyboardButton(text=label("cancel", language), callback_data="nav:cancel")],
        ]
    )


def pair_selection_keyboard(language: str, pair_ids: list[int], prefix: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=str(pair_id), callback_data=f"{prefix}:{pair_id}")]
        for pair_id in pair_ids
    ]
    rows.append([InlineKeyboardButton(text=label("back", language), callback_data="nav:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
