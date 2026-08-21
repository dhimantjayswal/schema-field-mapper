"""Domain abbreviation lexicon for this dataset's HR/data-migration field names.

A small declarative dict, not a general NLP expander — seeded from the
abbreviations that actually appear in `legacy_hrm`/`people_platform`. Used to
expand tokens before they're compared, so `tz_cd` reads close to `timezone`
via its expansion rather than needing a literal substring match. A real run
against this dataset found `tz_cd -> timezone` failing to map without this —
see WRITEUP.md.
"""
from pipeline.names import tokenize

LEXICON = {
    "emp": "employee", "cd": "code", "nm": "name", "dt": "date",
    "ts": "timestamp", "sal": "salary", "lvl": "level", "mgr": "manager",
    "dept": "department", "loc": "location", "stat": "status", "rec": "record",
    "ctr": "center", "tz": "timezone", "dob": "date of birth",
    "prov": "province", "addr": "address", "qty": "quantity", "amt": "amount",
    "f": "first", "l": "last",
}


def expand(tokens: list[str]) -> list[str]:
    """Expand each token via `LEXICON`, leaving unknown tokens as-is.

    Args:
        tokens: Output of `pipeline.names.tokenize`.

    Returns:
        Tokens with any lexicon match replaced by its (possibly multi-word)
        expansion; expansions are re-tokenized so the result is always a
        flat list of single words.

    Example:
        >>> expand(["tz", "cd"])
        ['timezone', 'code']
        >>> expand(["dept", "stat"])
        ['department', 'status']
        >>> expand(["city"])
        ['city']
    """
    out = []
    for token in tokens:
        out.extend(tokenize(LEXICON.get(token, token)))
    return out
