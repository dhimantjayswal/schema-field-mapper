"""Score a generated mapping document against the hand-curated gold mapping.

Deliberately separate from the pytest suite (`tests/`): testing asks "does
the code do what I wrote," evaluation asks "are the mappings actually
correct." Conflating them means asserting on live, non-deterministic LLM
output inside a test suite — a flaky build waiting to happen. This module
is pure and deterministic; it just compares two already-materialized JSON
structures.
"""
from pipeline.parse_schema import fields_for_collection

_DIFFICULTIES = ("easy", "medium", "hard")


def score_mapping(document: dict, gold: dict) -> dict:
    """Score one mapping document against `gold`.

    Three things are measured, matching the three ways this pipeline can
    fail silently: getting the wrong answer (`accuracy_at_1`), inventing a
    destination that doesn't exist (`path_validity`), and dropping a field
    entirely (`coverage` — expected to be 1.0 by construction, since
    `pipeline.validate.validate_table_mapping`'s completeness check makes
    it a structural guarantee rather than an empirical one).

    Args:
        document: A parsed mapping document — `pipeline.assemble.assemble`'s
            return value, or `json.load` of the file it wrote.
        gold: `data.gold_mapping.GOLD_MAPPING`-shaped:
            `{table: {source_field: {"expected", "alternatives",
            "difficulty", "rationale"}}}`. `expected: None` means the
            field has no destination and should end up in
            `unmapped_source_fields`.

    Returns:
        `{"n", "accuracy_at_1", "coverage", "path_validity",
        "by_difficulty": {difficulty: {"correct", "n", "accuracy"}},
        "invalid_paths": [...], "misses": [...]}`.

    Example:
        >>> from data.gold_mapping import GOLD_MAPPING
        >>> document = {"tables": [{
        ...     "source_table": "locations", "destination_collection": "locations",
        ...     "field_mappings": [
        ...         {"source_field": "loc_id", "destination_field": "_id",
        ...          "type_transform": "INT -> ObjectId", "confidence": 0.9,
        ...          "reasoning": "pk", "notes": None},
        ...     ],
        ...     "unmapped_source_fields": [
        ...         "loc_cd", "loc_nm", "city", "state_prov",
        ...         "country_cd", "postal_cd", "tz_cd",
        ...     ],
        ...     "unmapped_destination_fields": [],
        ... }]}
        >>> gold = {"locations": GOLD_MAPPING["locations"]}
        >>> result = score_mapping(document, gold)
        >>> result["n"]
        8
        >>> result["accuracy_at_1"]
        0.125
        >>> result["path_validity"]
        1.0
    """
    valid_paths = {
        collection: {f.path for f in fields_for_collection(collection)}
        for table in document["tables"]
        for collection in [table["destination_collection"]]
    }

    total = correct = 0
    invalid_paths = []
    misses = []
    by_difficulty = {d: [0, 0] for d in _DIFFICULTIES}

    for table in document["tables"]:
        source_table = table["source_table"]
        gold_fields = gold.get(source_table, {})
        predicted = {fm["source_field"]: fm["destination_field"] for fm in table["field_mappings"]}
        unmapped = set(table["unmapped_source_fields"])

        for fm in table["field_mappings"]:
            if fm["destination_field"] not in valid_paths.get(table["destination_collection"], set()):
                invalid_paths.append(f"{source_table}.{fm['source_field']} -> {fm['destination_field']}")

        for source_field, entry in gold_fields.items():
            total += 1
            expected = entry["expected"]
            difficulty = entry["difficulty"]
            by_difficulty.setdefault(difficulty, [0, 0])
            by_difficulty[difficulty][1] += 1

            if expected is None:
                is_correct = source_field in unmapped and source_field not in predicted
                got = "unmapped" if source_field in unmapped else predicted.get(source_field, "unmapped")
            else:
                acceptable = {expected, *entry["alternatives"]}
                got = predicted.get(source_field, "unmapped")
                is_correct = got in acceptable

            if is_correct:
                correct += 1
                by_difficulty[difficulty][0] += 1
            else:
                misses.append({"field": f"{source_table}.{source_field}", "expected": expected, "predicted": got})

    gold_field_count = sum(len(fields) for fields in gold.values())

    return {
        "n": total,
        "accuracy_at_1": round(correct / total, 4) if total else 0.0,
        "coverage": round(total / gold_field_count, 4) if gold_field_count else 0.0,
        "path_validity": round(1 - len(invalid_paths) / max(_count_mappings(document), 1), 4),
        "invalid_paths": invalid_paths,
        "by_difficulty": {
            d: {"correct": c, "n": n, "accuracy": round(c / n, 4) if n else None}
            for d, (c, n) in by_difficulty.items() if n
        },
        "misses": misses,
    }


def _count_mappings(document: dict) -> int:
    """Total `field_mappings` entries across all tables — the denominator
    for `path_validity`."""
    return sum(len(t["field_mappings"]) for t in document["tables"])
