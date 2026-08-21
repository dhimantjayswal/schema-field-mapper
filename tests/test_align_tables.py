from pipeline.align_tables import align_tables


def test_alignment_matches_obvious_pairs():
    alignments = {a["source_table"]: a["destination_collection"] for a in align_tables()}
    assert alignments == {
        "emp_master": "employees",
        "dept_info": "departments",
        "locations": "locations",
    }


def test_alignments_carry_confidence_and_reasoning():
    for alignment in align_tables():
        assert 0.0 <= alignment["confidence"] <= 1.0
        assert alignment["reasoning"]
