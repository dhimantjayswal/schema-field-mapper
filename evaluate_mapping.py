#!/usr/bin/env python3
"""CLI: score output/mapping.json against the hand-curated gold mapping.

Pure, offline, no LLM call — see pipeline/evaluate.py for what's measured
and why. Run this any time a change to the pipeline should be checked
against ground truth, not just against the cold test suite (which checks
the code runs correctly, not that its answers are correct).
"""
import argparse
import json
import sys
from pathlib import Path

from data.gold_mapping import GOLD_MAPPING
from pipeline.evaluate import score_mapping

DEFAULT_MAPPING_PATH = Path(__file__).parent / "output" / "mapping.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Score a mapping.json against the gold mapping.")
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING_PATH)
    parser.add_argument("--fail-under", type=float, default=None,
                         help="exit 1 if accuracy_at_1 falls below this")
    args = parser.parse_args()

    document = json.loads(args.mapping.read_text())
    result = score_mapping(document, GOLD_MAPPING)

    print(f"n:              {result['n']}")
    print(f"accuracy@1:     {result['accuracy_at_1']:.2%}")
    print(f"coverage:       {result['coverage']:.2%}")
    print(f"path_validity:  {result['path_validity']:.2%}")
    print()
    print("by difficulty:")
    for difficulty, stats in result["by_difficulty"].items():
        print(f"  {difficulty:8s} {stats['correct']:>2}/{stats['n']:<2}  ({stats['accuracy']:.2%})")

    if result["invalid_paths"]:
        print("\nHALLUCINATED DESTINATION PATHS (should never happen):")
        for p in result["invalid_paths"]:
            print(f"  - {p}")

    if result["misses"]:
        print("\nmisses:")
        for m in result["misses"]:
            print(f"  {m['field']:35s} expected={m['expected']!r:30} predicted={m['predicted']!r}")

    if args.fail_under is not None and result["accuracy_at_1"] < args.fail_under:
        print(f"\naccuracy@1 {result['accuracy_at_1']:.2%} is below --fail-under {args.fail_under:.2%}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
