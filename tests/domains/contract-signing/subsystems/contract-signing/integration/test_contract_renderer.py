"""
File: test_contract_renderer.py
Description: 驗證契約 renderer port、相容 XLSX 填值與公式型文字的 literal 安全契約。
"""

from io import BytesIO
import json
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook

from subsystems.contract_signing.contract_renderer import (
    ContractRenderer,
    ContractRendererError,
    RenderedContract,
    render_contract_template,
)


def test_renderer_fills_only_declared_snapshot_values(tmp_path):
    template = tmp_path / "template.xlsx"
    workbook = Workbook()
    workbook.active["A1"] = "unchanged"
    workbook.save(template)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"param_mappings": {"B2": {"db_key": "case_no"}, "C3": {"db_key": "pending"}}}), encoding="utf-8")

    rendered = render_contract_template(template_path=template, mapping_path=mapping, facts={"case_no": "CASE-1"})
    worksheet = load_workbook(BytesIO(rendered)).active

    assert worksheet["A1"].value == "unchanged"
    assert worksheet["B2"].value == "CASE-1"
    assert worksheet["C3"].value is None


def test_renderer_writes_formula_like_facts_as_literal_text(tmp_path):
    template = tmp_path / "template.xlsx"
    workbook = Workbook()
    workbook.save(template)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "param_mappings": {
                    "A1": {"db_key": "formula"},
                    "A2": {"db_key": "plus"},
                    "A3": {"db_key": "minus"},
                    "A4": {"db_key": "at"},
                }
            }
        ),
        encoding="utf-8",
    )
    facts = {
        "formula": "=WEBSERVICE(\"https://example.invalid\")",
        "plus": "+1+1",
        "minus": "-1+1",
        "at": "  @SUM(1,1)",
    }

    rendered = render_contract_template(
        template_path=template,
        mapping_path=mapping,
        facts=facts,
    )
    worksheet = load_workbook(BytesIO(rendered), data_only=False).active

    for row, expected in enumerate(facts.values(), start=1):
        cell = worksheet.cell(row=row, column=1)
        assert cell.value == expected
        assert cell.data_type == "s"


def test_missing_optional_fact_clears_legacy_formula_instead_of_printing_zero(tmp_path):
    template = tmp_path / "template.xlsx"
    workbook = Workbook()
    workbook.active['B19'] = '=B13+B15'
    workbook.save(template)
    mapping = tmp_path / 'mapping.json'
    mapping.write_text(json.dumps({'param_mappings': {'B19': {'db_key': 'staff_payable_total', 'requiredness': 'conditional'}}}), encoding='utf-8')
    rendered = render_contract_template(template_path=template, mapping_path=mapping, facts={})
    assert load_workbook(BytesIO(rendered)).active['B19'].value is None


@pytest.mark.parametrize('key', ['contract_client_copy', 'contract_staff_service'])
def test_approved_contract_drops_external_formulas_and_unrelated_historical_cache(key):
    from zipfile import ZipFile
    from subsystems.contract_signing.template_catalog import TEMPLATE_DIRECTORY, approved_template_mapping_path, load_approved_template
    from subsystems.contract_signing.contract_renderer import external_formula_cells
    template = load_approved_template(key)
    mapping = approved_template_mapping_path(key)
    payload = json.loads(mapping.read_text())
    facts = {item['db_key']: '合成值' for item in payload['param_mappings'].values() if item.get('db_key') and item.get('requiredness') == 'required'}
    output = render_contract_template(template_path=TEMPLATE_DIRECTORY/template.template_filename, mapping_path=mapping, facts=facts)
    assert external_formula_cells(output) == ()
    with ZipFile(BytesIO(output)) as archive:
        assert not any(path.startswith('xl/externalLinks/') for path in archive.namelist())
    sheet = load_workbook(BytesIO(output)).active
    if key == 'contract_client_copy':
        assert len(payload['static_cells']) == 38
        assert sheet.row_dimensions[64].height == 42
        for cell, value in payload['static_cells'].items():
            assert sheet[cell].value == value
    else:
        assert sheet['D13'].value is None  # employer cost must not appear as staff compensation
        assert sheet['A13'].value == '整筆應付金額'
        assert sheet['A14'].value is None
        assert sheet['C11'].value is None
        assert not any('補助費用' in str(cell.value) or '雇主自費' in str(cell.value) for row in sheet for cell in row)


