"""`pipeline.evaluate.score_mapping` regression tests.

Exercises the three failure modes it's built to catch: a wrong prediction
(`accuracy_at_1`), a hallucinated destination path that doesn't exist in
the real schema (`path_validity`), and a field correctly left unmapped
(`expected: None` in gold) vs. one wrongly forced to a match. Builds tiny
inline `_table`/`_fm` fixtures rather than importing real pipeline output,
so these stay independent of any LLM/embedder behavior.
"""
from pipeline.evaluate import score_mapping

_GOLD = {
    "locations": {
        "loc_id": {"expected": "_id", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "tz_cd": {"expected": "timezone", "alternatives": [], "difficulty": "easy", "rationale": ""},
    },
}


def _table(field_mappings, unmapped=None):
    """Wrap `field_mappings` into a one-table `document` shaped like
    `pipeline.assemble.assemble`'s output, scoped to `_GOLD`'s "locations" table."""
    return {
        "tables": [{
            "source_table": "locations", "destination_collection": "locations",
            "field_mappings": field_mappings,
            "unmapped_source_fields": unmapped or [],
            "unmapped_destination_fields": [],
        }],
    }


def _fm(source_field, destination_field, confidence=0.9):
    """Build one `field_mappings` entry dict with placeholder
    type_transform/reasoning — only the fields these tests actually assert on matter."""
    return {"source_field": source_field, "destination_field": destination_field,
            "type_transform": "x", "confidence": confidence, "reasoning": "r", "notes": None}


def test_perfect_prediction_scores_100_percent():
    """Both fields mapped to their gold destination scores 1.0 on every metric."""
    document = _table([_fm("loc_id", "_id"), _fm("tz_cd", "timezone")])
    result = score_mapping(document, _GOLD)
    assert result["accuracy_at_1"] == 1.0
    assert result["path_validity"] == 1.0
    assert result["misses"] == []


def test_wrong_prediction_is_a_miss():
    """A field mapped to the wrong (but valid) destination is recorded in `misses`."""
    document = _table([_fm("loc_id", "_id"), _fm("tz_cd", "code")])  # wrong target
    result = score_mapping(document, _GOLD)
    assert result["accuracy_at_1"] == 0.5
    assert result["misses"] == [{"field": "locations.tz_cd", "expected": "timezone", "predicted": "code"}]


def test_hallucinated_path_fails_path_validity():
    """A destination_field that doesn't exist in the real schema is caught by `path_validity`."""
    document = _table([_fm("loc_id", "_id"), _fm("tz_cd", "notARealField")])
    result = score_mapping(document, _GOLD)
    assert result["path_validity"] == 0.5
    assert result["invalid_paths"] == ["locations.tz_cd -> notARealField"]


def test_correctly_flagged_no_match_field_scores_correct():
    """A field gold expects to have no destination, correctly left unmapped, scores correct."""
    gold = {"locations": {"loc_id": {"expected": None, "alternatives": [],
                                      "difficulty": "hard", "rationale": "no target"}}}
    document = _table([], unmapped=["loc_id"])
    result = score_mapping(document, gold)
    assert result["accuracy_at_1"] == 1.0


def test_forcing_a_match_on_a_no_match_field_is_a_miss():
    """A field gold expects unmapped, but the pipeline forced a match on, scores as a miss."""
    gold = {"locations": {"loc_id": {"expected": None, "alternatives": [],
                                      "difficulty": "hard", "rationale": "no target"}}}
    document = _table([_fm("loc_id", "_id")])  # forced a match where gold says none exists
    result = score_mapping(document, gold)
    assert result["accuracy_at_1"] == 0.0
