"""Render a regulation PDF page with the cited quote highlighted.

This lets the engineer see the exact requirement on the page itself, not only
as copied text. The same approach can later highlight problems on drawings.
"""

import io
import re
from pathlib import Path

from .rag import REGULATIONS_DIR

RENDER_SCALE = 1.6
WINDOW_WORDS = 4
HIGHLIGHT = (255, 214, 0, 110)
OUTLINE = (214, 120, 0, 255)


def regulation_path(filename: str, regulations_dir: Path = REGULATIONS_DIR) -> Path:
    """Only files directly inside the regulations folder can be opened."""
    path = regulations_dir / filename
    if Path(filename).name != filename or path.suffix.lower() != ".pdf" or not path.is_file():
        raise FileNotFoundError(f"{filename} is not a regulation PDF in the project.")
    return path


def _quote_windows(quote: str) -> list[str]:
    """Short overlapping word runs, so a quote split across lines can still be found."""
    words = re.sub(r"[\x02­]\s*", "", quote).split()
    if len(words) <= WINDOW_WORDS:
        return [" ".join(words)] if words else []
    return [" ".join(words[start : start + WINDOW_WORDS]) for start in range(len(words) - WINDOW_WORDS + 1)]


def _quote_matches(textpage, windows: list[str]) -> list[tuple[int, int]]:
    """Find the quote as one unbroken run of word windows.

    A short phrase like "of walking surfaces shall" can appear elsewhere on the
    page. Only matches that follow each other in order, as the quote does, are
    kept, so the highlight marks the quote and nothing else.
    """
    found: list[list[tuple[int, int]]] = []
    for window in windows:
        searcher = textpage.search(window, match_case=False)
        hits = []
        while (hit := searcher.get_next()) is not None:
            hits.append(hit)
        searcher.close()
        found.append(hits)

    # best[i][j]: the longest run ending at match j of window i.
    best: list[list[tuple[int, int | None]]] = []
    for window_index, hits in enumerate(found):
        row = []
        for index, _ in hits:
            length, previous = 1, None
            if window_index and best[window_index - 1]:
                for prev_j, (prev_index, prev_count) in enumerate(found[window_index - 1]):
                    gap = index - prev_index
                    if 0 < gap <= prev_count + 3 and best[window_index - 1][prev_j][0] + 1 > length:
                        length, previous = best[window_index - 1][prev_j][0] + 1, prev_j
            row.append((length, previous))
        best.append(row)

    end = max(
        ((length, window_index, j) for window_index, row in enumerate(best) for j, (length, _) in enumerate(row)),
        default=None,
    )
    if end is None:
        return []
    _, window_index, j = end
    chain: list[tuple[int, int]] = []
    while j is not None:
        chain.append(found[window_index][j])
        j = best[window_index][j][1]
        window_index -= 1
    return chain


def render_highlighted_page(filename: str, page_number: int, quote: str = "") -> tuple[bytes, int]:
    """Return a PNG of the page and how many places were highlighted."""
    import pypdfium2
    from PIL import Image, ImageDraw

    document = pypdfium2.PdfDocument(str(regulation_path(filename)))
    try:
        if not 1 <= page_number <= len(document):
            raise ValueError(f"{filename} has no page {page_number}.")
        page = document[page_number - 1]
        page_height = page.get_height()
        image = page.render(scale=RENDER_SCALE).to_pil().convert("RGBA")
        overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        textpage = page.get_textpage()
        boxes: set[tuple[int, int, int, int]] = set()
        for index, count in _quote_matches(textpage, _quote_windows(quote)):
            for rect_index in range(textpage.count_rects(index, count)):
                left, bottom, right, top = textpage.get_rect(rect_index)
                boxes.add((
                    int(left * RENDER_SCALE) - 2,
                    int((page_height - top) * RENDER_SCALE) - 2,
                    int(right * RENDER_SCALE) + 2,
                    int((page_height - bottom) * RENDER_SCALE) + 2,
                ))
        for box in boxes:
            draw.rectangle(box, fill=HIGHLIGHT, outline=OUTLINE, width=2)
        textpage.close()
        page.close()

        output = io.BytesIO()
        Image.alpha_composite(image, overlay).convert("RGB").save(output, format="PNG")
        return output.getvalue(), len(boxes)
    finally:
        document.close()
