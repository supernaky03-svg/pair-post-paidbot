from __future__ import annotations

from app.i18n.locales import LOCALES

def t(language: str, key: str, **kwargs) -> str:
    lang = (language or "en").lower()
    template = LOCALES.get(lang, LOCALES["en"]).get(key, LOCALES["en"].get(key, key))
    return template.format(**kwargs)

