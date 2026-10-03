"""Cooperative cancellation and plain-data events for a conversion job."""

from threading import Event


class ConversionCancelled(Exception):
    """The user cancelled the job; completed text may have been saved."""


class JobControl:
    def __init__(self, on_event=None):
        self.cancelled = Event()
        self.on_event = on_event

    def check(self):
        if self.cancelled.is_set():
            raise ConversionCancelled()

    def emit(self, **event):
        if self.on_event is not None:
            self.on_event(event)
