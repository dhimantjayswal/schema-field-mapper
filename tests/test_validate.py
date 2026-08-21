import pytest
from pydantic import ValidationError

from pipeline.validate import validate_table_mapping


def _raw(field_mappings, unmapped=None):
    return {
        "source_table": "locations",
        "destination_collection": "locations",
        "field_mappings": field_mappings,
        "unmapped_source_fields": unmapped or [],
    }


def _mapping(source_field, destination_field="code"):
    return {
        "source_field": source_field,
        "destination_field": destination_field,
        "type_transform": "VARCHAR -> String",
        "confidence": 0.95,
        "reasoning": "test mapping",
        "notes": None,
    }


def test_forgotten_field_ends_up_unmapped_not_silently_dropped():
    # locations has 8 source fields; this batch only maps loc_id, leaving 7
    # neither mapped nor declared unmapped by the (simulated) LLM response.
    raw = _raw([{**_mapping("loc_id"), "destination_field": "_id", "type_transform": "INT -> ObjectId"}])

    table = validate_table_mapping(raw, table_confidence=0.9, table_reasoning="test")

    assert "loc_cd" in table.unmapped_source_fields
    assert "loc_id" not in table.unmapped_source_fields


def test_unmapped_destination_fields_computed_by_set_difference():
    raw = _raw([{**_mapping("loc_id"), "destination_field": "_id", "type_transform": "INT -> ObjectId"}])

    table = validate_table_mapping(raw, table_confidence=0.9, table_reasoning="test")

    assert "timezone" in table.unmapped_destination_fields
    assert "_id" not in table.unmapped_destination_fields


def test_confidence_out_of_range_is_rejected():
    raw = _raw([{**_mapping("loc_id"), "confidence": 1.5}])
    with pytest.raises(ValidationError):
        validate_table_mapping(raw, table_confidence=0.9, table_reasoning="test")
