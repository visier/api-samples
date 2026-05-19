"""
Custom errors for the SDLC workflow.

Raising a dedicated exception type lets calling code catch failures without
treating them like generic Python errors, and the ``step`` field is used
to build clear messages such as "Step 3 failed: ...".
"""

from __future__ import annotations


class VisierSDLCError(Exception):
    """Raised when a Visier SDLC step fails or the API returns an error response."""

    def __init__(self, message: str, *, step: int | None = None) -> None:
        self.step = step
        if step is not None:
            super().__init__(f"Step {step} failed: {message}")
        else:
            super().__init__(message)
