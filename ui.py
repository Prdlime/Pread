"""The windows: status bar, drag-to-select overlay, on-screen highlights and the suggestions box."""
from __future__ import annotations

from html import escape

from PySide6.QtCore import QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QScrollArea, QVBoxLayout, QWidget)

import macos
import review

PANEL = QColor(24, 24, 28, 242)
EDGE = QColor(255, 255, 255, 36)
TONES = {
    "idle": QColor(120, 200, 150),
    "busy": QColor(240, 180, 70),
    "ok": QColor(110, 210, 130),
    "error": QColor(235, 100, 90),
}
# One colour per suggestion. Used for the highlight on screen and the card badge.
COLORS = [QColor("#f0b446"), QColor("#6cb6ff"), QColor("#7ee787"),
          QColor("#d2a8ff"), QColor("#ff9bce"), QColor("#79e0d6")]
_FLAGS = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
MONO = "font-family: Menlo, Monaco, 'Courier New', monospace; font-size: 12px;"


def place_beside(anchor: QRect, size: QSize, avail: QRect, gap: int = 14) -> QPoint:
    """Pick a spot for a box of `size` next to `anchor`, kept inside `avail`."""
    w, h = size.width(), size.height()
    y = min(max(anchor.top(), avail.top() + 4), avail.bottom() - h - 4)
    x = anchor.right() + gap
    if x + w <= avail.right() - 4:                    # room on the right
        return QPoint(x, y)
    x = anchor.left() - gap - w
    if x >= avail.left() + 4:                         # room on the left
        return QPoint(x, y)
    x = min(max(anchor.left(), avail.left() + 4), avail.right() - w - 4)   # below
    y = min(anchor.bottom() + gap, avail.bottom() - h - 4)
    return QPoint(x, y)


def _close_button() -> QPushButton:
    b = QPushButton("×")
    b.setFixedSize(24, 24)
    b.setCursor(Qt.PointingHandCursor)
    b.setStyleSheet(
        "QPushButton{color:#9a9a9f;background:transparent;border:none;font-size:18px;}"
        "QPushButton:hover{color:#ffffff;}")
    return b


class _Floating(QWidget):
    """A window that stays in front of every other app (macOS)."""
    LEVEL = macos.STATUS_LEVEL

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # wait one beat so the native window exists
        QTimer.singleShot(0, lambda: macos.float_above_all(self, self.LEVEL))


class Bar(_Floating):
    """Small dark status bar at the top-centre of the screen."""
    quit_requested = Signal()

    def __init__(self) -> None:
        super().__init__(None, _FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._tone = "idle"

        self.label = QLabel()
        self.label.setStyleSheet("color: #e8e6e3; background: transparent;")
        f = QFont(); f.setPointSize(13)
        self.label.setFont(f)

        close = _close_button()
        close.setToolTip("Quit Pread")
        close.clicked.connect(self.quit_requested)

        row = QHBoxLayout(self)
        row.setContentsMargins(40, 6, 12, 6)
        row.addWidget(self.label, 1)
        row.addWidget(close)
        self.setFixedSize(460, 44)

    def set_status(self, text: str, tone: str = "idle") -> None:
        self._tone = tone
        # long messages are shortened with "..." here; the full text is in the tooltip
        room = self.width() - 40 - 12 - 24 - 12
        self.label.setText(self.label.fontMetrics().elidedText(text, Qt.ElideRight, room))
        self.label.setToolTip(text)
        self.setToolTip(text)
        self.update()

    def place(self) -> None:
        screen = QGuiApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2, screen.top() + 10)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.setPen(QPen(EDGE, 1))
        p.setBrush(PANEL)
        p.drawRoundedRect(r, 14, 14)
        p.setPen(Qt.NoPen)
        p.setBrush(TONES.get(self._tone, TONES["idle"]))
        p.drawEllipse(QPoint(22, self.height() // 2), 5, 5)


class SelectOverlay(_Floating):
    """Dims one screen so you can mark your code.

    Click once to anchor a corner, move the mouse, then click again to finish.
    (Press, drag and release also works.)
    """
    LEVEL = macos.POPUP_LEVEL
    selected = Signal(QRect)   # in global screen coordinates
    cancelled = Signal()
    anchored = Signal()        # the first click happened

    def __init__(self, screen) -> None:
        super().__init__(None, _FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self._origin: QPoint | None = None
        self._rect = QRect()
        self._held = False

    def begin(self) -> None:
        self.show()
        self.raise_()
        macos.activate_app()
        self.activateWindow()
        self.setFocus()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 70))
        if self._rect.isNull():
            return
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self._rect, QColor(0, 0, 0, 1))
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        p.setPen(QPen(QColor(120, 190, 255), 2))
        p.drawRect(self._rect)
        label = f"{self._rect.width()} \u00d7 {self._rect.height()}"
        tag = QRect(self._rect.left(), self._rect.bottom() + 6, 84, 20)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(24, 24, 28, 220))
        p.drawRoundedRect(tag, 6, 6)
        p.setPen(QColor("#e8e6e3"))
        p.drawText(tag, Qt.AlignCenter, label)

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            self._finish(False)
            return
        pos = e.position().toPoint()
        if self._origin is None:                 # first click: drop the anchor
            self._origin = pos
            self._rect = QRect(pos, QSize())
            self._held = True
            self.anchored.emit()
            self.update()
        else:                                    # second click: finish
            self._complete(pos)

    def mouseMoveEvent(self, e) -> None:
        if self._origin is not None:
            self._rect = QRect(self._origin, e.position().toPoint()).normalized()
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if not self._held:
            return
        self._held = False
        pos = e.position().toPoint()
        if (pos - self._origin).manhattanLength() >= 10:   # press-drag-release style
            self._complete(pos)

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Escape:
            self._finish(False)

    def _complete(self, pos: QPoint) -> None:
        rect = QRect(self._origin, pos).normalized()
        if rect.width() < 12 or rect.height() < 12:
            return                                # too small: keep waiting for a proper second click
        global_rect = QRect(self.mapToGlobal(rect.topLeft()), rect.size())
        self._finish(True)
        self.selected.emit(global_rect)

    def _finish(self, ok: bool) -> None:
        self.hide()
        self.deleteLater()
        if not ok:
            self.cancelled.emit()


