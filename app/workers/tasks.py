from __future__ import annotations

import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class TaskSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    progress = Signal(int, int, str)
    finished = Signal()


class FunctionTask(QRunnable):
    def __init__(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = TaskSignals()
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(
                *self.args,
                progress=lambda current, total, message="": self.signals.progress.emit(current, total, message),
                cancelled=lambda: self.cancelled,
                **self.kwargs,
            )
            self.signals.result.emit(result)
        except Exception as error:
            self.signals.error.emit(f"{error}\n\n{traceback.format_exc(limit=3)}")
        finally:
            self.signals.finished.emit()

