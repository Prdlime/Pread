"""Turn a screenshot of code into plain text, locally and for free.

Uses the text recogniser built into macOS (the Vision framework), so nothing
is sent anywhere and no tokens are spent. The recogniser tells us where each
piece of text sits, which lets us rebuild the indentation and find where the
code is on screen.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass

import config


@dataclass
class Box:
    """One piece of recognised text. Pixels, origin at top-left, y points down."""
    text: str
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Line:
    label: int   # the number shown to Claude (the editor's own number if visible)
    text: str
    left: float = 0.0     # where this line sits in the image, in pixels
    top: float = 0.0
    right: float = 0.0
    bottom: float = 0.0


# ---------------------------------------------------------------- macOS part
def recognize(png_bytes: bytes, width: int, height: int) -> list[Box]:
    """Run macOS text recognition on a PNG image. Needs pyobjc (macOS only)."""
    import Vision
    from Foundation import NSData

    data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setUsesLanguageCorrection_(False)  # code is not normal English
    request.setRecognitionLanguages_(["en-US"])

    ok, error = handler.performRequests_error_([request], None)
    if not ok:
        raise RuntimeError(f"Text recognition failed: {error}")

    boxes: list[Box] = []
    for obs in request.results() or []:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        r = obs.boundingBox()  # normalised, origin at bottom-left
        boxes.append(Box(
            text=str(candidates[0].string()),
            x=r.origin.x * width,
            y=(1.0 - r.origin.y - r.size.height) * height,
            w=r.size.width * width,
            h=r.size.height * height,
        ))
    return boxes


# ------------------------------------------------------- pure Python part
def _char_width(boxes: list[Box]) -> float:
    widths = [b.w / len(b.text) for b in boxes if len(b.text) >= 3 and b.w > 0]
    return statistics.median(widths) if widths else 8.0


def _group_rows(boxes: list[Box]) -> list[list[Box]]:
    rows: list[list[Box]] = []
    for b in sorted(boxes, key=lambda b: b.cy):
        if rows and abs(b.cy - rows[-1][0].cy) < max(b.h, rows[-1][0].h) * 0.5:
            rows[-1].append(b)
        else:
            rows.append([b])
    for row in rows:
        row.sort(key=lambda b: b.x)
    return rows


_DIGITS = re.compile(r"^\d{1,4}$")


def _find_gutter(rows: list[list[Box]], cw: float) -> set[int]:
    """Return ids of boxes that are editor line numbers (a column of digits)."""
    cands = [row[0] for row in rows if _DIGITS.match(row[0].text.strip())]
    if len(cands) < 2:
        return set()
    lefts = [b.x for b in cands]
    rights = [b.right for b in cands]
    aligned = (max(lefts) - min(lefts) <= 1.5 * cw) or (max(rights) - min(rights) <= 1.5 * cw)
    return {id(b) for b in cands} if aligned else set()


def boxes_to_lines(boxes: list[Box]) -> tuple[list[Line], list[Box]]:
    """Rebuild lines of code (with indentation) from recognised text boxes.

    Returns the lines and the boxes that really are code (line numbers removed).
    """
    boxes = [b for b in boxes if b.text.strip()]
    if not boxes:
        return [], []
    cw = _char_width(boxes)
    rows = _group_rows(boxes)
    gutter = _find_gutter(rows, cw)

    code_rows: list[tuple[int | None, list[Box], Box]] = []
    for row in rows:
        number = None
        first = row[0]
        if id(first) in gutter:
            number = int(first.text.strip())
            row = row[1:]
        code_rows.append((number, row, first))

    code_boxes = [b for _, row, _ in code_rows for b in row]
    if not code_boxes:
        return [], []
    base_x = min(row[0].x for _, row, _ in code_rows if row)
    unit = max(1, config.INDENT_UNIT)

    lines: list[Line] = []
    next_label = 1
    for number, row, first in code_rows:
        label = number if number is not None else next_label
        next_label = label + 1
        geom = row or [first]
        left, top = min(b.x for b in geom), min(b.y for b in geom)
        right, bottom = max(b.right for b in geom), max(b.y + b.h for b in geom)
        if not row:
            lines.append(Line(label, "", left, top, right, bottom))
            continue
        spaces = round((row[0].x - base_x) / cw)
        spaces = round(spaces / unit) * unit
        text = " " * spaces + row[0].text.rstrip()
        for prev, cur in zip(row, row[1:]):
            gap = max(1, min(20, round((cur.x - prev.right) / cw)))
            text += " " * gap + cur.text.strip()
        lines.append(Line(label, text, left, top, right, bottom))
    return lines, code_boxes


def union_bbox(boxes: list[Box]) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) of all boxes, in pixels."""
    return (
        min(b.x for b in boxes),
        min(b.y for b in boxes),
        max(b.right for b in boxes),
        max(b.y + b.h for b in boxes),
    )
