"""
File: test_libreoffice_contract_renderer.py
Description: 驗證 LibreOffice PDF adapter 的隔離、限制、去敏錯誤與 portable executable discovery。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest
from openpyxl import Workbook

from infrastructure.file.libreoffice_contract_renderer import (
    LibreOfficeContractRenderer,
)
from subsystems.contract_signing.contract_renderer import ContractRendererError


def _source_files(tmp_path: Path) -> tuple[Path, Path]:
    template = tmp_path / "approved-template.xlsx"
    workbook = Workbook()
    workbook.active["A1"] = "template"
    workbook.save(template)
    mapping = tmp_path / "approved-template.json"
    mapping.write_text(
        json.dumps({"param_mappings": {"A2": {"db_key": "case_no"}}}),
        encoding="utf-8",
    )
    return template, mapping


def _executable(tmp_path: Path) -> Path:
    executable = tmp_path / "portable-soffice"
    executable.write_text("executable marker", encoding="utf-8")
    executable.chmod(0o700)
    return executable


def _successful_runner(observed: dict[str, object]):
    def run(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        output_directory = Path(command[command.index("--outdir") + 1])
        (output_directory / "contract-source.pdf").write_bytes(
            b"%PDF-1.7\nrendered\n%%EOF\n"
        )
        return subprocess.CompletedProcess(command, 0, stdout=b"converted", stderr=b"")

    return run


def test_adapter_uses_isolated_profile_fixed_flags_and_sanitized_environment(
    tmp_path, monkeypatch
):
    template, mapping = _source_files(tmp_path)
    executable = _executable(tmp_path)
    observed: dict[str, object] = {}
    monkeypatch.setenv("DB_PASSWORD", "must-not-reach-renderer")
    renderer = LibreOfficeContractRenderer(
        executable=str(executable),
        timeout_seconds=17,
        runner=_successful_runner(observed),
    )

    result = renderer.render(
        template_path=template,
        mapping_path=mapping,
        facts={"case_no": "CASE-1"},
    )

    command = observed["command"]
    kwargs = observed["kwargs"]
    assert command[0] == str(executable)
    assert command[1:6] == [
        "--headless",
        "--nologo",
        "--nodefault",
        "--nolockcheck",
        "--nofirststartwizard",
    ]
    assert any(part.startswith("-env:UserInstallation=file:") for part in command)
    assert command[command.index("--convert-to") + 1] == "pdf:calc_pdf_Export"
    assert kwargs["timeout"] == 17
    assert kwargs["capture_output"] is True
    assert kwargs["check"] is False
    assert "DB_PASSWORD" not in kwargs["env"]
    assert result.content.startswith(b"%PDF-")
    assert result.content.rstrip().endswith(b"%%EOF")
    assert result.filename == "approved-template.pdf"


def test_adapter_discovers_soffice_from_path_without_personal_fallback(tmp_path):
    template, mapping = _source_files(tmp_path)
    executable = _executable(tmp_path)
    observed: dict[str, object] = {}

    def locate(name: str):
        return str(executable) if name == "soffice" else None

    renderer = LibreOfficeContractRenderer(
        runner=_successful_runner(observed),
        executable_locator=locate,
    )
    renderer.render(template_path=template, mapping_path=mapping, facts={})

    assert observed["command"][0] == str(executable)


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"not-pdf\n%%EOF", "contract_pdf_renderer_output_invalid"),
        (b"%PDF-1.7\nmissing-eof", "contract_pdf_renderer_output_invalid"),
        (b"", "contract_pdf_renderer_output_empty"),
    ],
)
def test_adapter_rejects_empty_or_corrupt_pdf_output(tmp_path, payload, code):
    template, mapping = _source_files(tmp_path)
    executable = _executable(tmp_path)

    def run(command, **_kwargs):
        output_directory = Path(command[command.index("--outdir") + 1])
        (output_directory / "contract-source.pdf").write_bytes(payload)
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    renderer = LibreOfficeContractRenderer(executable=str(executable), runner=run)

    with pytest.raises(ContractRendererError) as captured:
        renderer.render(template_path=template, mapping_path=mapping, facts={})

    assert captured.value.code == code


def test_adapter_rejects_multiple_or_oversized_pdf_outputs(tmp_path):
    template, mapping = _source_files(tmp_path)
    executable = _executable(tmp_path)

    def multiple(command, **_kwargs):
        output_directory = Path(command[command.index("--outdir") + 1])
        for name in ("one.pdf", "two.pdf"):
            (output_directory / name).write_bytes(b"%PDF-1.7\n%%EOF")
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    renderer = LibreOfficeContractRenderer(executable=str(executable), runner=multiple)
    with pytest.raises(ContractRendererError) as captured:
        renderer.render(template_path=template, mapping_path=mapping, facts={})
    assert captured.value.code == "contract_pdf_renderer_output_ambiguous"

    def oversized(command, **_kwargs):
        output_directory = Path(command[command.index("--outdir") + 1])
        (output_directory / "contract-source.pdf").write_bytes(
            b"%PDF-1.7\n" + b"x" * 32 + b"\n%%EOF"
        )
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    renderer = LibreOfficeContractRenderer(
        executable=str(executable), runner=oversized, max_pdf_bytes=24
    )
    with pytest.raises(ContractRendererError) as captured:
        renderer.render(template_path=template, mapping_path=mapping, facts={})
    assert captured.value.code == "contract_pdf_renderer_output_too_large"


def test_adapter_maps_timeout_and_conversion_error_without_path_or_stderr_leakage(
    tmp_path,
):
    template, mapping = _source_files(tmp_path)
    executable = _executable(tmp_path)

    def timeout(command, **_kwargs):
        raise subprocess.TimeoutExpired(command, timeout=5)

    renderer = LibreOfficeContractRenderer(executable=str(executable), runner=timeout)
    with pytest.raises(ContractRendererError) as captured:
        renderer.render(template_path=template, mapping_path=mapping, facts={})
    assert captured.value.code == "contract_pdf_renderer_timeout"
    assert str(tmp_path) not in str(captured.value)

    def failed(command, **_kwargs):
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=b"",
            stderr=f"secret renderer path: {tmp_path}".encode(),
        )

    renderer = LibreOfficeContractRenderer(executable=str(executable), runner=failed)
    with pytest.raises(ContractRendererError) as captured:
        renderer.render(template_path=template, mapping_path=mapping, facts={})
    assert captured.value.code == "contract_pdf_renderer_conversion_failed"
    assert str(tmp_path) not in str(captured.value)


def test_adapter_fails_closed_when_no_configured_or_path_executable(tmp_path):
    template, mapping = _source_files(tmp_path)
    renderer = LibreOfficeContractRenderer(executable_locator=lambda _name: None)

    with pytest.raises(ContractRendererError) as captured:
        renderer.render(template_path=template, mapping_path=mapping, facts={})

    assert captured.value.code == "contract_pdf_renderer_unavailable"


def test_adapter_maps_invalid_source_without_leaking_its_path(tmp_path):
    executable = _executable(tmp_path)
    missing_template = tmp_path / "private-case-directory" / "missing-template.xlsx"
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"param_mappings": {}}), encoding="utf-8")
    renderer = LibreOfficeContractRenderer(executable=str(executable))

    with pytest.raises(ContractRendererError) as captured:
        renderer.render(
            template_path=missing_template,
            mapping_path=mapping,
            facts={},
        )

    assert captured.value.code == "contract_pdf_renderer_source_invalid"
    assert str(tmp_path) not in str(captured.value)


def test_adapter_preserves_unresolved_mapping_failure(tmp_path):
    template = tmp_path / "approved-template.xlsx"
    Workbook().save(template)
    mapping = tmp_path / "approved-template.json"
    mapping.write_text(
        json.dumps(
            {
                "param_mappings": {
                    "A1": {"db_key": "", "status": "pending"}
                }
            }
        ),
        encoding="utf-8",
    )
    executable = _executable(tmp_path)
    renderer = LibreOfficeContractRenderer(executable=str(executable))

    with pytest.raises(ContractRendererError) as captured:
        renderer.render(template_path=template, mapping_path=mapping, facts={})

    assert captured.value.code == "contract_pdf_required_mapping_unresolved"
