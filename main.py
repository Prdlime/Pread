"""Pread: press a shortcut, drag a box around your code, get Claude's suggestions beside it."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import (QBuffer, QByteArray, QIODevice, QObject, QRect, Qt, QThread,
                            QTimer, Signal)
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication

import config
import macos
import ocr
import review
from ui import COLORS, Bar, Bubble, HighlightLayer, SelectOverlay


class HotkeyBridge(QObject):
    """Listens for the global shortcut and tells the main thread."""
    pressed = Signal()

    def start(self, combo: str) -> None:
        from pynput import keyboard
        self._listener = keyboard.GlobalHotKeys({combo: self.pressed.emit})
        self._listener.start()


class Job(QThread):
    """Reads the screenshot and asks Claude, away from the main window thread."""
    status = Signal(str)
    done = Signal(object, object)     # review.Result, list[ocr.Line]
    failed = Signal(str)

    def __init__(self, png: bytes, width: int, height: int) -> None:
        super().__init__()
        self._png, self._w, self._h = png, width, height

    def run(self) -> None:
        try:
            self.status.emit("Reading your code…")
            boxes = ocr.recognize(self._png, self._w, self._h)
            lines, _ = ocr.boxes_to_lines(boxes)
            if config.DEBUG:
                self._save_debug(lines)
            if not any(ln.text.strip() for ln in lines):
                self.failed.emit("No text found. Try selecting a bigger area.")
                return
            self.status.emit("Asking Claude…")
            result = review.ask_claude(lines)
            self.done.emit(result, lines)
        except Exception as exc:  # shown to the user in the bar
            self.failed.emit(review.friendly_error(exc))

    def _save_debug(self, lines) -> None:
        folder = Path.home() / "pread-debug"
        folder.mkdir(exist_ok=True)
        stamp = time.strftime("%H%M%S")
        (folder / f"{stamp}.png").write_bytes(self._png)
        (folder / f"{stamp}.txt").write_text(review.build_user_message(lines))


class Controller(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.bar = Bar()
        self.bubble = Bubble()
        self.marks = HighlightLayer()
        self.busy = False
        self.bar.quit_requested.connect(QApplication.quit)
        self.bubble.hovered.connect(self.marks.set_active)
        self.bubble.closed.connect(self.marks.hide)

        self.bar.place()
        self.bar.show()
        self.ready()

        if not os.getenv("ANTHROPIC_API_KEY"):
            self.bar.set_status("Add your API key to the .env file, then restart", "error")

        self.bridge = HotkeyBridge()
        self.bridge.pressed.connect(self.on_hotkey)
        try:
            self.bridge.start(config.HOTKEY)
        except Exception as exc:
            self.bar.set_status(f"Shortcut unavailable: {exc}", "error")

    # ---- steps
    def ready(self) -> None:
        pretty = config.HOTKEY.replace("<", "").replace(">", "").replace("+", " + ")
        self.bar.set_status(f"Pread ready · press {pretty}", "idle")

    def on_hotkey(self) -> None:
        if self.busy:
            return
        self.busy = True
        self.bubble.hide()
        self.marks.hide()
        self.bar.hide()                      # keep our own windows out of the screenshot
        QTimer.singleShot(150, self.grab_and_select)

    def grab_and_select(self) -> None:
        self.screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.shot = self.screen.grabWindow(0)
        self.bar.show()
        self.bar.set_status("Click one corner of your code · Esc to cancel", "busy")
        self.overlay = SelectOverlay(self.screen)
        self.overlay.anchored.connect(lambda: self.bar.set_status(
            "Move to the opposite corner, then click again · Esc to cancel", "busy"))
        self.overlay.selected.connect(self.on_selected)
        self.overlay.cancelled.connect(self.on_cancelled)
        self.overlay.begin()

    def on_cancelled(self) -> None:
        self.busy = False
        self.ready()

    def on_selected(self, rect: QRect) -> None:
        self.region = rect
        dpr = self.shot.devicePixelRatio()
        local = rect.translated(-self.screen.geometry().topLeft())
        device = QRect(round(local.x() * dpr), round(local.y() * dpr),
                       round(local.width() * dpr), round(local.height() * dpr))
        image = self.shot.copy(device).toImage()
        image.setDevicePixelRatio(1.0)

        scale = max(1.0, config.OCR_UPSCALE)
        if scale > 1.0:       # bigger text helps the reader catch small punctuation
            image = image.scaled(round(image.width() * scale), round(image.height() * scale),
                                 Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self.factor = 1.0 / (dpr * scale)      # image pixels -> screen points

        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.WriteOnly)
        image.save(buf, "PNG")
        self.job = Job(bytes(data), image.width(), image.height())
        self.job.status.connect(lambda t: self.bar.set_status(t, "busy"))
        self.job.done.connect(self.on_done)
        self.job.failed.connect(self.on_failed)
        self.bar.set_status("Reading your code…", "busy")
        self.job.start()

    def _screen_rect(self, lines: list[ocr.Line]) -> QRect:
        f, ox, oy = self.factor, self.region.x(), self.region.y()
        left = min(ln.left for ln in lines)
        top = min(ln.top for ln in lines)
        right = max(ln.right for ln in lines)
        bottom = max(ln.bottom for ln in lines)
        return QRect(round(ox + left * f), round(oy + top * f),
                     round((right - left) * f), round((bottom - top) * f))

    def on_done(self, result: review.Result, lines: list[ocr.Line]) -> None:
        code_lines = [ln for ln in lines if ln.text.strip()]
        anchor = self._screen_rect(code_lines)

        items = []
        for i, s in enumerate(result.suggestions):
            rows = [ln for ln in code_lines if s.first <= ln.label <= s.last]
            rect = self._screen_rect(rows).adjusted(-4, -2, 4, 2) if rows else None
            items.append((rect, COLORS[i % len(COLORS)]))
        self.marks.show_items(items)

        self.bubble.show_result(result, anchor, self.screen.availableGeometry(),
                                review.build_user_message(lines))
        self.busy = False
        n = len(result.suggestions)
        self.bar.set_status(f"Done · {n} suggestion{'s' if n != 1 else ''}", "ok")

    def on_failed(self, message: str) -> None:
        self.busy = False
        self.bar.set_status(message, "error")


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    macos.make_accessory_app()          # no Dock icon; allows floating over full-screen apps
    controller = Controller()  # noqa: F841  (kept alive by this variable)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
