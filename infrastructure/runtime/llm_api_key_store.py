"""Write-only-at-HTTP runtime storage for the configured Gemini API key.

The secret is kept outside Git under ``runtime_data`` by default. HTTP routes
may replace it or query presence metadata, while the Gemini provider adapter is
the only application path that reads the value through ``read_for_runtime``.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LLM_API_KEY_PATH = PROJECT_ROOT / "runtime_data" / "secrets" / "gemini_api_key"


@dataclass(frozen=True)
class LlmApiKeyStatus:
    configured: bool
    updated_at: datetime | None


class LlmApiKeyStore:
    """Persist one replace-only Gemini API key with owner-only file permissions."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured_path = (
            path
            or os.getenv("GEMINI_API_KEY_FILE")
            or os.getenv("LLM_API_KEY_FILE")
            or DEFAULT_LLM_API_KEY_PATH
        )
        self._path = Path(configured_path)

    @property
    def path(self) -> Path:
        return self._path

    def status(self) -> LlmApiKeyStatus:
        try:
            stat_result = self._path.stat()
        except FileNotFoundError:
            return LlmApiKeyStatus(configured=False, updated_at=None)
        return LlmApiKeyStatus(
            configured=stat_result.st_size > 0,
            updated_at=datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc),
        )

    def replace(self, api_key: str) -> LlmApiKeyStatus:
        normalized = api_key.strip()
        if len(normalized) < 8 or len(normalized) > 4096:
            raise ValueError("invalid_llm_api_key")

        self._path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(self._path.parent, 0o700)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".gemini_api_key.",
            dir=str(self._path.parent),
            text=True,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(normalized)
                handle.flush()
                os.fsync(handle.fileno())
            if os.name != "nt":
                os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
            if os.name != "nt":
                os.chmod(self._path, 0o600)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

        return self.status()

    def read_for_runtime(self) -> str | None:
        """Internal provider-facing read; never expose this value through HTTP."""
        try:
            value = self._path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None
        return value or None
