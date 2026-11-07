"""Write a realistic ship design specification PDF with known right and wrong values.

    python scripts/make_design_spec.py
    python scripts/make_design_spec.py --out somewhere/spec.pdf

The ship (MV Nordic Aurora) and the document are made up. Every checkable
value is chosen on purpose to meet or break a limit as the regulation states
it, with a clear margin, and the answer key (.key.json next to the PDF) says
which. Values no rule covers are expected to be "not checked".
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_random_plan import write_pdf  # noqa: E402

# (page, line as written, element, value as written, expected, why)
ITEMS: list[tuple[int, str, str, str, str, str]] = []
PAGES: list[list[str]] = []


def page(*lines: str) -> None:
    PAGES.append(list(lines))


def value(line: str, element: str, value_text: str, expected: str, why: str) -> str:
    ITEMS.append((len(PAGES) + 1, line, element, value_text, expected, why))
    return line


page(
    "MV NORDIC AURORA - DESIGN SPECIFICATION",
    "Document NA-2026-DS-06, revision B. Basic design, deck 6 and open decks.",
    "Prepared by the outfitting design team for regulatory review.",
    "",
    "1. GENERAL",
    "The vessel is a day passenger ship for coastal routes with 400 passengers.",
    "Main particulars are given for reference only and are not part of this review.",
    value("Length overall: 92.4 m", "Length overall", "92.4 m", "NOT_CHECKED", "no rule covers ship length"),
    value("Fresh water tank capacity: 45 m3", "Fresh water tank", "45 m3", "NOT_CHECKED", "no rule covers tank capacity"),
    value("Main engines: 2 x 3200 kW", "Main engines", "3200 kW", "NOT_CHECKED", "no rule covers engine power"),
    "",
    "2. ACCESSIBLE ROUTES AND CORRIDORS",
    "All public corridors on deck 6 form part of the accessible route.",
    value("Corridor 6-01, main passenger corridor: clear width 1100 mm.",
          "Corridor 6-01", "1100 mm", "PASS", "at least 915 mm required (ADA 403.5.1)"),
    value("Corridor 6-02, passenger corridor to the aft lounge: clear width 850 mm.",
          "Corridor 6-02", "850 mm", "FAIL", "65 mm below the 915 mm minimum"),
    value("Accessible route to cabin 6112: clear width 950 mm.",
          "Accessible route to cabin 6112", "950 mm", "PASS", "at least 915 mm required"),
    "",
    "3. DOORS",
    "Doors on accessible routes are side-hinged and open with one hand.",
    value("Cabin 6112 entrance door: clear opening 860 mm.",
          "Cabin 6112 entrance door", "860 mm", "PASS", "at least 815 mm required (ADA 404.2.3)"),
    value("Public toilet 6-03 door: clear opening 780 mm.",
          "Public toilet 6-03 door", "780 mm", "FAIL", "35 mm below the 815 mm minimum"),
    value("Cabin 6112 door threshold height: 10 mm.",
          "Cabin 6112 door threshold", "10 mm", "PASS", "at most 13 mm allowed (ADA 404.2.5)"),
    value("Balcony door 6120 threshold height: 22 mm.",
          "Balcony door 6120 threshold", "22 mm", "FAIL", "9 mm above the 13 mm maximum"),
    "",
    "4. RAMPS AND STAIRS",
    value("Ramp from the lobby to the pool deck: running slope 1:14.",
          "Ramp to the pool deck", "1:14", "PASS", "1:12 or flatter required (ADA 405.2)"),
    value("Aft lobby ramp: running slope 1:10.",
          "Aft lobby ramp", "1:10", "FAIL", "steeper than the 1:12 maximum"),
    value("Main stair to deck 7: handrail height 900 mm above the stair nosings.",
          "Main stair handrail", "900 mm", "PASS", "865 to 965 mm required (ADA 505.4)"),
    value("Crew stair aft: handrail height 1010 mm above the stair nosings.",
          "Crew stair aft handrail", "1010 mm", "FAIL", "45 mm above the 965 mm maximum"),
)

page(
    "MV NORDIC AURORA - DESIGN SPECIFICATION",
    "Document NA-2026-DS-06, revision B. Page 2.",
    "",
    "5. ACCESSIBLE CABIN 6112 AND PUBLIC SPACES",
    "Cabin 6112 is the accessible cabin on deck 6, next to the main lift.",
    value("Cabin 6112 wheelchair turning space: diameter 1600 mm.",
          "Cabin 6112 turning space", "1600 mm", "PASS", "at least 1525 mm required (ADA 304.3.1)"),
    value("Cabin 6112 bathroom: toilet seat height 450 mm.",
          "Cabin 6112 toilet", "450 mm", "PASS", "430 to 485 mm required (ADA 604.4)"),
    value("Cabin 6112 light switch: mounting height 1300 mm.",
          "Cabin 6112 light switch", "1300 mm", "FAIL", "80 mm above the 1220 mm maximum reach (ADA 308.2.1)"),
    value("Public toilet 6-03: toilet seat height 400 mm.",
          "Public toilet 6-03 toilet", "400 mm", "FAIL", "30 mm below the 430 mm minimum"),
    value("Reception counter, deck 6: counter top height 800 mm.",
          "Reception counter", "800 mm", "PASS", "710 to 865 mm required (ADA 902.3)"),
    value("Aft lounge bar counter: counter top height 960 mm.",
          "Aft lounge bar counter", "960 mm", "FAIL", "95 mm above the 865 mm maximum"),
    "",
    "6. OPEN DECKS AND WEATHERTIGHT DOORS",
    value("Superstructure end bulkhead door, frame 52: sill height 460 mm above deck.",
          "Superstructure door frame 52", "460 mm", "PASS", "at least 380 mm required (Load Lines reg. 12(3))"),
    value("Forward superstructure end door, frame 118: sill height 300 mm above deck.",
          "Superstructure door frame 118", "300 mm", "FAIL", "80 mm below the 380 mm minimum"),
    value("Sun deck guard rail: height 1050 mm above the deck.",
          "Sun deck guard rail", "1050 mm", "PASS", "at least 1 m required (Load Lines reg. 25)"),
    value("Mooring deck guard rail: height 940 mm above the deck.",
          "Mooring deck guard rail", "940 mm", "FAIL", "60 mm below the 1 m minimum"),
    "",
    "7. BALLAST WATER",
    value("Ballast water exchange system: volumetric exchange efficiency 96 %.",
          "Ballast water exchange", "96 %", "PASS", "at least 95 % required (BWM D-1)"),
    "",
    "8. STRUCTURE (FOR INFORMATION)",
    value("Hull bottom plating thickness: 12 mm.", "Hull bottom plating", "12 mm", "NOT_CHECKED",
          "no rule in the project covers plate thickness"),
    "",
    "9. NOTES",
    "Final dimensions are confirmed after detail design and yard measurements.",
    "Deviations from this specification require approval by the design manager.",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=Path("data/samples/designs/ship_design_spec.pdf"))
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_pdf(PAGES, args.out)
    key = [{"page": page_number, "element": element, "value_text": value_text, "expected": expected, "why": why, "line": line}
           for page_number, line, element, value_text, expected, why in ITEMS]
    args.out.with_suffix(".key.json").write_text(json.dumps({"items": key}, indent=2), encoding="utf-8")
    counts = {status: sum(item["expected"] == status for item in key) for status in ("FAIL", "PASS", "NOT_CHECKED")}
    print(f"Wrote {args.out}: {len(key)} values: {counts['FAIL']} wrong, {counts['PASS']} right, "
          f"{counts['NOT_CHECKED']} that no rule covers.")


if __name__ == "__main__":
    main()
