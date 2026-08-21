from pipeline.evaluate import score_mapping

_GOLD = {
    "locations": {
        "loc_id": {"expected": "_id", "alternatives": [], "difficulty": "easy", "rationale": ""},
        "tz_cd": {"expected": "timezone", "alternatives": [], "difficulty": "easy", "rationale": ""},
    },
}


def _table(field_mappings, unmapped=None):
    return {
        "tables": [{
            "source_table": "locations", "destination_collection": "locations",
            "field_mappings": field_mappings,
            "unmapped_source_fields": unmapped or [],
            "unmapped_destination_fields": [],
        }],
    }


def _fm(source_field, destination_field, confidence=0.9):
    return {"source_field": source_field, "destination_field": destination_field,
            "type_transform": "x", "confidence": confidence, "reasoning": "r", "notes": None}


def test_perfect_prediction_scores_100_percent():
    document = _table([_fm("loc_id", "_id"), _fm("tz_cd", "timezone")])
    result = score_mapping(document, _GOLD)
    assert result["accuracy_at_1"] == 1.0
    assert result["path_validity"] == 1.0
    assert result["misses"] == []


def test_wrong_prediction_is_a_miss():
    document = _table([_fm("loc_id", "_id"), _fm("tz_cd", "code")])  # wrong target
    result = score_mapping(document, _GOLD)
    assert result["accuracy_at_1"] == 0.5
    assert result["misses"] == [{"field": "locations.tz_cd", "expected": "timezone", "predicted": "code"}]


def test_hallucinated_path_fails_path_validity():
    document = _table([_fm("loc_id", "_id"), _fm("tz_cd", "notARealField")])
    result = score_mapping(document, _GOLD)
    assert result["path_validity"] == 0.5
    assert result["invalid_paths"] == ["locations.tz_cd -> notARealField"]


def test_correctly_flagged_no_match_field_scores_correct():
    gold = {"locations": {"loc_id": {"expected": None, "alternatives": [],
                                      "difficulty": "hard", "rationale": "no target"}}}
    document = _table([], unmapped=["loc_id"])
    result = score_mapping(document, gold)
    assert result["accuracy_at_1"] == 1.0


def test_forcing_a_match_on_a_no_match_field_is_a_miss():
    gold = {"locations": {"loc_id": {"expected": None, "alternatives": [],
                                      "difficulty": "hard", "rationale": "no target"}}}
    document = _table([_fm("loc_id", "_id")])  # forced a match where gold says none exists
    result = score_mapping(document, gold)
    assert result["accuracy_at_1"] == 0.0
