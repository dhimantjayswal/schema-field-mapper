"""`pipeline.lexicon.expand` regression tests.

`test_tz_cd_expands_to_share_a_token_with_timezone` locks in the real
retrieval miss this module exists to fix (see `pipeline/lexicon.py`'s
docstring); the other two cover a multi-abbreviation name and the
pass-through behavior for tokens with no lexicon entry.
"""
from pipeline.lexicon import expand
from pipeline.names import tokenize


def test_tz_cd_expands_to_share_a_token_with_timezone():
    """The real miss this lexicon exists to fix: `tz_cd` and `timezone`
    share no literal tokens, but both should expand to include "timezone"."""
    assert set(expand(tokenize("tz_cd"))) & set(expand(tokenize("timezone")))


def test_cost_ctr_cd_expands_to_match_cost_center_code():
    """A multi-abbreviation name (`cost_ctr_cd`) expands token-by-token into its full words."""
    assert expand(tokenize("cost_ctr_cd")) == ["cost", "center", "code"]


def test_unknown_tokens_pass_through_unchanged():
    """A token with no `LEXICON` entry is returned as-is."""
    assert expand(["city"]) == ["city"]
