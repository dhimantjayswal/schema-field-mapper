"""Stage 1 — table/collection alignment.

Only 3 source tables vs. 3 destination collections here, so a lightweight
name + field-vocabulary overlap heuristic is used instead of an LLM call —
see WRITEUP.md for why that's the right call at this scale.
"""
from pipeline.names import tokenize
from pipeline.parse_schema import (
    dest_collections,
    fields_for_collection,
    fields_for_table,
    source_tables,
)

_STOPWORDS = {"master", "info", "data", "tbl"}

# Small, closed set of standard HR shorthand — not a general abbreviation
# solver, just enough to bridge this assignment's actual table names.
_ABBREVIATIONS = {"dept": "department", "emp": "employee", "loc": "location"}


def _tokens(name: str) -> set[str]:
    """Tokenize a table/collection name and drop generic suffixes.

    Args:
        name: A table or collection name, e.g. "dept_info".

    Returns:
        The name's tokens with `_STOPWORDS` removed.

    Example:
        >>> _tokens("dept_info")
        {'dept'}
        >>> _tokens("departments")
        {'departments'}
    """
    return {t for t in tokenize(name) if t not in _STOPWORDS}


def _name_score(table_tokens: set[str], collection: str) -> float:
    """Score how well a table's name tokens match a collection's name.

    1.0 if any table token (or its `_ABBREVIATIONS` expansion) stems into
    the collection name, else 0.0 — e.g. 'dept' expands to 'department',
    which is a prefix of 'departments'. Plain substring matching alone
    misses abbreviations like this.

    Args:
        table_tokens: Tokens from `_tokens(table_name)`.
        collection: A destination collection name, e.g. "departments".

    Returns:
        1.0 (match) or 0.0 (no match) — this is a hard yes/no signal, not
        a graded similarity; `align_tables` blends it with field-vocabulary
        overlap for the final score.

    Example:
        >>> _name_score({"dept"}, "departments")
        1.0
        >>> _name_score({"dept"}, "employees")
        0.0
    """
    collection = collection.lower()
    singular = collection[:-1] if collection.endswith("s") else collection
    for token in table_tokens:
        for candidate in (token, _ABBREVIATIONS.get(token, token)):
            if candidate in collection or singular in candidate or candidate in singular:
                return 1.0
    return 0.0


def align_tables() -> list[dict]:
    """Stage 1: match each source table to its best destination collection.

    Only 3-vs-3 here, so this uses a lightweight heuristic (`_name_score`
    blended with source/destination field-name overlap) instead of an LLM
    call — see WRITEUP.md for why that trade-off makes sense at this scale.

    Returns:
        One dict per source table, in `source_tables()` order:
        `{"source_table", "destination_collection", "confidence", "reasoning"}`.
        This is the outer `tables[].confidence` / `.reasoning` in the
        final mapping document (see `pipeline.assemble.assemble`).

    Example:
        >>> alignments = align_tables()
        >>> [(a["source_table"], a["destination_collection"]) for a in alignments]
        [('emp_master', 'employees'), ('dept_info', 'departments'), ('locations', 'locations')]
    """
    alignments = []
    for table in source_tables():
        table_tokens = _tokens(table)
        source_field_names = {f.field.split("_")[-1].lower() for f in fields_for_table(table)}

        best_collection, best_score = None, -1.0
        for collection in dest_collections():
            name_score = _name_score(table_tokens, collection)

            dest_field_names = {f.path.split(".")[-1].lower() for f in fields_for_collection(collection)}
            field_overlap = len(
                {n for n in source_field_names if n in dest_field_names}
            ) / max(len(source_field_names), 1)

            score = 0.7 * name_score + 0.3 * field_overlap
            if score > best_score:
                best_collection, best_score = collection, score

        confidence = round(min(0.99, 0.6 + best_score * 0.4), 2)
        alignments.append({
            "source_table": table,
            "destination_collection": best_collection,
            "confidence": confidence,
            "reasoning": (
                f"'{table}' and '{best_collection}' share overlapping name tokens "
                "and field vocabulary consistent with representing the same entity."
            ),
        })
    return alignments
