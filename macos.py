"""macOS-only window tweaks so Pread stays in front of every other app.

By default Qt "tool" windows hide whenever you switch to another app, and they
sit below full-screen apps. These helpers fix both. On other systems (or if
anything goes wrong) they quietly do nothing.
"""
from __future__ import annotations

import sys

STATUS_LEVEL = 25    # above normal windows and floating panels
POPUP_LEVEL = 101    # above the menu bar (used for the selection overlay)

# CanJoinAllSpaces | FullScreenAuxiliary: show on every desktop, and over full-screen apps
_BEHAVIOR = (1 << 0) | (1 << 8)
_warned = False


def _warn(exc: Exception) -> None:
    global _warned
    if not _warned:
        _warned = True
        print(f"[pread] could not keep windows in front: {exc}", file=sys.stderr)


def make_accessory_app() -> None:
    """Run as a background-style app: no Dock icon, and windows may float over full-screen apps."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except Exception as exc:
        _warn(exc)


def float_above_all(widget, level: int = STATUS_LEVEL) -> None:
    """Keep this window on top of everything, on every desktop, even when Pread isn't the active app."""
    if sys.platform != "darwin":
        return
    try:
        import objc
        view = objc.objc_object(c_void_p=int(widget.winId()))
        window = view.window()
        if window is None:
            return
        window.setLevel_(level)
        window.setHidesOnDeactivate_(False)     # the big one: don't vanish when you click another app
        window.setCollectionBehavior_(_BEHAVIOR)
    except Exception as exc:
        _warn(exc)


def activate_app() -> None:
    """Bring Pread forward so the selection overlay can receive the Esc key."""
    if sys.platform != "darwin":
        return
    try:
        from AppKit import NSApplication
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception as exc:
        _warn(exc)
