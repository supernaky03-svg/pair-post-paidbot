from app.domain.models import PairRecord
from app.services.repost_logic import append_ads, keyword_match, pair_keyword_allows_text

def test_append_ads():
    assert append_ads("hello", ["a", "b"]) == "hello\n\na\nb"

def test_keyword_match():
    assert keyword_match("This is Anime Time", ["movie", "anime"]) is True

def test_keyword_post_mode():
    pair = PairRecord(user_id=1, pair_no=1, source_input="s", source_key="k", source_kind="public", target_input="t", keyword_mode="post", keyword_values=["anime"])
    assert pair_keyword_allows_text(pair, "new anime episode") is True
    assert pair_keyword_allows_text(pair, "sports") is False
