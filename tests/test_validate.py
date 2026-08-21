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


def test_conflicting_destination_claims_keep_the_higher_confidence_one():
    """Regression test for a real bug found in a live run: the local model
    mapped both `dob` and `created_ts` to `meta.createdAt` (confidences 0.7
    and 0.8). Without conflict resolution, both ended up in the committed
    output as if valid."""
    raw = {
        "source_table": "emp_master",
        "destination_collection": "employees",
        "field_mappings": [
            {**_mapping("dob", "meta.createdAt"), "type_transform": "DATE", "confidence": 0.7,
             "reasoning": "dob is often stored as the creation date"},
            {**_mapping("created_ts", "meta.createdAt"), "type_transform": "DATETIME", "confidence": 0.8,
             "reasoning": "created_ts closely aligns with meta.createdAt"},
        ],
        "unmapped_source_fields": [],
    }

    table = validate_table_mapping(raw, table_confidence=0.9, table_reasoning="test")

    destinations = [fm.destination_field for fm in table.field_mappings]
    assert destinations.count("meta.createdAt") == 1
    assert "created_ts" in {fm.source_field for fm in table.field_mappings}
    assert "dob" in table.unmapped_source_fields
