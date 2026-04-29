"""Item detectors for ``context-kit refactor track``.

A detector is a callable ``(ast.Module) -> list[str]`` that returns the
names of module-level items that count as migratable. v1 ships three:

- ``function``    — every module-level FunctionDef / AsyncFunctionDef
- ``class``       — every module-level ClassDef
- ``celery-task`` — every FunctionDef / AsyncFunctionDef decorated with
                    ``@shared_task`` or ``@app.task`` (with or without
                    parentheses / args)

The registry is a plain dict so callers can ``raise`` on unknown
detector names with a helpful suggestion list.
"""

from __future__ import annotations

import ast
from typing import Callable

# Public type alias — a detector takes a parsed module and returns
# the *names* of the items it identifies. Names are returned (rather
# than nodes) because callers care about identity across files.
Detector = Callable[[ast.Module], list[str]]


def detect_functions(module: ast.Module) -> list[str]:
    """Every module-level function definition (sync or async)."""
    return [
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def detect_classes(module: ast.Module) -> list[str]:
    """Every module-level class definition."""
    return [
        node.name
        for node in module.body
        if isinstance(node, ast.ClassDef)
    ]


def _is_celery_decorator(deco: ast.expr) -> bool:
    """Return True if ``deco`` is ``@shared_task`` or ``@app.task``.

    Handles all four common forms:
        @shared_task
        @shared_task()
        @shared_task(name=...)
        @app.task / @celery.task / @anything.task
    """
    if isinstance(deco, ast.Name):
        # @shared_task
        return deco.id == "shared_task"
    if isinstance(deco, ast.Attribute):
        # @app.task / @celery.task etc.
        return deco.attr == "task"
    if isinstance(deco, ast.Call):
        # @shared_task(...) / @app.task(...) — recurse on the callable
        return _is_celery_decorator(deco.func)
    return False


def detect_celery_tasks(module: ast.Module) -> list[str]:
    """Functions decorated with ``@shared_task`` or ``@x.task``."""
    out: list[str] = []
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(_is_celery_decorator(d) for d in node.decorator_list):
            out.append(node.name)
    return out


DETECTORS: dict[str, Detector] = {
    "function": detect_functions,
    "class": detect_classes,
    "celery-task": detect_celery_tasks,
}


def get_detector(name: str) -> Detector:
    """Return the detector callable for ``name`` or raise ``ValueError``."""
    if name not in DETECTORS:
        known = ", ".join(sorted(DETECTORS))
        raise ValueError(
            f"unknown detector {name!r} — known detectors: {known}"
        )
    return DETECTORS[name]
