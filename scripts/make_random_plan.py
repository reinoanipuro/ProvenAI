"""Write a random ship design planning document as a text PDF, with an answer key.

    python scripts/make_random_plan.py                     random seed
    python scripts/make_random_plan.py --seed 7 --items 18
    python scripts/make_random_plan.py --out data/samples/designs/random_plan.pdf

The document mixes values that meet and break the requirements, written in
varied wording, with notes that no rule covers. The answer key is worked out
here from the limits as the regulations state them, not from the checker's
code, so it is an independent test. Mistral never sees the key.
"""

import argparse
import json
import random
from pathlib import Path

# (attribute, element names, wordings, limits as the regulation states them, unit, how values are drawn)
# Limits: (minimum, maximum) in the unit shown; None means no limit on that side.
SPECS = [
    ("walking_route_clear_width", ["Passenger corridor {deck}-{n:02d}", "Crew corridor {deck}-{n:02d}", "Accessible route to cabin {deck}{n:03d}"],
     ["Clear width: {v} mm", "Clear corridor width {v} mm", "The corridor has a clear width of {v} mm."], (915, None), "mm", (700, 1200)),
    ("door_clear_width", ["Cabin {deck}{n:03d} entrance door", "Door to public toilet {deck}-{n:02d}", "Accessible cabin {deck}{n:03d} door"],
     ["Clear opening: {v} mm", "Door clear width {v} mm", "The door gives a clear opening of {v} mm."], (815, None), "mm", (700, 950)),
    ("ramp_running_slope", ["Ramp to the pool deck", "Ramp at the aft lobby, deck {deck}", "Gangway ramp, deck {deck}"],
     ["Running slope: 1:{v}", "Ramp running slope 1:{v}", "The ramp rises with a running slope of 1:{v}."], (12, None), "ratio", (8, 16)),
    ("handrail_height", ["Stair to deck {deck}, handrail", "Ramp handrail, deck {deck}", "Lobby stair handrail {n}"],
     ["Height above stair nosings: {v} mm", "Handrail height {v} mm", "The handrail top is {v} mm above the walking surface."], (865, 965), "mm", (780, 1050)),
    ("turning_space_diameter", ["Accessible cabin {deck}{n:03d}", "Accessible toilet {deck}-{n:02d}"],
     ["Turning space diameter: {v} mm", "Free turning circle {v} mm", "A turning space of {v} mm diameter is provided."], (1525, None), "mm", (1300, 1800)),
    ("door_threshold_height", ["Cabin {deck}{n:03d} door threshold", "Balcony door {deck}{n:03d} threshold"],
     ["Threshold height: {v} mm", "Raised threshold {v} mm", "The threshold is {v} mm high."], (None, 13), "mm", (5, 25)),
    ("toilet_seat_height", ["Accessible toilet {deck}-{n:02d}", "Cabin {deck}{n:03d} bathroom"],
     ["Seat height: {v} mm", "Toilet seat height {v} mm", "The water closet seat is {v} mm above the floor."], (430, 485), "mm", (380, 530)),
    ("table_counter_height", ["Restaurant table, deck {deck}", "Reception counter, deck {deck}", "Bar counter {n}"],
     ["Top height: {v} mm", "Counter top height {v} mm", "The table top is at {v} mm."], (710, 865), "mm", (650, 950)),
    ("high_forward_reach_height", ["Cabin {deck}{n:03d} light switch", "Elevator call button, deck {deck}"],
     ["Mounting height: {v} mm", "Control height {v} mm", "The control is mounted at {v} mm."], (None, 1220), "mm", (1000, 1400)),
    ("superstructure_door_sill_height", ["Superstructure end bulkhead door, frame {f}", "Forward superstructure end door, frame {f}"],
     ["Sill height: {v} mm", "Door sill height {v} mm above deck", "The sill of the access opening is {v} mm above the deck."], (380, None), "mm", (250, 500)),
    ("guard_rail_height", ["Open deck guard rail, deck {deck}", "Sun deck railing, deck {deck}", "Mooring deck guard rail"],
     ["Rail height: {v} mm", "Guard rail height {v} mm", "The guard rail is {v} mm high from the deck."], (1000, None), "mm", (850, 1200)),
    ("ballast_water_exchange_efficiency", ["Ballast water exchange system", "Ballast water management system"],
     ["Volumetric exchange efficiency: {v} %", "Exchange efficiency {v} %", "The system exchanges {v} % of the ballast water volume."], (95, None), "%", (88, 99)),
]
# Notes no rule covers: the right answer is "not checked", never a FAIL.
UNCOVERED = [
    "Hull bottom plate thickness: {v} mm",
    "Main engine room deck height {v} mm above baseline",
    "Fresh water tank capacity {v} m3",
    "Cabin {deck}{n:03d} floor area {v} m2",
]
FILLER = [
    "Arrangement follows the outline specification, revision C.",
    "Dimensions are taken from the latest general arrangement.",
    "Final figures to be confirmed by the yard after detail design.",
    "All doors on accessible routes are side-hinged.",
]


