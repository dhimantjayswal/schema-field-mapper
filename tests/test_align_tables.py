"""Stage 1 (table/collection alignment) regression tests.

Locks in the one alignment the heuristic must always get right (all 3
tables to their obvious counterparts) and checks the confidence/reasoning
fields `pipeline.assemble.assemble` propagates into the final document are
always populated, not just present-but-empty.
"""
from pipeline.align_tables import align_tables


def test_alignment_matches_obvious_pairs():
    """All 3 source tables align to their obviously-correct destination collection."""
    alignments = {a["source_table"]: a["destination_collection"] for a in align_tables()}
    assert alignments == {
        "emp_master": "employees",
        "dept_info": "departments",
        "locations": "locations",
    }


def test_alignments_carry_confidence_and_reasoning():
    """Every alignment has an in-range confidence and a non-empty reasoning string."""
    for alignment in align_tables():
        assert 0.0 <= alignment["confidence"] <= 1.0
        assert alignment["reasoning"]
