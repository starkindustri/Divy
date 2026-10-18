"""Run blocking network calls off the UI thread and deliver results back on it."""
from PySide6.QtCore import QObject, QThreadPool, Signal, Slot

_dispatcher = None


class _Dispatcher(QObject):
    # Lives on the UI thread; emitting from a worker thread queues the call.
    deliver = Signal(object, object)

    def __init__(self):
        super().__init__()
        self.deliver.connect(self._call)

    @Slot(object, object)
    def _call(self, callback, value):
        callback(value)


def run_async(fn, on_done, on_error=None) -> None:
    """Call `fn()` on a worker thread, then `on_done(result)` or `on_error(exc)` on the UI thread."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = _Dispatcher()
    dispatcher = _dispatcher

    def job():
        try:
            result = fn()
        except Exception as exc:
            if on_error is not None:
                dispatcher.deliver.emit(on_error, exc)
            return
        dispatcher.deliver.emit(on_done, result)

    QThreadPool.globalInstance().start(job)