def _value(rng: random.Random, spec) -> tuple[float, str]:
    """A value at least 2 % away from any limit, so rounding cannot change the answer."""
    attribute, _, _, (low, high), unit, (lo, hi) = spec
    limits = [limit for limit in (low, high) if limit is not None]
    while True:
        value = rng.randint(lo, hi)
        if all(abs(value - limit) / limit >= 0.02 for limit in limits):
            break
    if unit == "ratio":
        # 1:N is steeper for a smaller N, so "minimum 12" means at least 1:12.
        ok = value >= low
    else:
        ok = (low is None or value >= low) and (high is None or value <= high)
    return value, "PASS" if ok else "FAIL"


def build(seed: int, count: int) -> tuple[list[list[str]], list[dict]]:
    rng = random.Random(seed)
    pages: list[list[str]] = []
    key: list[dict] = []
    used_values: set[str] = set()
    decks = rng.sample(range(2, 12), 3)
    per_page = max(3, count // len(decks) + 1)
    specs = (SPECS * (count // len(SPECS) + 1))[:count]
    rng.shuffle(specs)
    for page_number, deck in enumerate(decks, start=1):
        lines = [f"SHIP DESIGN PLANNING NOTES - DECK {deck}", f"Project RV-{seed:04d}, page {page_number}", ""]
        for spec in specs[(page_number - 1) * per_page : page_number * per_page]:
            attribute, names, wordings = spec[0], spec[1], spec[2]
            while True:
                value, expected = _value(rng, spec)
                if str(value) not in used_values:
                    used_values.add(str(value))
                    break
            # Each element gets its own name: one name with two values is a real conflict, not a test of a rule.
            for attempt in range(50):
                name = rng.choice(names).format(deck=deck, n=rng.randint(1, 60), f=rng.randint(20, 140))
                if attempt >= 20:
                    name += f" no. {attempt}"
                if name not in used_values:
                    used_values.add(name)
                    break
            wording = rng.choice(wordings)
            text = wording.format(v=value)
            if wording.endswith("."):
                lines.append(f"{name}: {text[0].lower()}{text[1:]}")
            else:
                lines += [name, text]
            value_text = f"1:{value}" if spec[4] == "ratio" else f"{value} {spec[4]}"
            key.append({"element": name, "attribute": attribute, "value_text": value_text,
                        "expected": expected, "page": page_number})
            if rng.random() < 0.3:
                lines.append(rng.choice(FILLER))
            lines.append("")
        uncovered = rng.choice(UNCOVERED).format(deck=deck, n=rng.randint(1, 60), v=rng.randint(12, 400))
        lines += [uncovered, ""]
        key.append({"element": uncovered.split(":")[0].split(" floor")[0], "attribute": "uncovered",
                    "value_text": uncovered, "expected": "NOT_CHECKED", "page": page_number})
        pages.append(lines)
    return pages, key


def write_pdf(pages: list[list[str]], path: Path) -> None:
    """A minimal text PDF with Helvetica, so every line has a real text layer."""
    def escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objects: list[bytes] = []
    page_ids = []
    font_id = 3
    for lines in pages:
        content = ["BT", "/F1 11 Tf", "14 TL", "56 790 Td"]
        for index, line in enumerate(lines):
            size = 14 if index == 0 else 11
            content += [f"/F1 {size} Tf", f"({escape(line)}) Tj", "T*"]
        content.append("ET")
        stream = "\n".join(content).encode("latin-1")
        content_id = 4 + len(objects)
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        page_id = 4 + len(objects)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 {font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>".encode()
        )
        page_ids.append(page_id)
    header = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{pid} 0 R' for pid in page_ids)}] /Count {len(page_ids)} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(header + objects, start=1):
        offsets.append(len(output))
        output += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    output += f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(output))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--items", type=int, default=15, help="checkable items (default 15)")
    parser.add_argument("--out", type=Path, default=Path("data/samples/designs/random_plan.pdf"))
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else random.randrange(10_000)
    pages, key = build(seed, args.items)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_pdf(pages, args.out)
    key_path = args.out.with_suffix(".key.json")
    key_path.write_text(json.dumps({"seed": seed, "items": key}, indent=2), encoding="utf-8")
    fails = sum(item["expected"] == "FAIL" for item in key)
    print(f"Wrote {args.out} ({len(pages)} pages, seed {seed}): {len(key)} items, {fails} should fail.")
    print(f"Answer key: {key_path}")


if __name__ == "__main__":
    main()
