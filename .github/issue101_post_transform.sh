#!/usr/bin/env bash
set -euo pipefail

python - <<'PY'
from pathlib import Path


def replace_any(path: str, replacements: list[tuple[str, str]], *, minimum: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    changed = 0
    for old, new in replacements:
        if old in text:
            changed += text.count(old)
            text = text.replace(old, new)
    if changed < minimum:
        raise RuntimeError(f"{path}: expected at least {minimum} canonical regression replacement(s), got {changed}")
    target.write_text(text, encoding="utf-8")


# Data Browser: removing the `masked` presentation value must leave canonical
# name cells with an explicit text presentation rather than a 3-argument call.
replace_any(
    "infrastructure/mysql/data_browser_query_repository.py",
    [
        ('_cell("name", "客戶姓名", name),', '_cell("name", "客戶姓名", name, "text"),'),
        ('_cell("name", "服務人員姓名", name),', '_cell("name", "服務人員姓名", name, "text"),'),
        ('_cell("name", "報名者", name),', '_cell("name", "報名者", name, "text"),'),
    ],
    minimum=3,
)

# Rewrite the legacy Data Browser privacy regression as the #101 canonical
# projection contract. Fields outside the allowlisted projection remain absent;
# values that are projected are no longer obfuscated.
Path("tests/test_data_browser_privacy.py").write_text(
    '''"""Regression coverage for canonical Data Browser projections after issue #101."""

from __future__ import annotations

import json

from api.schemas.data_browser import DataBrowserPageView
from infrastructure.mysql.data_browser_query_repository import DataBrowserQueryRepository


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, _sql, _params):
        return None

    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _Cursor(self.rows)


def _render(source_id, row):
    page = DataBrowserQueryRepository(_Connection([row])).query_page(
        source_id,
        limit=25,
        after=None,
        query=None,
    )
    return json.dumps(
        DataBrowserPageView.model_validate(page).model_dump(mode="json"),
        ensure_ascii=False,
    )


def test_client_and_staff_rows_preserve_canonical_names_without_expanding_projection():
    client = _render(
        "clients",
        {
            "id": 7,
            "name": "林佩萱",
            "city": "台北市",
            "identity_status": "一般市民",
            "db_created_at": "2026-08-01T00:00:00",
            "db_updated_at": "2026-08-02T00:00:00",
            "phone": "OUTSIDE_PROJECTION_PHONE",
            "address": "OUTSIDE_PROJECTION_ADDRESS",
        },
    )
    staff = _render(
        "staff",
        {
            "id": 9,
            "name": "王美惠",
            "city": "新竹市",
            "status": "active",
            "created_at": "2026-08-01T00:00:00",
            "updated_at": "2026-08-02T00:00:00",
            "identity_card": "OUTSIDE_PROJECTION_ID",
            "bank_account": "OUTSIDE_PROJECTION_ACCOUNT",
        },
    )

    assert "林佩萱" in client
    assert "王美惠" in staff
    assert "OUTSIDE_PROJECTION_PHONE" not in client
    assert "OUTSIDE_PROJECTION_ADDRESS" not in client
    assert "OUTSIDE_PROJECTION_ID" not in staff
    assert "OUTSIDE_PROJECTION_ACCOUNT" not in staff


def test_bank_row_exposes_canonical_amount_without_expanding_projection():
    rendered = _render(
        "bank_facts",
        {
            "id": 12,
            "dedup_fingerprint": "a" * 64,
            "transaction_date": "2026-08-17",
            "direction": "incoming",
            "classification_type": "pending",
            "reconciliation_status": "pending",
            "credit": 78000,
            "debit": None,
            "created_at": "2026-08-17T00:00:00",
            "source_bank_account": "OUTSIDE_PROJECTION_ACCOUNT",
            "counterparty_name": "OUTSIDE_PROJECTION_COUNTERPARTY",
            "raw_payload": {"secret": "raw"},
        },
    )

    assert "78000" in rendered
    assert "OUTSIDE_PROJECTION_ACCOUNT" not in rendered
    assert "OUTSIDE_PROJECTION_COUNTERPARTY" not in rendered
    assert "raw_payload" not in rendered
''',
    encoding="utf-8",
)

# The old UI test points at the retired Streamlit page. Keep the acceptance
# assertion on the current backend projection/ownership surface instead.
Path("tests/test_data_browser_identity_status_ui.py").write_text(
    '''"""Acceptance coverage for the current Data Browser client identity source."""

from pathlib import Path

from subsystems.access.data_browser_maintenance import EDITABLE_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT / "infrastructure/mysql/data_browser_query_repository.py"


def test_data_browser_projects_client_identity_status_with_the_expected_label():
    source = REPOSITORY.read_text(encoding="utf-8")
    assert '_cell("identity_status", "身分資格"' in source


def test_client_identity_status_is_read_only_in_data_browser():
    assert "identity_status" not in EDITABLE_COLUMNS["clients"]
''',
    encoding="utf-8",
)

replace_any(
    "tests/domains/case-import/subsystems/case-import/modules/staff-historical-workbook-adoption/regression/test_review_intake_translation.py",
    [("staff-***-6789", "A123456789")],
    minimum=2,
)
replace_any(
    "tests/test_beclass_review_intake.py",
    [
        ('"client-***-1234"', '"ABC1234"'),
        ('"client-***-none"', '"client-unknown"'),
    ],
    minimum=2,
)
replace_any(
    "tests/test_finance_import_warning_occurrences.py",
    [('"finance-row-***-17"', '"finance-row-17"')],
)
replace_any(
    "tests/test_finance_query_page_routes.py",
    [
        ('recipient_name="去敏受款人"', 'recipient_name="完整受款人"'),
        ('row["bank_account"].endswith("9012")', 'row["bank_account"] == "123456789012"'),
        ('row["recipient_identity_card"] == "A*********"', 'row["recipient_identity_card"] == "A123456789"'),
        ('assert "123456789012" not in response.text', 'assert "123456789012" in response.text'),
        ('assert "A123456789" not in response.text', 'assert "A123456789" in response.text'),
    ],
    minimum=5,
)
replace_any(
    "tests/test_government_subsidy_report_query_contract.py",
    [
        ('row["employer_name"] == "王**"', 'row["employer_name"] == "王小美"'),
        ('row["identity_card"] == "A*********"', 'row["identity_card"] == "A123456789"'),
        ('row["address_masked"] == "地址已遮罩"', 'row["address"] == "完整地址"'),
        ('row["address"] == "地址已遮罩"', 'row["address"] == "完整地址"'),
        ('row["address"] == "—"', 'row["address"] == "完整地址"'),
        ('assert "A123456789" not in quarterly.text', 'assert "A123456789" in quarterly.text'),
        ('assert "完整地址" not in quarterly.text', 'assert "完整地址" in quarterly.text'),
    ],
    minimum=5,
)
replace_any(
    "tests/test_weekly_operations_report_contract.py",
    [
        ('data["case_rows"][0]["applicant_name"] == "王**"', 'data["case_rows"][0]["applicant_name"] == "王小美"'),
        ('data["subsidy_partitions"][0]["rows"][0]["identity_card"] == "A*********"', 'data["subsidy_partitions"][0]["rows"][0]["identity_card"] == "A123456789"'),
        ('assert "王小美" not in response.text', 'assert "王小美" in response.text'),
        ('assert "A123456789" not in response.text', 'assert "A123456789" in response.text'),
        ('assert "完整地址" not in response.text', 'assert "完整地址" in response.text'),
        ('assert "王小美" not in workbook_text', 'assert "王小美" in workbook_text'),
        ('assert "A123456789" not in workbook_text', 'assert "A123456789" in workbook_text'),
        ('assert "完整地址" not in workbook_text', 'assert "完整地址" in workbook_text'),
    ],
    minimum=8,
)
PY

python - <<'PY'
from pathlib import Path
import hashlib
import json

root = Path(".")
assembly_path = root / "db/schema_assembly/labor_union_fresh_schema_v1.json"
cutover_path = root / "db/cutover_releases/labor_union_validation_schema_v1.json"
assembly = json.loads(assembly_path.read_text(encoding="utf-8"))
cutover = json.loads(cutover_path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


active = list(assembly["active_bootstrap"])
cutover["base_schema"]["sha256"] = sha256(root / assembly["base_schema"]["path"])
cutover["schema_parts"]["expected_count"] = len(active)
cutover["schema_parts"]["ordered_digest_sha256"] = assembly["active_artifacts_sha256"]
cutover["schema_parts"]["terminal_artifact"] = Path(active[-1]).name
cutover["schema_assembly"]["sha256"] = sha256(assembly_path)
cutover_path.write_text(
    json.dumps(cutover, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

python scripts/build_validation_schema_release.py
python - <<'PY'
from scripts.build_validation_schema_release import verify_release
from scripts.verify_validation_schema_manifest import load_manifest, verify_manifest

manifest = load_manifest()
errors = [*verify_manifest(manifest), *verify_release(manifest)]
if errors:
    raise SystemExit("validation release refresh failed: " + "; ".join(errors))
PY

git diff --check
