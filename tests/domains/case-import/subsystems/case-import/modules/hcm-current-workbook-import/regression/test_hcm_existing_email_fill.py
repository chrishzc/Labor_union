"""Existing-case email fills do not enter case reconstruction or reconciliation."""
from types import SimpleNamespace
import json
import pandas as pd
import pytest

from scripts.imports import import_client_hcm as intake
from subsystems.case_import.hcm_workbook_import import HcmWorkbookImportService, HcmWorkbookConflict


@pytest.mark.parametrize("changed,outcome", [(True, "email_filled"), (False, "skipped_existing")])
def test_existing_email_lane_ignores_all_other_invalid_source_fields(monkeypatch, changed, outcome):
    def forbidden(*args, **kwargs):
        raise AssertionError("email-only rows cannot reconstruct cases, bootstrap, or reconcile")
    monkeypatch.setattr(intake, "_hcm_import_intent", forbidden)
    monkeypatch.setattr(intake, "_reconcile_without_rolling_back_hcm", forbidden)
    monkeypatch.setattr(intake.MySqlClientProfileRepository, "load_email_fill_target",
                        lambda *_: {"client_id": 1, "client_profile_version": 0, "email": None})
    calls = []
    monkeypatch.setattr(intake.ClientProfileApplication, "fill_hcm_email_in_current_uow",
        lambda repository, case_no, email, **kw: calls.append((case_no, email, kw)) or changed)
    row = pd.Series({"查詢序號(案件編號)": "SYNTH-EMAIL", "姓名": "不採納姓名", "行動電話": "invalid", "email": "hcm@example.com"})
    application = SimpleNamespace(resolve_hcm_identity=forbidden)
    result = intake._import_row(row, 2, None, application, "synthetic.xlsx", connection=object(),
        source_digest="a" * 64, source_sheet="HCM", detailed=True, current_uow=True)
    assert result["outcome"] == outcome and result["problem_fields"] == []
    assert calls[0][:2] == ("SYNTH-EMAIL", "hcm@example.com")
    assert "a" * 64 in calls[0][2]["source_identity"]


class ReceiptRepository:
    def __init__(self): self.saved = None
    def acquire_lock(self, key): return True
    def release_lock(self, key): pass
    def claim(self, *args): return "created"
    def load_receipt(self, key): return self.saved
    def load_receipt_by_digest(self, digest): return self.saved
    def save_receipt(self, key, digest, actor, snapshot):
        self.saved = {"request_fingerprint": digest, "result_snapshot": json.dumps(snapshot)}


class Uow:
    def __init__(self): self.commits = 0
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def commit(self): self.commits += 1


class EmailIntake:
    def __init__(self): self.empty = True; self.writes = 0
    def preview_rows(self, frame, path):
        return {"ready": 1, "email_fill": int(self.empty)}
    def import_rows(self, *args): raise AssertionError("must borrow outer workbook UoW")
    def import_rows_in_current_uow(self, frame, path):
        self.empty = False; self.writes += 1
        return {"email_filled": 1, "row_outcomes": [{"source_row": 1, "case_no": "SYNTH-EMAIL",
            "outcome": "email_filled", "problem_identity": None, "problem_fields": [], "issue_codes": [],
            "referral_occurrence_identities": []}]}


def test_applied_email_workbook_replays_original_receipt_before_changed_eligibility(tmp_path):
    path = tmp_path / "synthetic.xlsx"; path.write_bytes(b"synthetic source")
    repository, rows, uow = ReceiptRepository(), EmailIntake(), Uow()
    service = HcmWorkbookImportService(repository, rows, lambda: uow)
    frame = pd.DataFrame([{}])
    preview = service.preview(frame, str(path))
    assert preview.email_fill_count == 1
    result = service.apply(frame, str(path), preview.preview_fingerprint, "synthetic-key", "admin", "corr")
    assert result.email_filled_count == 1 and result.inserted_count == 0
    assert result.row_outcomes[0].outcome == "email_filled"
    replay = service.apply(frame, str(path), preview.preview_fingerprint, "synthetic-key", "admin", "corr2")
    assert replay.replayed_workbook and replay.email_filled_count == 1
    assert rows.writes == 1 and uow.commits == 1


def test_email_filled_between_preview_and_apply_is_a_typed_stale_conflict(tmp_path):
    path = tmp_path / "synthetic.xlsx"; path.write_bytes(b"synthetic source")
    repository, rows = ReceiptRepository(), EmailIntake()
    service = HcmWorkbookImportService(repository, rows, Uow)
    frame = pd.DataFrame([{}]); preview = service.preview(frame, str(path))
    rows.empty = False
    with pytest.raises(HcmWorkbookConflict, match="hcm_workbook_preview_stale"):
        service.apply(frame, str(path), preview.preview_fingerprint, "synthetic-key", "admin", "corr")
    assert rows.writes == 0 and repository.saved is None
