"""Cross-version filesystem compatibility helpers for supported Python runtimes."""

from __future__ import annotations

from pathlib import Path


def is_link_like_directory(path: Path) -> bool:
    """Return whether *path* is a symlink or Windows junction.

    ``Path.is_junction`` was added after Python 3.11, while this repository
    still supports Python 3.11. Treat the capability as optional so callers
    keep the same security posture without requiring a newer interpreter.
    """

    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction()) if callable(is_junction) else False


__all__ = ["is_link_like_directory"]
