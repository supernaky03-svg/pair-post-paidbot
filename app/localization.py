
from __future__ import annotations

from typing import Dict

from .models import UserRecord

LANG_EN = "en"
LANG_MY = "my"

MESSAGES: Dict[str, Dict[str, str]] = {
    "otp_prompt": {
        "en": "Please enter your one-time password first.\n\nFor password contact admin <b>@mnsm6003</b>.",
        "my": "အရင်ဆုံး one-time password ထည့်ပေးပါ။\n\nPassword ရယူရန် admin <b>@mnsm6003</b> ကို ဆက်သွယ်ပါ။",
    },
    "banned": {
        "en": "Your access is banned. Contact admin: <b>@mnsm6003</b>",
        "my": "သင့်အကောင့်ကို ban လုပ်ထားပါတယ်။ Admin <b>@mnsm6003</b> ကို ဆက်သွယ်ပါ။",
    },
    "expired": {
        "en": "Your access has expired. Please redeem a new OTP.",
        "my": "သင့် access သက်တမ်းကုန်သွားပါပြီ။ OTP အသစ်သုံးပြီး ပြန်ဖွင့်ပါ။",
    },
    "setup_guide": {
        "en": (
            "Database channel setup guide\n\n"
            "1. Create a private Telegram channel for your own bot data.\n"
            "2. Add this bot into that channel and grant admin with Post Messages permission.\n"
            "3. Linked repost account: {linked_account}\n"
            "4. Add that repost account into the same channel.\n"
            "5. Use @RawDataBot to get the channel ID.\n"
            "6. Send the channel ID here.\n"
            "   Example: `-1001234567890`"
        ),
        "my": (
            "Database channel setup guide\n\n"
            "1. သင့်အတွက် သီးသန့် private Telegram channel တစ်ခု ဖန်တီးပါ။\n"
            "2. ဒီ bot ကို အဲဒီ channel ထဲ add ပြီး admin ပေးကာ Post Messages permission ကို ဖွင့်ပေးပါ။\n"
            "3. Linked repost account: {linked_account}\n"
            "4. အဲဒီ repost account ကိုလည်း အဲဒီ channel ထဲ add ပေးပါ။\n"
            "5. @RawDataBot နဲ့ channel ID ကိုယူပါ။\n"
            "6. ပြီးရင် ဒီမှာ channel ID ပို့ပါ။\n"
            "   ဥပမာ `-1001234567890`"
        ),
    },
    "setup_saved": {
        "en": "Database channel saved successfully.",
        "my": "Database channel ကို အောင်မြင်စွာ သိမ်းပြီးပါပြီ။",
    },
    "cancelled": {
        "en": "Cancelled.",
        "my": "ပယ်ဖျက်လိုက်ပါပြီ။",
    },
    "main_menu_title": {
        "en": "Main menu",
        "my": "မိန်းမီနူး",
    },
    "contact_text": {
        "en": "For support or password, contact admin: <b>@mnsm6003</b>",
        "my": "အကူအညီလိုရင် သို့မဟုတ် password လိုရင် admin <b>@mnsm6003</b> ကို ဆက်သွယ်ပါ။",
    },
    "help_text": {
        "en": (
            "<b>How to use</b>\n\n"
            "• Add pairs from source channel to target channel.\n"
            "• Use Keyword for ban/post filtering.\n"
            "• Use Ads to append links after cleaning the caption/text.\n"
            "• Use Forward rule to skip forwarded messages.\n"
            "• Use Post rule to only repost video posts.\n"
            "• Use Check to rescan from last processed IDs."
        ),
        "my": (
            "<b>အသုံးပြုပုံ</b>\n\n"
            "• Source channel ကနေ target channel ကို pair ထည့်ပြီး repost လုပ်နိုင်ပါတယ်။\n"
            "• Keyword ကနေ ban/post filter သတ်မှတ်နိုင်ပါတယ်။\n"
            "• Ads ကနေ caption/text အဆုံးမှာ link ထည့်နိုင်ပါတယ်။\n"
            "• Forward rule က forwarded post တွေကို skip လုပ်စေပါတယ်။\n"
            "• Post rule က video post တွေပဲ repost လုပ်စေပါတယ်။\n"
            "• Check က last processed ID ကနေ ပြန်စစ်ပေးပါတယ်။"
        ),
    },
    "restore_choice": {
        "en": "Your old access expired before. Choose what to do with your previous data.",
        "my": "ယခင် access သက်တမ်းကုန်ခဲ့ပါတယ်။ အရင် data တွေကို ဘယ်လိုလုပ်မလဲ ရွေးပါ။",
    },
    "reuse_done": {
        "en": "Previous data has been reused.",
        "my": "အရင် data တွေကို ပြန်သုံးထားပါတယ်။",
    },
    "reset_done": {
        "en": "Old data was reset. Please set up your database channel again.",
        "my": "အရင် data တွေကို reset လုပ်ပြီးပါပြီ။ Database channel ကို ပြန်သတ်မှတ်ပေးပါ။",
    },
    "otp_success": {
        "en": "OTP accepted. Access granted until <b>{expiry}</b>.",
        "my": "OTP အောင်မြင်ပါတယ်။ Access ကို <b>{expiry}</b> အထိ ပေးထားပါတယ်။",
    },
    "invalid_otp": {
        "en": "Invalid or already-used OTP key.",
        "my": "OTP key မှားနေပါတယ် သို့မဟုတ် သုံးပြီးသားဖြစ်နေပါတယ်။",
    },
    "need_active_access": {
        "en": "You need active access first.",
        "my": "အရင်ဆုံး active access ရှိရပါမယ်။",
    },
    "status_title": {
        "en": "<b>Status</b>",
        "my": "<b>အခြေအနေ</b>",
    },
    "check_started": {
        "en": "Check started.",
        "my": "Check စတင်ပြီးပါပြီ။",
    },
    "pair_limit_error": {
        "en": "You reached your pair limit. Contact admin <b>@mnsm6003</b> to get more pair slots.",
        "my": "Pair limit ပြည့်သွားပါပြီ။ Pair slot ပိုလိုလျှင် admin <b>@mnsm6003</b> ကို ဆက်သွယ်ပါ။",
    },
    "source_dup_limit_error": {
        "en": "The same source can be used in maximum 3 pairs only because too many duplicates can cause posting errors.",
        "my": "Source တူတာကို pair 3 ခုအထိပဲ သုံးလို့ရပါတယ်။ ပိုများသွားရင် posting error ဖြစ်နိုင်ပါတယ်။",
    },
    "db_channel_invalid": {
        "en": "Database channel validation failed. Make sure the bot can post there and the linked user account can access it.",
        "my": "Database channel စစ်ဆေးမှုမအောင်မြင်ပါ။ Bot က post တင်လို့ရရမယ်၊ linked user account ကလည်း access ရရမယ်။",
    },
    "forward_rule_help": {
        "en": "Forward rule: when ON, forwarded messages are skipped.",
        "my": "Forward rule: ON လုပ်ထားရင် forwarded message တွေကို skip လုပ်ပါမယ်။",
    },
    "post_rule_help": {
        "en": "Post rule: when ON, only video posts/albums are reposted. Preview text before video is preserved like the old logic.",
        "my": "Post rule: ON လုပ်ထားရင် video post/album တွေပဲ repost လုပ်ပါမယ်။ Video မတိုင်ခင် preview စာသားကိုတော့ old logic လို ဆက်ထိန်းထားပါတယ်။",
    },
    "language_saved": {
        "en": "Language updated.",
        "my": "Language ပြောင်းပြီးပါပြီ။",
    },
}

