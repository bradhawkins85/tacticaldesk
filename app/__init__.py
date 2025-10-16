"""Application package initialization hooks."""

from __future__ import annotations

from typing import Any, cast

import pydantic.typing


def _patch_forward_ref_evaluate() -> None:
    """Ensure Pydantic forward references remain compatible with Python 3.12."""

    def evaluate_forwardref(type_: Any, globalns: Any, localns: Any) -> Any:
        forward_ref = cast(Any, type_)
        try:
            return forward_ref._evaluate(globalns, localns, set())
        except TypeError:
            return forward_ref._evaluate(globalns, localns, None, recursive_guard=set())

    pydantic.typing.evaluate_forwardref = evaluate_forwardref


_patch_forward_ref_evaluate()

