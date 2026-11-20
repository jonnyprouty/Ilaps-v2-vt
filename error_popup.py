"""Show Ilaps errors in a pop-up instead of only in the error log / log.txt.

Three sources feed one notifier:
- unexpected exceptions in button handlers (sys.excepthook; the traceback still goes to the error log);
- ERROR messages logged by imgMS (logging handler on the "main" logger);
- messages Ilaps reports itself (notify()).

Messages are collected and shown together, once, after the current action finishes, so one failing
button gives one dialog, and the same message from two sources is shown only once.
"""
import logging
import sys
import traceback

from PySide2.QtCore import QTimer
from PySide2.QtWidgets import QApplication, QMessageBox

_pending = []
_scheduled = False
_parent = None


def notify(message):
    """Queue a message for the pop-up (shown after the current action finishes)."""
    global _scheduled
    message = str(message).strip()
    if not message or message in _pending:
        return
    _pending.append(message)
    if not _scheduled and QApplication.instance() is not None:
        _scheduled = True
        QTimer.singleShot(0, _flush)


def _flush():
    global _scheduled
    _scheduled = False
    if not _pending:
        return
    messages = list(_pending)
    _pending.clear()
    box = QMessageBox(_parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Ilaps: problem")
    box.setText("\n\n".join(messages))
    box.setInformativeText("Details: Show error log (Ctrl+E) and log.txt in the Ilaps folder.")
    box.exec_()


class PopupHandler(logging.Handler):
    """Sends ERROR (and worse) log records to the pop-up and to the error log page."""

    def __init__(self):
        super().__init__(level=logging.ERROR)

    def emit(self, record):
        msg = record.getMessage()
        sys.stderr.write(f"ERROR: {msg}\n")
        notify(msg)


HINT_MISSING = ("A step was probably skipped: import data first, then on Bulk analysis run Average, then "
                "Quantification, before the corrections, Report or Export.")


def _excepthook(exc_type, exc, tb):
    traceback.print_exception(exc_type, exc, tb)  # to the error log page (stderr)
    msg = f"{exc_type.__name__}: {exc}" if str(exc) else exc_type.__name__
    if "NoneType" in str(exc):
        msg = HINT_MISSING + "\n(" + msg + ")"
    notify(msg)


def install(parent=None):
    """Call once after the main window exists."""
    global _parent
    _parent = parent
    sys.excepthook = _excepthook


def attach(logger):
    """Add the pop-up handler to a logger (safe to call on every import)."""
    if logger is not None and not any(isinstance(h, PopupHandler) for h in logger.handlers):
        logger.addHandler(PopupHandler())