class HighlightLayer(_Floating):
    """Coloured marks drawn over your real code, one per suggestion. Clicks pass through."""
    PAD = 26

    def __init__(self) -> None:
        super().__init__(None, _FLAGS | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._items: list[tuple[QRect | None, QColor]] = []
        self._active = -1
        self._origin = QPoint()

    def show_items(self, items: list[tuple[QRect | None, QColor]]) -> None:
        rects = [r for r, _ in items if r is not None]
        if not rects:
            self.hide()
            return
        self._items, self._active = items, -1
        union = rects[0]
        for r in rects[1:]:
            union = union.united(r)
        union = union.adjusted(-self.PAD, -4, 4, 4)
        self._origin = union.topLeft()
        self.setGeometry(union)
        self.show()
        self.raise_()

    def set_active(self, index: int) -> None:
        self._active = index
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        for i, (rect, color) in enumerate(self._items):
            if rect is None:
                continue
            r = rect.translated(-self._origin)
            active = i == self._active
            fill = QColor(color)
            fill.setAlpha(80 if active else (20 if self._active >= 0 else 42))
            p.setPen(QPen(color, 3 if active else 2))
            p.setBrush(fill)
            p.drawRoundedRect(r, 4, 4)
            # numbered badge on the left edge
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            c = QPoint(r.left() - 13, r.top() + min(12, r.height() // 2))
            p.drawEllipse(c, 10, 10)
            p.setPen(QColor("#111111"))
            f = p.font(); f.setBold(True); f.setPointSize(11)
            p.setFont(f)
            p.drawText(QRect(c.x() - 10, c.y() - 10, 20, 20), Qt.AlignCenter, str(i + 1))


class Card(QFrame):
    """One suggestion: reason, original code, fixed code."""
    hovered = Signal(int)

    def __init__(self, index: int, s: review.Suggestion) -> None:
        super().__init__()
        self.index = index
        color = COLORS[index % len(COLORS)]
        self.setObjectName("card")
        self.setStyleSheet("#card{background:rgba(255,255,255,0.05);border-radius:10px;}")

        badge = QLabel(str(index + 1))
        badge.setFixedSize(22, 22)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(f"background:{color.name()};color:#111;border-radius:11px;"
                            "font-weight:700;font-size:12px;")
        rng = f"L{s.first}" if s.first == s.last else f"L{s.first}–{s.last}"
        title = QLabel(f"<b>{escape(s.title.replace(chr(96), ''))}</b> &nbsp;<span style='color:#9a9a9f'>{rng}</span>")
        title.setTextFormat(Qt.RichText)
        title.setWordWrap(True)
        title.setStyleSheet("background:transparent;color:#f1efec;font-size:13px;")

        head = QHBoxLayout()
        head.setSpacing(8)
        head.addWidget(badge, 0, Qt.AlignTop)
        head.addWidget(title, 1)

        why = QLabel(s.why.replace("`", ""))
        why.setWordWrap(True)
        why.setStyleSheet("background:transparent;color:#d6d4d0;font-size:12.5px;")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 9, 10, 10)
        lay.setSpacing(7)
        lay.addLayout(head)
        lay.addWidget(why)
        lay.addWidget(self._code("ORIGINAL", s.original, "#ff9b93", "rgba(235,100,90,0.16)"))
        lay.addWidget(self._code("FIX", s.fixed, "#8fe0a6", "rgba(80,200,120,0.16)"))

    @staticmethod
    def _code(caption: str, code: str, fg: str, bg: str) -> QFrame:
        box = QFrame()
        box.setObjectName("code")
        box.setStyleSheet(f"#code{{background:{bg};border-radius:7px;}}")
        cap = QLabel(caption)
        cap.setStyleSheet(f"background:transparent;color:{fg};font-size:10px;font-weight:700;"
                          "letter-spacing:1px;")
        body = QLabel(code or "(nothing)")
        body.setTextFormat(Qt.PlainText)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextSelectableByMouse)   # so you can copy the fix
        body.setStyleSheet(f"background:transparent;color:#ecebe8;{MONO}")
        v = QVBoxLayout(box)
        v.setContentsMargins(9, 6, 9, 8)
        v.setSpacing(3)
        v.addWidget(cap)
        v.addWidget(body)
        return box

    def enterEvent(self, _event) -> None:
        self.hovered.emit(self.index)

    def leaveEvent(self, _event) -> None:
        self.hovered.emit(-1)


class Bubble(_Floating):
    """The suggestions box. Drag its top strip to move it."""
    WIDTH = 440
    INNER = WIDTH - 14 - 12 - 12      # card column width (margins + scrollbar)
    hovered = Signal(int)
    closed = Signal()

    def __init__(self) -> None:
        super().__init__(None, _FLAGS)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.title = QLabel("Pread")
        self.title.setStyleSheet("color:#b4b4b9; background:transparent; font-weight:600;")
        close = _close_button()
        close.clicked.connect(self._on_close)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea{background:transparent;}"
            "QScrollBar:vertical{width:8px;background:transparent;}"
            "QScrollBar::handle:vertical{background:#55555a;border-radius:4px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        self.scroll.viewport().setStyleSheet("background:transparent;")

        self.toggle = QPushButton("Show what Pread read")
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.setStyleSheet(
            "QPushButton{color:#8c8f98;background:transparent;border:none;text-align:left;font-size:11.5px;}"
            "QPushButton:hover{color:#ffffff;}")
        self.toggle.clicked.connect(self._toggle_text)
        self.sent = QPlainTextEdit()
        self.sent.setReadOnly(True)
        self.sent.setFixedHeight(140)
        self.sent.setVisible(False)
        self.sent.setStyleSheet(f"QPlainTextEdit{{background:rgba(255,255,255,0.06);color:#d6d4d0;"
                                f"border:none;border-radius:7px;{MONO}}}")

        head = QHBoxLayout()
        head.addWidget(self.title, 1)
        head.addWidget(close)
        col = QVBoxLayout(self)
        col.setContentsMargins(14, 8, 12, 10)
        col.setSpacing(4)
        col.addLayout(head)
        col.addWidget(self.scroll, 1)
        col.addWidget(self.toggle)
        col.addWidget(self.sent)
        self._drag_strip = 44

    # ---- content
    def show_result(self, result: review.Result, anchor: QRect, avail: QRect, text_sent: str) -> None:
        body = QWidget()
        body.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        if result.suggestions:
            for i, s in enumerate(result.suggestions):
                card = Card(i, s)
                card.hovered.connect(self.hovered)
                lay.addWidget(card)
        else:
            ok = QLabel("No suggestions. This code looks good. ✓")
            ok.setStyleSheet("color:#d6d4d0; background:transparent; padding:8px 2px;")
            lay.addWidget(ok)

        body.setFixedWidth(self.INNER)
        content_h = lay.totalHeightForWidth(self.INNER)
        body.setFixedHeight(content_h)
        self.scroll.setWidget(body)

        lang = f" · {result.language}" if result.language and result.language != "Unknown" else ""
        n = len(result.suggestions)
        self.title.setText(f"Pread{lang} · {n} suggestion{'s' if n != 1 else ''}")
        self.sent.setPlainText(text_sent)
        self.sent.setVisible(False)
        self.toggle.setText("Show what Pread read")

        chrome = 8 + 30 + 4 + 28 + 10          # header, spacing, toggle, margins
        height = max(150, min(content_h + chrome, min(640, avail.height() - 20)))
        self.setFixedSize(self.WIDTH, height)
        self.move(place_beside(anchor, self.size(), avail))
        self.show()
        self.raise_()

    def _toggle_text(self) -> None:
        show = not self.sent.isVisible()
        self.sent.setVisible(show)
        self.toggle.setText("Hide what Pread read" if show else "Show what Pread read")
        screen = QGuiApplication.screenAt(self.pos()) or QGuiApplication.primaryScreen()
        extra = 148 if show else -148
        h = max(150, min(self.height() + extra, screen.availableGeometry().height() - 20))
        self.setFixedSize(self.WIDTH, h)

    def _on_close(self) -> None:
        self.hide()
        self.closed.emit()

    # ---- dragging
    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton and e.position().y() < self._drag_strip:
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemMove()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(EDGE, 1))
        p.setBrush(PANEL)
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)
