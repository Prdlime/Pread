"""Checks for the parts of Pread that don't need a Mac. Run:  python3 tests/test_logic.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import ocr  # noqa: E402
import review  # noqa: E402

CW, H = 9.0, 18.0   # pretend character width / height in pixels


def mk(text, col, row, gutter_offset=0):
    return ocr.Box(text, gutter_offset + col * CW, row * 24.0, len(text) * CW, H)


def test_indentation_and_gutter():
    # An editor with a line-number gutter; code starts at column 6; line 4 is blank.
    code = [
        (10, 0, "def average(numbers):"),
        (11, 4, "total = 0"),
        (12, 4, "for n in numbers:"),
        (13, 8, "total += n"),
        (15, 4, "return total / len(numbers)"),
    ]
    boxes = []
    for r, (num, indent, text) in enumerate(code):
        boxes.append(ocr.Box(str(num), 5.0 + (2 - len(str(num))) * CW, r * 24.0, len(str(num)) * CW, H))
        boxes.append(mk(text, 6 + indent, r))
    lines, kept = ocr.boxes_to_lines(boxes)
    got = [(l.label, l.text) for l in lines]
    want = [(10, "def average(numbers):"), (11, "    total = 0"), (12, "    for n in numbers:"),
            (13, "        total += n"), (15, "    return total / len(numbers)")]
    assert got == want, got
    assert all(not b.text.isdigit() for b in kept)
    left, top, right, bottom = ocr.union_bbox(kept)
    assert left == 6 * CW and top == 0 and bottom == 4 * 24.0 + H


def test_no_gutter_sequential_labels():
    boxes = [mk("SELECT name, age", 0, 0), mk("FROM users", 4, 1), mk("WHERE age > 30;", 4, 2)]
    lines, _ = ocr.boxes_to_lines(boxes)
    assert [(l.label, l.text) for l in lines] == [
        (1, "SELECT name, age"), (2, "    FROM users"), (3, "    WHERE age > 30;")]


def test_split_row_is_joined():
    boxes = [mk("x = 1", 0, 0), mk("# note", 8, 0)]
    lines, _ = ocr.boxes_to_lines(boxes)
    assert len(lines) == 1 and lines[0].text.startswith("x = 1") and lines[0].text.endswith("# note")


def test_digits_in_code_are_not_a_gutter():
    boxes = [mk("5 + 3", 0, 0), mk("print(8)", 4, 1)]
    lines, _ = ocr.boxes_to_lines(boxes)
    assert lines[0].text == "5 + 3"


def test_message_and_placement():
    msg = review.build_user_message([ocr.Line(3, "x = 1"), ocr.Line(4, "")])
    assert msg == "3: x = 1\n4: "
    from PySide6.QtCore import QRect, QSize
    from ui import place_beside
    avail = QRect(0, 0, 1440, 900)
    p = place_beside(QRect(100, 200, 500, 300), QSize(400, 300), avail)
    assert (p.x(), p.y()) == (613, 200)                       # right of the code
    p = place_beside(QRect(900, 200, 500, 300), QSize(400, 300), avail)
    assert (p.x(), p.y()) == (486, 200)                       # no room on right -> left
    p = place_beside(QRect(20, 100, 1400, 300), QSize(400, 300), avail)
    assert p.y() == 413 and 0 <= p.x() <= 1040                # no room either side -> below
    p = place_beside(QRect(100, 800, 300, 80), QSize(400, 300), avail)
    assert p.y() == 595                                       # kept on screen vertically


def test_line_geometry():
    boxes = [ocr.Box("12", 5.0, 0.0, 18.0, H), mk("x = 1", 6, 0),
             ocr.Box("13", 5.0, 24.0, 18.0, H), mk("y = 2", 6, 1)]
    lines, _ = ocr.boxes_to_lines(boxes)
    assert [l.label for l in lines] == [12, 13]
    assert lines[1].top == 24.0 and lines[1].left == 6 * CW and lines[1].bottom == 24.0 + H


def test_parse_result_filters_bad_items():
    data = {"language": "Python", "suggestions": [
        {"first_line": 3, "last_line": 5, "title": "Use sum", "why": "w", "original": "a", "fixed": "b"},
        {"first_line": 99, "last_line": 99, "title": "Ghost", "why": "w", "original": "a", "fixed": "b"},
        {"first_line": "x", "last_line": 1, "title": "Bad", "why": "w", "original": "a", "fixed": "b"},
        {"first_line": 6, "last_line": 4, "title": "Swapped", "why": "w", "original": "a", "fixed": "b"},
    ]}
    res = review.parse_result(data, {3, 4, 5, 6})
    assert [(s.title, s.first, s.last) for s in res.suggestions] == [("Use sum", 3, 5), ("Swapped", 4, 6)]
    assert review.parse_result({}, {1}).suggestions == []


def _overlay():
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication
    from ui import SelectOverlay
    app = QApplication.instance() or QApplication([])
    ov = SelectOverlay(QGuiApplication.primaryScreen())
    got = {"sel": [], "cancel": 0, "anchor": 0}
    ov.selected.connect(lambda r: got["sel"].append(r))
    ov.cancelled.connect(lambda: got.__setitem__("cancel", got["cancel"] + 1))
    ov.anchored.connect(lambda: got.__setitem__("anchor", got["anchor"] + 1))
    ov.show()
    return app, ov, got


def test_overlay_click_move_click():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    app, ov, got = _overlay()
    QTest.mouseClick(ov, Qt.LeftButton, Qt.NoModifier, QPoint(100, 120))      # anchor
    assert got["anchor"] == 1 and not got["sel"]
    QTest.mouseMove(ov, QPoint(250, 200))                                      # no button held
    QTest.mouseMove(ov, QPoint(400, 300))
    assert ov._rect.width() == 301 and ov._rect.height() == 181, ov._rect
    QTest.mouseClick(ov, Qt.LeftButton, Qt.NoModifier, QPoint(400, 300))      # finish
    assert len(got["sel"]) == 1 and got["cancel"] == 0
    r = got["sel"][0]
    assert (r.width(), r.height()) == (301, 181)


def test_overlay_drag_still_works():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    app, ov, got = _overlay()
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, QPoint(50, 60))
    QTest.mouseMove(ov, QPoint(200, 160))
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, QPoint(200, 160))
    assert len(got["sel"]) == 1 and got["sel"][0].width() == 151


def test_overlay_tiny_second_click_waits_and_esc_cancels():
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    app, ov, got = _overlay()
    QTest.mouseClick(ov, Qt.LeftButton, Qt.NoModifier, QPoint(100, 100))
    QTest.mouseClick(ov, Qt.LeftButton, Qt.NoModifier, QPoint(103, 104))      # too small: ignored
    assert not got["sel"] and got["cancel"] == 0
    QTest.keyClick(ov, Qt.Key_Escape)
    assert got["cancel"] == 1


def test_macos_helpers_are_safe_elsewhere():
    import macos
    macos.make_accessory_app()
    macos.activate_app()


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
