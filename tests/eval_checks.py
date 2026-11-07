"""Measure how accurately the design check identifies compliant and non-compliant designs.

Run from the project root, after building the index:
    python tests/eval_checks.py           checks confirmed values (fast, no Mistral)
    python tests/eval_checks.py --llm     also lets Mistral read each case as text (slow)

Each case has a known correct answer worked out by hand from the regulation.
The report separates the two kinds of error that matter for trust:
- false non-compliance: a compliant design reported as failing
- missed non-compliance: a failing design reported as compliant
Cases sent to review are not counted as wrong, but are reported, because a
tool that sends everything to review is safe but not useful.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from backend.checker import check_design  # noqa: E402

# (element, property, attribute, value, expected overall result)
CASES = [
    ("Deck 5 passenger corridor", "clear width", "walking_route_clear_width", "800 mm", "FAIL"),
    ("Deck 5 passenger corridor", "clear width", "walking_route_clear_width", "915 mm", "PASS"),
    ("Deck 7 corridor", "clear width", "walking_route_clear_width", "36 in", "PASS"),
    ("Deck 7 corridor", "clear width", "walking_route_clear_width", "35 in", "FAIL"),
    ("Cabin door", "clear opening width", "door_clear_width", "850 mm", "PASS"),
    ("Cabin door", "clear opening width", "door_clear_width", "800 mm", "FAIL"),
    ("Pool deck ramp", "running slope", "ramp_running_slope", "1:12", "PASS"),
    ("Pool deck ramp", "running slope", "ramp_running_slope", "1:10", "FAIL"),
    ("Gangway ramp", "running slope", "ramp_running_slope", "6 %", "PASS"),
    ("Gangway ramp", "running slope", "ramp_running_slope", "5 degrees", "FAIL"),
    ("Stair handrail", "height", "handrail_height", "900 mm", "PASS"),
    ("Stair handrail", "height", "handrail_height", "1000 mm", "FAIL"),
    ("Stair handrail", "height", "handrail_height", "850 mm", "FAIL"),
    ("Accessible cabin", "turning space diameter", "turning_space_diameter", "1500 mm", "FAIL"),
    ("Accessible cabin", "turning space diameter", "turning_space_diameter", "1600 mm", "PASS"),
    ("Cabin door threshold", "height", "door_threshold_height", "10 mm", "PASS"),
    ("Cabin door threshold", "height", "door_threshold_height", "20 mm", "FAIL"),
    ("Accessible toilet", "seat height", "toilet_seat_height", "450 mm", "PASS"),
    ("Accessible toilet", "seat height", "toilet_seat_height", "400 mm", "FAIL"),
    ("Restaurant table", "top height", "table_counter_height", "750 mm", "PASS"),
    ("Bar counter", "top height", "table_counter_height", "900 mm", "FAIL"),
    ("Cabin light switch", "high forward reach height", "high_forward_reach_height", "1300 mm", "FAIL"),
    ("Cabin light switch", "high forward reach height", "high_forward_reach_height", "1200 mm", "PASS"),
    ("Superstructure end bulkhead door", "sill height", "superstructure_door_sill_height", "300 mm", "FAIL"),
    ("Superstructure end bulkhead door", "sill height", "superstructure_door_sill_height", "400 mm", "PASS"),
    ("Open deck guard rail", "height", "guard_rail_height", "1100 mm", "PASS"),
    ("Open deck guard rail", "height", "guard_rail_height", "900 mm", "FAIL"),
    ("Open deck guard rail", "height", "guard_rail_height", "1 m", "PASS"),
    ("Ballast water exchange", "volumetric efficiency", "ballast_water_exchange_efficiency", "96 %", "PASS"),
    ("Ballast water exchange", "volumetric efficiency", "ballast_water_exchange_efficiency", "92 %", "FAIL"),
    # No approved rule and no regulation text: the honest answer is "needs review".
    ("Hull bottom plate", "thickness", "unknown", "12 mm", "NEEDS_REVIEW"),
    # A value without a unit cannot be checked: also "needs review", never a guess.
    ("Deck 3 corridor", "clear width", "walking_route_clear_width", "800", "NEEDS_REVIEW"),
]


def run(use_llm: bool) -> None:
    from backend.rag import RegulatoryRetriever

    retriever = RegulatoryRetriever()
    llm = None
    if use_llm:
        from backend.llm import OllamaClient

        llm = OllamaClient()

    counts = {"correct": 0, "false_fail": 0, "missed_fail": 0, "review": 0, "other": 0}
    started = time.time()
    for element, measured, attribute, value, expected in CASES:
        if use_llm:
            text = f"{element}: {measured} {value}."
            result = check_design(text=text, llm=llm, retriever=retriever, summarize=False)
        else:
            item = {"element": element, "property": measured, "attribute": attribute, "value_text": value}
            result = check_design(items=[item], retriever=retriever, summarize=False)
        got = result["overall"]
        if got == expected:
            outcome = "correct"
        elif expected == "PASS" and got in ("FAIL", "ISSUES_FOUND"):
            outcome = "false_fail"
        elif expected == "FAIL" and got in ("PASS", "NO_ISSUES_FOUND"):
            outcome = "missed_fail"
        elif got == "NEEDS_REVIEW":
            outcome = "review"
        else:
            outcome = "other"
        counts[outcome] += 1
        mark = "OK " if outcome == "correct" else outcome.upper()
        print(f"{mark:<12} expected {expected:<13} got {got:<15} {element}: {measured} {value}")

    total = len(CASES)
    print(f"\nMode: {'Mistral reads the text' if use_llm else 'confirmed values'}, {time.time() - started:.0f} s")
    print(f"Correct:                {counts['correct']}/{total} = {counts['correct'] / total:.0%}")
    print(f"False non-compliance:   {counts['false_fail']}")
    print(f"Missed non-compliance:  {counts['missed_fail']}")
    print(f"Sent to review instead: {counts['review']}")
    if counts["other"]:
        print(f"Other mismatches:       {counts['other']}")


if __name__ == "__main__":
    run(use_llm="--llm" in sys.argv)
