"""Shared word-tokenizer for comparing identifiers by their component words.

Three places in this codebase needed to compare a `snake_case` name against
a `camelCase` one (or filter stopwords out of either) — table alignment
(Stage 1), candidate retrieval's name-overlap boost (Stage 3), and the cold
test suite's fake embedder. Each had grown its own near-identical regex
tokenizer. This module is that logic written once.
"""
import re

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_NON_WORD = re.compile(r"[^a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    """Split text into lowercase word tokens on non-alphanumeric characters
    and camelCase boundaries.

    Used anywhere an identifier needs to be compared by its component
    words rather than as a literal string — e.g. matching `is_remote`
    against `isRemote`, or `dept_info` against `departments`.

    Args:
        text: Any identifier or short phrase — snake_case, camelCase, a
            dotted path, or a mix. Non-alphanumeric runs (`_`, `.`, `-`,
            whitespace, punctuation) are treated as separators, and a
            lowercase-to-uppercase transition is treated as one too.

    Returns:
        Lowercase word tokens, in order. Empty input returns `[]`.

    Example:
        >>> tokenize("is_remote")
        ['is', 'remote']
        >>> tokenize("isRemote")
        ['is', 'remote']
        >>> tokenize("employment.managerId")
        ['employment', 'manager', 'id']
        >>> tokenize("")
        []
    """
    text = _CAMEL_BOUNDARY.sub(" ", text)
    text = _NON_WORD.sub(" ", text)
    return [t for t in text.lower().split() if t]
