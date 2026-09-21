"""Generated from native/conformance/status_codes.json; do not hand-renumber."""

from enum import IntEnum


class Status(IntEnum):
    OK = 0
    OK_WARNINGS = 1
    PARTIAL_UNSUPPORTED = 2
    CANCELLED = 10
    TIMEOUT = 11
    RESOURCE_LIMITED = 12
    BUSY = 13
    STALE = 14
    PROVIDER_FAILURE = 20
    ENGINE_FAILURE = 21
    INVALID_ARGUMENT = 30
    NOT_INITIALIZED = 31


class GnsdkError(RuntimeError):
    """A non-success status returned by the native ABI."""

    def __init__(self, status: int, operation: str):
        self.status = int(status)
        self.operation = operation
        try:
            name = Status(self.status).name
        except ValueError:
            name = "UNKNOWN_STATUS"
        super().__init__(f"{operation}: {name} ({self.status})")
