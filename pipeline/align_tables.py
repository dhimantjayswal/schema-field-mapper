"""Stage 1 — table/collection alignment.

Only 3 source tables vs. 3 destination collections here, so a lightweight
name + field-vocabulary overlap heuristic is used instead of an LLM call —
see WRITEUP.md for why that's the right call at this scale.
"""
import re

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
    words = re.split(r"[_\W]+", name.lower())
    return {w for w in words if w and w not in _STOPWORDS}


def _name_score(table_tokens: set[str], collection: str) -> float:
    """1.0 if the table's core token (or its expansion) stems into the
    collection name, else 0.0 — e.g. 'dept' expands to 'department', which
    is a prefix of 'departments'. Plain substring matching alone misses
    abbreviations like this.
    """
    collection = collection.lower()
    singular = collection[:-1] if collection.endswith("s") else collection
    for token in table_tokens:
        for candidate in (token, _ABBREVIATIONS.get(token, token)):
            if candidate in collection or singular in candidate or candidate in singular:
                return 1.0
    return 0.0


def align_tables() -> list[dict]:
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
