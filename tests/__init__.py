"""Test suite configuration for Tactical Desk."""

from __future__ import annotations

# Importing the app package applies compatibility patches that must run before
# FastAPI (and its pydantic dependencies) are imported by the individual test
# modules. This keeps forward reference evaluation working on Python 3.12.
import app  # noqa: F401  # pylint: disable=unused-import

