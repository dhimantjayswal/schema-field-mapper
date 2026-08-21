from pipeline.lexicon import expand
from pipeline.names import tokenize


def test_tz_cd_expands_to_share_a_token_with_timezone():
    """The real miss this lexicon exists to fix: `tz_cd` and `timezone`
    share no literal tokens, but both should expand to include "timezone"."""
    assert set(expand(tokenize("tz_cd"))) & set(expand(tokenize("timezone")))


def test_cost_ctr_cd_expands_to_match_cost_center_code():
    assert expand(tokenize("cost_ctr_cd")) == ["cost", "center", "code"]


def test_unknown_tokens_pass_through_unchanged():
    assert expand(["city"]) == ["city"]
