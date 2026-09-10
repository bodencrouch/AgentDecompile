"""Small, dependency-free Python consumer for the gnsdk C ABI."""

from .errors import GnsdkError, Status
from .session import Session, Version, capabilities

__all__ = ["GnSdkError", "GnsdkError", "Session", "Status", "Version", "capabilities"]

# Compatibility with the spelling used in early design notes.
GnSdkError = GnsdkError
