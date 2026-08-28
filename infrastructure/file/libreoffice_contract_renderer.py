"""
File: libreoffice_contract_renderer.py
Description: 以隔離 LibreOffice headless process 將核准 XLSX 契約轉成受限制且驗證過的 PDF。
"""

from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Mapping

from subsystems.contract_signing.contract_renderer import (
    ContractRendererError,
    RenderedContract,
    render_contract_template,
)


_DEFAULT_TIMEOUT_SECONDS = 30
_DEFAULT_MAX_PDF_BYTES = 20 * 1024 * 1024
_EXECUTABLE_ENVIRONMENT_KEY = "CONTRACT_PDF_RENDERER_EXECUTABLE"
_RENDERER_IDENTITY = "libreoffice-headless-calc-pdf-v1"
_PASSTHROUGH_ENVIRONMENT_KEYS = (
    "PATH",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "SYSTEMROOT",
    "WINDIR",
)


class LibreOfficeContractRenderer:
    """Portable adapter around a configured or PATH-discovered soffice executable."""

    def __init__(
        self,
        *,
        executable: str | None = None,
        timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
        max_pdf_bytes: int = _DEFAULT_MAX_PDF_BYTES,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
        executable_locator: Callable[[str], str | None] = shutil.which,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if max_pdf_bytes <= 0:
            raise ValueError("max_pdf_bytes must be positive")
        self._configured_executable = executable
        self._timeout_seconds = timeout_seconds
        self._max_pdf_bytes = max_pdf_bytes
        self._runner = runner
        self._executable_locator = executable_locator

    def render(
        self,
        *,
        template_path: Path,
        mapping_path: Path,
        facts: Mapping[str, object],
    ) -> RenderedContract:
        executable = self._resolve_executable()
        try:
            workbook_content = render_contract_template(
                template_path=template_path,
                mapping_path=mapping_path,
                facts=facts,
            )
        except Exception:
            raise ContractRendererError(
                "contract_pdf_renderer_source_invalid",
                "契約 PDF renderer 的核准來源無法讀取。",
            ) from None
        try:
            with tempfile.TemporaryDirectory(prefix="contract-pdf-render-") as directory:
                workspace = Path(directory)
                profile_directory = workspace / "profile"
                output_directory = workspace / "output"
                profile_directory.mkdir()
                output_directory.mkdir()
                source_path = workspace / "contract-source.xlsx"
                source_path.write_bytes(workbook_content)
                command = self._command(
                    executable=executable,
                    profile_directory=profile_directory,
                    output_directory=output_directory,
                    source_path=source_path,
                )
                completed = self._runner(
                    command,
                    cwd=str(workspace),
                    env=_renderer_environment(workspace),
                    timeout=self._timeout_seconds,
                    capture_output=True,
                    check=False,
                )
                if completed.returncode != 0:
                    raise ContractRendererError(
                        "contract_pdf_renderer_conversion_failed",
                        "契約 PDF renderer 轉換失敗。",
                    )
                content = self._read_single_pdf(output_directory)
        except ContractRendererError:
            raise
        except subprocess.TimeoutExpired:
            raise ContractRendererError(
                "contract_pdf_renderer_timeout",
                "契約 PDF renderer 執行逾時。",
                retryable=True,
            ) from None
        except OSError:
            raise ContractRendererError(
                "contract_pdf_renderer_unavailable",
                "契約 PDF renderer 無法啟動。",
                retryable=True,
            ) from None
        return RenderedContract.from_pdf_bytes(
            content=content,
            filename=f"{Path(template_path).stem}.pdf",
            renderer_identity=_RENDERER_IDENTITY,
        )

    def _resolve_executable(self) -> str:
        configured = self._configured_executable
        if configured is None:
            configured = os.getenv(_EXECUTABLE_ENVIRONMENT_KEY, "").strip() or None
        if configured is not None:
            resolved = _locate_configured_executable(
                configured,
                locator=self._executable_locator,
            )
            if resolved is None:
                raise ContractRendererError(
                    "contract_pdf_renderer_unavailable",
                    "契約 PDF renderer 尚未配置。",
                    retryable=True,
                )
            return resolved
        for command in ("soffice", "libreoffice"):
            resolved = self._executable_locator(command)
            if resolved and _is_executable_file(Path(resolved)):
                return resolved
        raise ContractRendererError(
            "contract_pdf_renderer_unavailable",
            "契約 PDF renderer 尚未配置。",
            retryable=True,
        )

    @staticmethod
    def _command(
        *,
        executable: str,
        profile_directory: Path,
        output_directory: Path,
        source_path: Path,
    ) -> list[str]:
        return [
            executable,
            "--headless",
            "--nologo",
            "--nodefault",
            "--nolockcheck",
            "--nofirststartwizard",
            f"-env:UserInstallation={profile_directory.as_uri()}",
            "--convert-to",
            "pdf:calc_pdf_Export",
            "--outdir",
            str(output_directory),
            str(source_path),
        ]

    def _read_single_pdf(self, output_directory: Path) -> bytes:
        candidates = [
            path
            for path in output_directory.glob("*.pdf")
            if path.is_file() and not path.is_symlink()
        ]
        if len(candidates) != 1:
            code = (
                "contract_pdf_renderer_output_empty"
                if not candidates
                else "contract_pdf_renderer_output_ambiguous"
            )
            raise ContractRendererError(code, "契約 PDF renderer 輸出數量不正確。")
        candidate = candidates[0]
        size = candidate.stat().st_size
        if size <= 0:
            raise ContractRendererError(
                "contract_pdf_renderer_output_empty",
                "契約 PDF renderer 未產生內容。",
            )
        if size > self._max_pdf_bytes:
            raise ContractRendererError(
                "contract_pdf_renderer_output_too_large",
                "契約 PDF renderer 輸出超過大小限制。",
            )
        content = candidate.read_bytes()
        if len(content) != size:
            raise ContractRendererError(
                "contract_pdf_renderer_output_changed",
                "契約 PDF renderer 輸出在讀取期間變更。",
            )
        return content


def _locate_configured_executable(
    configured: str,
    *,
    locator: Callable[[str], str | None],
) -> str | None:
    requested = configured.strip()
    if not requested:
        return None
    has_path_separator = any(separator and separator in requested for separator in (os.sep, os.altsep))
    if has_path_separator or Path(requested).is_absolute():
        return requested if _is_executable_file(Path(requested)) else None
    resolved = locator(requested)
    return resolved if resolved and _is_executable_file(Path(resolved)) else None


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _renderer_environment(workspace: Path) -> dict[str, str]:
    environment = {
        key: value
        for key in _PASSTHROUGH_ENVIRONMENT_KEYS
        if (value := os.environ.get(key)) is not None
    }
    environment["HOME"] = str(workspace)
    return environment