MENU_LABELS = {
    "help": {"en": "Help", "my": "အကူအညီ"},
    "addpair": {"en": "Addpair", "my": "Pair ထည့်ရန်"},
    "deletepair": {"en": "Deletepair", "my": "Pair ဖျက်ရန်"},
    "edit_source": {"en": "Edit source", "my": "Source ပြင်ရန်"},
    "edit_target": {"en": "Edit target", "my": "Target ပြင်ရန်"},
    "keyword": {"en": "Keyword", "my": "Keyword"},
    "ads": {"en": "Ads", "my": "Ads"},
    "status": {"en": "Status", "my": "Status"},
    "check": {"en": "Check", "my": "Check"},
    "forward_rule": {"en": "Forward rule", "my": "Forward rule"},
    "post_rule": {"en": "Post rule", "my": "Post rule"},
    "contact": {"en": "Contact", "my": "Contact"},
    "language": {"en": "Language", "my": "Language"},
    "back": {"en": "Back", "my": "နောက်သို့"},
    "cancel": {"en": "Cancel", "my": "ပယ်ဖျက်မည်"},
    "skip": {"en": "Skip", "my": "ကျော်မည်"},
    "all": {"en": "all", "my": "all"},
    "auto": {"en": "auto", "my": "auto"},
}


def lang_for(user: UserRecord | None) -> str:
    return user.language if user and user.language in {LANG_EN, LANG_MY} else LANG_EN


def t(user: UserRecord | None, key: str, **kwargs) -> str:
    language = lang_for(user)
    template = MESSAGES.get(key, {}).get(language) or MESSAGES.get(key, {}).get(LANG_EN) or key
    return template.format(**kwargs)


def label(action: str, language: str) -> str:
    labels = MENU_LABELS.get(action, {})
    return labels.get(language, labels.get(LANG_EN, action))


def resolve_menu_action(text: str) -> str | None:
    normalized = (text or "").strip()
    for action, labels in MENU_LABELS.items():
        if normalized in labels.values():
            return action
    return None
