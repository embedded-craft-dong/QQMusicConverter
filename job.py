"""Cancellation and progress shared by the CLI, GUI and optional login adapter."""
from dataclasses import dataclass, field
import threading


class Cancelled(Exception):
    """A user cancellation, not a conversion failure."""


@dataclass
class SessionCache:
    # A batch owns this object. Never serialize it or include it in diagnostics.
    tokens: set = field(default_factory=set, repr=False)
    scanned: bool = False

    def clear(self):
        self.tokens.clear()
        self.scanned = False


def checkpoint(args=None):
    event = getattr(args, 'cancel_event', None)
    if event is not None and event.is_set():
        raise Cancelled()


def report(args, phase, fraction):
    checkpoint(args)
    callback = getattr(args, 'progress', None)
    if callback:
        callback(phase, max(0.0, min(1.0, fraction)))
