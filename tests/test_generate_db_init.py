"""Regression test for scripts/generate_db_init.py's Mongo schema
reconstruction — a real bug here (double-wrapped nested `properties`)
was caught by inspecting the generated output, not by an earlier version
of this test. Locking in the fix so it can't silently regress.
"""
import json

from data.dest_schema import DEST_SCHEMA
from data.source_schema import SOURCE_SCHEMA
from scripts.generate_db_init import _nest, _tree_to_properties, generate_mysql_ddl


def _leaf_paths(node, prefix=""):
    """Flatten a `$jsonSchema` `properties` tree (as built by
    `_tree_to_properties`) back into dot-paths, e.g.
    `{"employment": {"properties": {"status": ...}}}` -> `["employment.status"]`
    — the inverse of `_nest`, used to check nothing was lost or double-wrapped."""
    out = []
    for key, value in node.get("properties", {}).items():
        path = f"{prefix}{key}"
        if "properties" in value:
            out.extend(_leaf_paths(value, path + "."))
        else:
            out.append(path)
    return out


def test_reconstructed_paths_match_dest_schema_exactly():
    """Round-tripping every collection's fields through `_nest` + `_tree_to_properties`
    and flattening back with `_leaf_paths` reproduces the exact original path set."""
    for collection, fields in DEST_SCHEMA["collections"].items():
        schema = {"bsonType": "object", "properties": _tree_to_properties(_nest(fields))}
        json.dumps(schema)  # must be valid JSON, not just a Python dict
        reconstructed = sorted(_leaf_paths(schema))
        original = sorted(f["path"] for f in fields)
        assert reconstructed == original


def test_nested_group_is_wrapped_exactly_once():
    """The specific bug this test exists for: a nested group like
    `employment` must have `properties` directly under it, not under a
    second `bsonType: object` layer."""
    schema = {"bsonType": "object", "properties": _tree_to_properties(_nest(DEST_SCHEMA["collections"]["employees"]))}
    employment = schema["properties"]["employment"]
    assert employment["bsonType"] == "object"
    assert "startDate" in employment["properties"]
    assert "properties" not in employment["properties"].get("bsonType", "")


def test_mysql_ddl_creates_every_table_and_declares_every_fk():
    """The rendered DDL has one `CREATE TABLE` per source table and one
    `ADD FOREIGN KEY` per FK column in the schema."""
    ddl = generate_mysql_ddl()
    for table in SOURCE_SCHEMA["tables"]:
        assert f"CREATE TABLE {table} (" in ddl

    fk_count = sum(
        1 for cols in SOURCE_SCHEMA["tables"].values() for col in cols if col.get("fk")
    )
    assert ddl.count("ADD FOREIGN KEY") == fk_count
