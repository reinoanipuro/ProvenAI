"""Draw a random 2D deck plan as a PNG picture, with an answer key.

    python scripts/make_plan_picture.py                    random seed
    python scripts/make_plan_picture.py --seed 7 --out data/samples/designs/deck_plan.png

Cabins, a corridor, doors and a stair are drawn with dimension labels, like a
plan exported as a picture. The values are random and the answer key comes
from the limits as the regulations state them (see make_random_plan.py), so it
is independent of the checker.
"""

import argparse
import json
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_random_plan import SPECS, _value  # noqa: E402

WIDTH, HEIGHT = 1800, 1100
SPEC = {spec[0]: spec for spec in SPECS}


def _font(size: int):
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def build(seed: int) -> tuple[Image.Image, list[dict]]:
    rng = random.Random(seed)
    deck = rng.randint(3, 11)
    image = Image.new("RGB", (WIDTH, HEIGHT), "white")
    draw = ImageDraw.Draw(image)
    text, small, title = _font(24), _font(20), _font(34)
    key: list[dict] = []

    def label(x: int, y: int, name: str, attribute: str) -> None:
        spec = SPEC[attribute]
        value, expected = _value(rng, spec)
        wording = rng.choice([w for w in spec[2] if not w.endswith(".")])
        draw.text((x, y), name, fill="black", font=text)
        draw.text((x, y + 30), wording.format(v=value), fill="black", font=text)
        value_text = f"1:{value}" if spec[4] == "ratio" else f"{value} {spec[4]}"
        key.append({"element": name, "attribute": attribute, "value_text": value_text, "expected": expected, "page": 1})

    # Hull outline, corridor and cabins.
    draw.rectangle([60, 120, WIDTH - 60, HEIGHT - 120], outline="black", width=5)
    corridor_top, corridor_bottom = 500, 620
    draw.line([60, corridor_top, WIDTH - 60, corridor_top], fill="black", width=3)
    draw.line([60, corridor_bottom, WIDTH - 60, corridor_bottom], fill="black", width=3)
    cabins = rng.sample(range(10, 60), 4)
    for index, x in enumerate(range(60, WIDTH - 360, 360)):
        draw.rectangle([x, 120, x + 360, corridor_top], outline="black", width=3)
        draw.rectangle([x, corridor_bottom, x + 360, HEIGHT - 120], outline="black", width=3)
        # Door openings into the corridor.
        draw.rectangle([x + 140, corridor_top - 6, x + 230, corridor_top + 6], fill="white")
        draw.arc([x + 140, corridor_top - 90, x + 320, corridor_top + 90], 180, 270, fill="black", width=2)
        if index < len(cabins):
            draw.text((x + 20, 140), f"CABIN {deck}{cabins[index]:03d}", fill="black", font=small)
    # Stair at the aft end.
    for step in range(10):
        draw.line([WIDTH - 340, 660 + step * 30, WIDTH - 80, 660 + step * 30], fill="black", width=2)

    label(440, 200, f"Cabin {deck}{cabins[1]:03d} entrance door", "door_clear_width")
    label(800, 330, f"Accessible cabin {deck}{cabins[2]:03d}", "turning_space_diameter")
    label(80, 535, f"Passenger corridor {deck}-{rng.randint(1, 20):02d}", "walking_route_clear_width")
    label(80, 700, f"Cabin {deck}{cabins[0]:03d} door threshold", "door_threshold_height")
    label(500, 820, f"Accessible toilet {deck}-{rng.randint(1, 40):02d}", "toilet_seat_height")
    label(1160, 700, f"Cabin {deck}{cabins[3]:03d} light switch", "high_forward_reach_height")
    label(560, 995, f"Stair to deck {deck + 1}, handrail", "handrail_height")

    draw.text((60, 40), f"DECK {deck} - GENERAL ARRANGEMENT (PICTURE)", fill="black", font=title)
    draw.rectangle([WIDTH - 520, HEIGHT - 100, WIDTH - 60, HEIGHT - 20], outline="black", width=2)
    draw.text((WIDTH - 505, HEIGHT - 90), f"Project RV-{seed:04d}   Rev A", fill="black", font=small)
    draw.text((WIDTH - 505, HEIGHT - 60), "Dimensions in millimetres", fill="black", font=small)
    return image, key


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out", type=Path, default=Path("data/samples/designs/deck_plan.png"))
    args = parser.parse_args()
    seed = args.seed if args.seed is not None else random.randrange(10_000)
    image, key = build(seed)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    image.save(args.out)
    key_path = args.out.with_suffix(".key.json")
    key_path.write_text(json.dumps({"seed": seed, "items": key}, indent=2), encoding="utf-8")
    fails = sum(item["expected"] == "FAIL" for item in key)
    print(f"Wrote {args.out} (seed {seed}): {len(key)} values, {fails} should fail.")
    print(f"Answer key: {key_path}")


if __name__ == "__main__":
    main()