def test_restored_catalogue_matches_only_the_exact_original_cached_source():
    from zipfile import ZipFile
    from xml.etree import ElementTree as ET
    from subsystems.contract_signing.template_catalog import PROJECT_ROOT, approved_template_mapping_path
    with ZipFile(PROJECT_ROOT/'document/管理端UI/表格需求模板/所需表格.xlsx') as archive:
        root = ET.fromstring(archive.read('xl/externalLinks/externalLink1.xml'))
    names = [item.attrib['val'] for item in root.findall('.//{*}sheetName')]
    catalog = next(item for item in root.findall('.//{*}sheetData') if names[int(item.attrib['sheetId'])] == '目錄')
    items = {}
    for row in catalog.findall('./{*}row'):
        if not 5 <= int(row.attrib['r']) <= 32:
            continue
        cells = {item.attrib['r'].rstrip('0123456789'): item.findtext('./{*}v') for item in row.findall('./{*}cell')}
        if (cells.get('L') or '').isdigit():
            items[int(cells['L'])] = (cells['M'], cells['N'])
    mappings = json.loads(approved_template_mapping_path('contract_client_copy').read_text())['static_cells']
    rows = (56,57,58,59,62,63,64,65,69,70,73,74,75,76,77,80,81,82,83)
    assert len(items) == len(rows) == 19
    for item, row in enumerate(rows, 1):
        assert (mappings[f'B{row}'], mappings[f'C{row}']) == items[item]


def test_renderer_fails_closed_for_unresolved_mapping_descriptor(tmp_path):
    template = tmp_path / "template.xlsx"
    Workbook().save(template)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "param_mappings": {
                    "A1": {
                        "db_key": "",
                        "status": "pending",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractRendererError) as captured:
        render_contract_template(
            template_path=template,
            mapping_path=mapping,
            facts={"case_no": "CASE-1"},
        )

    assert captured.value.code == "contract_pdf_required_mapping_unresolved"


def test_renderer_fails_closed_for_missing_fact_in_approved_mapping(tmp_path):
    template = tmp_path / "template.xlsx"
    Workbook().save(template)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "id": "contract_client_copy",
                "param_mappings": {
                    "A1": {
                        "db_key": "typed_owner_fact",
                        "requiredness": "required",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractRendererError) as captured:
        render_contract_template(
            template_path=template,
            mapping_path=mapping,
            facts={"case_no": "CASE-1"},
        )

    assert captured.value.code == "contract_pdf_required_mapping_missing"


def test_renderer_fails_closed_when_approved_mapping_lacks_requiredness(tmp_path):
    template = tmp_path / "template.xlsx"
    Workbook().save(template)
    mapping = tmp_path / "mapping.json"
    mapping.write_text(
        json.dumps(
            {
                "id": "contract_client_copy",
                "param_mappings": {"A1": {"db_key": "typed_owner_fact"}},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ContractRendererError) as captured:
        render_contract_template(
            template_path=template,
            mapping_path=mapping,
            facts={"typed_owner_fact": "value"},
        )

    assert captured.value.code == "contract_pdf_required_mapping_unresolved"


def test_rendered_contract_validates_its_pdf_contract():
    rendered = RenderedContract.from_pdf_bytes(
        content=b"%PDF-1.7\nbody\n%%EOF\n",
        filename="approved-contract.pdf",
        renderer_identity="libreoffice-headless",
    )

    assert rendered.mime_type == "application/pdf"
    assert rendered.filename == "approved-contract.pdf"
    assert len(rendered.sha256) == 64
    assert isinstance(object(), ContractRenderer) is False
