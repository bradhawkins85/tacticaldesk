"""Interpreter-wide customizations for the Tactical Desk test environment."""

from __future__ import annotations

# Importing the application package applies compatibility patches that allow
# FastAPI and Pydantic v1 to run on Python 3.12 without triggering forward
# reference evaluation errors during module import.
import app  # noqa: F401  # pylint: disable=unused-import

