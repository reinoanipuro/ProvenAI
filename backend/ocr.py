"""Read the text of pictures and scanned pages, with where each line is.

Uses OnnxTR, the ONNX build of docTR by Mindee (France): a local European OCR
model on ONNX Runtime, so no GPU and no data leaves the computer. The models
(about 50 MB) are downloaded once to ~/.cache/onnxtr.

Positions are fractions of the picture, from the top left: (x0, y0, x1, y1).
"""

import threading
from dataclasses import dataclass

DETECTION_MODEL = "fast_base"
RECOGNITION_MODEL = "crnn_mobilenet_v3_small"

_lock = threading.Lock()
_predictor = None


@dataclass
class Line:
    text: str
    box: tuple[float, float, float, float]


class OCRUnavailableError(RuntimeError):
    """The OCR package or its models could not be loaded."""


def _model():
    global _predictor
    with _lock:
        if _predictor is None:
            try:
                from onnxtr.models import ocr_predictor
            except ImportError as error:
                raise OCRUnavailableError("OCR is not installed. Run: pip install onnxtr[cpu]") from error
            _predictor = ocr_predictor(det_arch=DETECTION_MODEL, reco_arch=RECOGNITION_MODEL)
        return _predictor


def warm_up() -> None:
    """Load the model ahead of the first picture, so the first check is not slower."""
    try:
        _model()
    except Exception:  # noqa: BLE001 - a failed warm-up is reported on first use instead
        pass


def read_lines(image) -> list[Line]:
    """The text lines of one PIL image, top to bottom."""
    import numpy as np

    predictor = _model()
    with _lock:
        result = predictor([np.asarray(image.convert("RGB"))])
    lines = []
    for block in result.pages[0].blocks:
        for line in block.lines:
            text = " ".join(word.value for word in line.words).strip()
            if text:
                (x0, y0), (x1, y1) = line.geometry
                lines.append(Line(text, (float(x0), float(y0), float(x1), float(y1))))
    return reading_order(lines)


def reading_order(lines: list[Line]) -> list[Line]:
    """Each label followed by the line printed right below it.

    Drawings put labels side by side, so plain top-to-bottom order would mix
    "Cabin 5012 door" with the value under a label next to it. A line is
    followed by the closest line below that overlaps it horizontally, which
    keeps "Cabin 5012 door" / "Clear opening: 800 mm" together.
    """
    lines = sorted(lines, key=lambda line: (line.box[1], line.box[0]))
    below: dict[int, int] = {}
    taken: set[int] = set()
    for index, line in enumerate(lines):
        x0, y0, x1, y1 = line.box
        height = y1 - y0
        candidates = [
            other for other in range(len(lines))
            if other not in taken and other != index
            and 0 <= lines[other].box[1] - y1 + height * 0.3 <= height * 1.3
            and min(x1, lines[other].box[2]) - max(x0, lines[other].box[0]) > 0
        ]
        if candidates:
            nearest = min(candidates, key=lambda other: (lines[other].box[1], abs(lines[other].box[0] - x0)))
            below[index] = nearest
            taken.add(nearest)
    ordered: list[Line] = []
    for start in range(len(lines)):
        if start in taken:
            continue
        current: int | None = start
        while current is not None:
            ordered.append(lines[current])
            current = below.get(current)
    return ordered
