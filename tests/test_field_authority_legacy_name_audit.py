import copy

from scripts.verify_field_authority_legacy_names import (
    audit_report,
    load_manifest,
    verify_manifest,
)


def test_checked_in_legacy_name_audit_has_no_active_contract_id_reference():
    manifest = load_manifest()

    assert verify_manifest(manifest) == []
    reports = audit_report(manifest)["mappings"]
    assert all(report["unexpected_legacy_references"] == [] for report in reports)
    assert all(report["missing_canonical_paths"] == [] for report in reports)
    assert any(report["allowed_legacy_references"] for report in reports)


def test_legacy_name_audit_rejects_an_unapproved_reference(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "writer.py").write_text("contract_id = value\n", encoding="utf-8")
    (tmp_path / "canonical.py").write_text("contract_identity = value\n", encoding="utf-8")
    manifest = copy.deepcopy(load_manifest())
    manifest["scan_roots"] = ["api"]
    manifest["mappings"] = [manifest["mappings"][0]]
    mapping = manifest["mappings"][0]
    mapping["required_canonical_paths"] = ["canonical.py"]
    mapping["allowed_legacy_paths"] = []

    assert verify_manifest(manifest, tmp_path) == [
        "field-authority mapping orders-contract-identity-v1 has unexpected legacy references"
    ]
