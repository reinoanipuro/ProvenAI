"""Check a random planning PDF end to end and compare the result with its answer key.

    python tests/eval_random_plan.py                 new random document
    python tests/eval_random_plan.py --seed 42       repeat a document
    python tests/eval_random_plan.py --pdf my.pdf --key my.key.json

Needs the regulation index and Ollama with the model, like the app. Runs the
same API the web app uses (/lovable), in this process, and saves each page as
a PNG with the FAIL marks drawn in red, where the app would draw them.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

from fastapi.testclient import TestClient  # noqa: E402

from backend.api import app  # noqa: E402

OUT = Path(".runtime/eval")


def _norm(text: str) -> str:
    return "".join(text.lower().split())


def outcome_for(item: dict, inspection: dict) -> tuple[str, dict | None]:
    """What the check said about one answer-key item, and the element it was found as."""
    value = _norm(item["value_text"])
    for element in inspection["elements"]:
        for attribute, attr in element["attrs"].items():
            if _norm(attr.get("value_text", "")) != value:
                continue
            results = [result for result in inspection["results"] if result["element_id"] == element["id"]
                       and attribute in result["required_inputs"]]
            statuses = {result["status"] for result in results}
            if "FAIL" in statuses:
                return "FAIL", element
            if statuses == {"PASS"}:
                return "PASS", element
            return "NOT_CHECKED", element
    return "NOT_READ", None


def save_marked_pages(pdf: Path, inspection: dict, out: Path) -> list[Path]:
    """Draw FAIL elements in red and PASS elements in green, at the positions the app uses."""
    import pypdfium2
    from PIL import ImageDraw

    failing = {result["element_id"] for result in inspection["results"] if result["status"] == "FAIL"}
    passing = {result["element_id"] for result in inspection["results"] if result["status"] == "PASS"} - failing
    scale = 1.5
    document = pypdfium2.PdfDocument(str(pdf))
    paths = []
    for index in range(len(document)):
        page = document[index]
        height = page.get_height()
        image = page.render(scale=scale).to_pil().convert("RGB")
        draw = ImageDraw.Draw(image)
        for element in inspection["elements"]:
            if element["page"] != index + 1 or element["bbox"] == [0, 0, 0, 0]:
                continue
            x0, y0, x1, y1 = element["bbox"]
            color = (200, 16, 46) if element["id"] in failing else (0, 140, 70) if element["id"] in passing else None
            if color:
                draw.rectangle([x0 * scale, (height - y1) * scale, x1 * scale, (height - y0) * scale], outline=color, width=3)
        path = out / f"{pdf.stem}-page{index + 1}.png"
        image.save(path)
        paths.append(path)
    document.close()
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--items", type=int, default=15)
    parser.add_argument("--pdf", type=Path)
    parser.add_argument("--key", type=Path)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    pdf = args.pdf
    if pdf is None:
        pdf = OUT / "random_plan.pdf"
        command = [sys.executable, "scripts/make_random_plan.py", "--items", str(args.items), "--out", str(pdf)]
        if args.seed is not None:
            command += ["--seed", str(args.seed)]
        subprocess.run(command, check=True)
    key = json.loads((args.key or pdf.with_suffix(".key.json")).read_text(encoding="utf-8"))["items"]

    client = TestClient(app)
    started = time.time()
    created = client.post("/lovable/inspections", data={"name": pdf.stem},
                          files=[("files", (pdf.name, pdf.read_bytes(), "application/pdf"))]).json()
    while True:
        inspection = client.get(f"/lovable/inspections/{created['id']}").json()
        if inspection["status"] in ("done", "error"):
            break
        time.sleep(2)
    if inspection["status"] == "error":
        sys.exit(f"Inspection failed: {inspection['progress']['label']}")

    counts = {"correct": 0, "missed_fail": 0, "false_fail": 0, "not_read": 0, "not_checked": 0}
    marked = 0
    for item in key:
        got, element = outcome_for(item, inspection)
        expected = item["expected"]
        if expected == "NOT_CHECKED":
            ok = got != "FAIL"
            label = "OK " if ok else "FALSE FAIL"
            counts["correct" if ok else "false_fail"] += 1
        elif got == expected:
            label, ok = "OK ", True
            counts["correct"] += 1
            marked += expected == "FAIL" and element is not None and element["bbox"] != [0, 0, 0, 0]
        elif got == "NOT_READ":
            label = "NOT READ"
            counts["not_read"] += 1
        elif got == "NOT_CHECKED":
            label = "NOT CHECKED"
            counts["not_checked"] += 1
        elif expected == "FAIL":
            label = "MISSED FAIL"
            counts["missed_fail"] += 1
        else:
            label = "FALSE FAIL"
            counts["false_fail"] += 1
        print(f"{label:<12} expected {expected:<11} got {got:<11} p{item['page']} {item['element'][:38]:<38} {item['value_text']}")

    total = len(key)
    should_fail = sum(item["expected"] == "FAIL" for item in key)
    print(f"\n{time.time() - started:.0f} s for {pdf.name}")
    print(f"Correct:                {counts['correct']}/{total} = {counts['correct'] / total:.0%}")
    print(f"Missed non-compliance:  {counts['missed_fail']}")
    print(f"False non-compliance:   {counts['false_fail']}")
    print(f"Value not read:         {counts['not_read']}")
    print(f"Read, but not checked:  {counts['not_checked']}")
    print(f"Failures marked on the page: {marked}/{should_fail}")
    for path in save_marked_pages(pdf, inspection, OUT):
        print(f"Marked page: {path}")


if __name__ == "__main__":
    main()
