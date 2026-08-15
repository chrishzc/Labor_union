"""
File: client_beclass_workbook_import.py
Description: 協調 Client BeClass 暫時活頁簿的 typed Preview、逐列 Apply 與 replay 收據。
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd

from domains.case_import.client_beclass_validation import CLIENT_BECLASS_REQUIRED_HEADERS, validate_client_beclass_row
from infrastructure.mysql.client_beclass_workbook_import_repository import ClientBeClassWorkbookImportRepository
from infrastructure.mysql.unit_of_work import MySqlUnitOfWork
from shared_kernel.fingerprints import fingerprint_payload
from subsystems.case_import.beclass_review_intake import masked_review_identifier, record_invalid_beclass_row
from domains.case_import.beclass_import_review import BeClassImportSourceKind


@dataclass(frozen=True, slots=True)
class ClientBeClassWorkbookPreview:
    source_content_digest: str
    sheet_identity: str
    source_row_count: int
    create_count: int
    review_required_count: int
    existing_conflict_count: int
    existing_source_count: int
    preview_fingerprint: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_content_digest": self.source_content_digest,
            "sheet_identity": self.sheet_identity,
            "source_row_count": self.source_row_count,
            "create_count": self.create_count,
            "review_required_count": self.review_required_count,
            "existing_conflict_count": self.existing_conflict_count,
            "existing_source_count": self.existing_source_count,
            "preview_fingerprint": self.preview_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class ClientBeClassWorkbookReceipt:
    source_content_digest: str
    source_row_count: int
    created_count: int
    exact_replay_count: int
    review_required_count: int
    existing_conflict_count: int
    existing_source_count: int
    replayed_workbook: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "source_content_digest": self.source_content_digest,
            "source_row_count": self.source_row_count,
            "created_count": self.created_count,
            "exact_replay_count": self.exact_replay_count,
            "review_required_count": self.review_required_count,
            "existing_conflict_count": self.existing_conflict_count,
            "existing_source_count": self.existing_source_count,
            "replayed_workbook": self.replayed_workbook,
        }


@dataclass(frozen=True, slots=True)
class _Workbook:
    digest: str
    sheet_identity: str
    rows: tuple[tuple[int, dict[str, Any]], ...]


class ClientBeClassWorkbookConflict(RuntimeError):
    pass


class ClientBeClassWorkbookUnavailable(RuntimeError):
    pass


class ClientBeClassWorkbookImportService:
    def __init__(self, repository: ClientBeClassWorkbookImportRepository) -> None:
        self._repository = repository

    def preview(self, source_path: str) -> ClientBeClassWorkbookPreview:
        workbook = _load_workbook(source_path)
        outcomes = Counter(self._preview_outcome(row) for _, row in workbook.rows)
        return _preview_from_outcomes(workbook, outcomes)

    def apply(self, source_path: str, key: str, supplied_preview: str, actor: str, correlation_id: str) -> ClientBeClassWorkbookReceipt:
        if not self._repository.acquire_lock(key):
            raise ClientBeClassWorkbookUnavailable("client_beclass_workbook_coordinator_lock_timeout")
        try:
            workbook = _load_workbook(source_path)
            replay = self._stored_replay(key, workbook.digest)
            if replay is not None:
                return replay
            preview = self.preview(source_path)
            if preview.preview_fingerprint != supplied_preview:
                raise ClientBeClassWorkbookConflict("client_beclass_preview_stale")
            self._claim_workbook(key, workbook.digest, correlation_id)
            outcomes = Counter(self._apply_row(workbook, row_number, row, actor, correlation_id) for row_number, row in workbook.rows)
            _assert_conservation(len(workbook.rows), outcomes)
            receipt = ClientBeClassWorkbookReceipt(workbook.digest, len(workbook.rows), outcomes["created"], outcomes["exact_replay"], outcomes["review_required"], outcomes["existing_conflict"], outcomes["existing_source"], False)
            self._save_workbook_receipt(key, workbook.digest, preview.preview_fingerprint, actor, receipt)
            return receipt
        finally:
            self._repository.release_lock(key)

    def _preview_outcome(self, row: dict[str, Any]) -> str:
        if validate_client_beclass_row(row):
            return "review_required"
        payload = _normalized_payload(row)
        source_state = self._repository.source_state(payload)
        if source_state == "exact":
            return "existing_source"
        if source_state == "conflict":
            return "existing_conflict"
        return "create" if self._repository.resolve_unique_client_case(payload["name"], payload["phone"]) else "existing_conflict"

    # Why: every branch must persist the row receipt and review in the same outer row transaction.
    def _apply_row(self, workbook: _Workbook, row_number: int, row: dict[str, Any], actor: str, correlation_id: str) -> str:
        source_identity = _source_identity(workbook.digest, row_number)
        payload = _normalized_payload(row)
        fingerprint = fingerprint_payload(payload).value
        with MySqlUnitOfWork(self._repository.connection) as unit_of_work:
            stored = self._repository.load_row_receipt(source_identity)
            if stored is not None:
                _require_same_fingerprint(stored, fingerprint)
                self._repository.require_matching_client_root(stored)
                unit_of_work.commit()
                return "exact_replay"
            self._repository.claim_row(source_identity, fingerprint, correlation_id)
            errors = validate_client_beclass_row(row)
            if errors:
                review_identity = record_invalid_beclass_row(
                    self._repository.connection, source_kind=BeClassImportSourceKind.CLIENT,
                    source_content_digest=workbook.digest, source_sheet=workbook.sheet_identity,
                    source_row=row_number, masked_identifier=masked_review_identifier(BeClassImportSourceKind.CLIENT, payload.get("query_no"), row_number),
                    source_payload=_safe_review_payload(payload), issue_codes=tuple(sorted(errors)),
                )
                self._repository.save_row_receipt(source_identity, fingerprint, None, "review_required", review_identity, actor)
                unit_of_work.commit()
                return "review_required"
            source_state = self._repository.source_state(payload)
            if source_state == "exact":
                self._repository.save_row_receipt(source_identity, fingerprint, None, "existing_source", None, actor)
                unit_of_work.commit()
                return "existing_source"
            if source_state == "conflict":
                outcome = self._save_review_outcome(
                    workbook, row_number, payload, source_identity, fingerprint,
                    actor, "client_beclass_source_payload_conflict",
                )
                unit_of_work.commit()
                return outcome
            client_case = self._repository.resolve_unique_client_case(payload["name"], payload["phone"])
            if client_case is None:
                outcome = self._save_review_outcome(
                    workbook, row_number, payload, source_identity, fingerprint,
                    actor, "client_case_binding_not_unique",
                )
                unit_of_work.commit()
                return outcome
            source_id = self._repository.create_bound_source_if_absent(payload, client_case)
            if source_id is None:
                outcome = "existing_source"
                review_identity = None
                if self._repository.source_state(payload) == "conflict":
                    outcome = "existing_conflict"
                    review_identity = self._record_review(
                        workbook, row_number, payload,
                        "client_beclass_source_payload_conflict",
                    )
                self._repository.save_row_receipt(source_identity, fingerprint, None, outcome, review_identity, actor)
                unit_of_work.commit()
                return outcome
            self._repository.save_row_receipt(source_identity, fingerprint, source_id, "created", None, actor)
            unit_of_work.commit()
            return "created"

    def _save_review_outcome(self, workbook, row_number, payload, source_identity, fingerprint, actor, issue_code) -> str:
        review_identity = self._record_review(workbook, row_number, payload, issue_code)
        self._repository.save_row_receipt(
            source_identity, fingerprint, None, "existing_conflict",
            review_identity, actor,
        )
        return "existing_conflict"

    def _record_review(self, workbook, row_number, payload, issue_code) -> str:
        return record_invalid_beclass_row(
            self._repository.connection, source_kind=BeClassImportSourceKind.CLIENT,
            source_content_digest=workbook.digest, source_sheet=workbook.sheet_identity,
            source_row=row_number,
            masked_identifier=masked_review_identifier(
                BeClassImportSourceKind.CLIENT, payload["query_no"], row_number,
            ),
            source_payload=_safe_review_payload(payload), issue_codes=(issue_code,),
        )

    def _stored_replay(self, key: str, digest: str) -> ClientBeClassWorkbookReceipt | None:
        stored = self._repository.load_workbook_receipt(key)
        if stored is None:
            return None
        if stored["request_fingerprint"] != digest:
            raise ClientBeClassWorkbookConflict("client_beclass_workbook_idempotency_conflict")
        return ClientBeClassWorkbookReceipt(**{**json.loads(stored["result_snapshot"]), "replayed_workbook": True})

    def _claim_workbook(self, key: str, digest: str, correlation_id: str) -> None:
        with MySqlUnitOfWork(self._repository.connection) as unit_of_work:
            if self._repository.claim_workbook(key, digest, correlation_id) == "conflict":
                raise ClientBeClassWorkbookConflict("client_beclass_workbook_idempotency_conflict")
            unit_of_work.commit()

    def _save_workbook_receipt(self, key: str, digest: str, preview: str, actor: str, receipt: ClientBeClassWorkbookReceipt) -> None:
        with MySqlUnitOfWork(self._repository.connection) as unit_of_work:
            self._repository.save_workbook_receipt(key, digest, preview, actor, receipt.as_dict())
            unit_of_work.commit()


def _load_workbook(source_path: str) -> _Workbook:
    path = Path(source_path)
    digest = sha256(path.read_bytes()).hexdigest()
    with pd.ExcelFile(path, engine="openpyxl") as excel:
        candidates = [(index, name, excel.parse(sheet_name=name, dtype=object)) for index, name in enumerate(excel.sheet_names)]
    matches = [(index, frame) for index, _, frame in candidates if not frame.dropna(how="all").empty and CLIENT_BECLASS_REQUIRED_HEADERS <= {str(column).strip() for column in frame.columns}]
    if len(matches) != 1:
        raise ValueError("client_beclass_workbook_sheet_contract_not_unique")
    sheet_index, frame = matches[0]
    rows = tuple((ordinal, {str(key).strip(): value for key, value in row.items()}) for ordinal, (_, row) in enumerate(frame.iterrows(), start=2) if not _blank_row(row))
    return _Workbook(digest, sha256(f"sheet:{sheet_index}".encode()).hexdigest(), rows)


def _preview_from_outcomes(workbook: _Workbook, outcomes: Counter[str]) -> ClientBeClassWorkbookPreview:
    row_contracts = tuple(
        (
            row_number,
            fingerprint_payload(_normalized_payload(row)).value,
            tuple(sorted(validate_client_beclass_row(row))),
        )
        for row_number, row in workbook.rows
    )
    fingerprint = fingerprint_payload({"digest": workbook.digest, "sheet": workbook.sheet_identity, "rows": row_contracts, "outcomes": dict(sorted(outcomes.items()))}).value
    return ClientBeClassWorkbookPreview(workbook.digest, workbook.sheet_identity, len(workbook.rows), outcomes["create"], outcomes["review_required"], outcomes["existing_conflict"], outcomes["existing_source"], fingerprint)


def _normalized_payload(row: dict[str, Any]) -> dict[str, object]:
    details = {key: _text(value) for key, value in row.items() if key not in {"項次", "查詢序號", "報名時間", "姓名", "Email", "行動電話", "市話", "分機", "縣市", "郵遞區號", "地址", "補助款退款:銀行代號+分行代號", "銀行帳號", "管理者註記事項", "出生年", "月", "日"} and not str(key).startswith("Unnamed") and _text(value)}
    return {"query_no": _text(row.get("查詢序號")), "created_at": _text(row.get("報名時間")), "name": _text(row.get("姓名")), "email": _text(row.get("Email")), "phone": _phone(row.get("行動電話")), "tel": _text(row.get("市話")), "ext": _text(row.get("分機")), "city": _text(row.get("縣市")), "zip_code": _text(row.get("郵遞區號")), "address": _text(row.get("地址")), "refund_bank_code": _digits(row.get("補助款退款:銀行代號+分行代號")), "refund_account_no": _digits(row.get("銀行帳號")), "admin_notes": _text(row.get("管理者註記事項")), "birth_date": _birth_date(row), "survey_details": json.dumps(details, ensure_ascii=False, sort_keys=True, separators=(",", ":"))}


def _safe_review_payload(payload: dict[str, object]) -> dict[str, object]:
    return {"has_query_no": bool(payload.get("query_no")), "has_name": bool(payload.get("name")), "has_phone": bool(payload.get("phone")), "source_field_count": len(payload)}


def _birth_date(row: dict[str, Any]) -> str | None:
    try:
        year = int(row.get("出生年")); year += 1911 if year < 1900 else 0
        return f"{year:04d}-{int(row.get('月')):02d}-{int(row.get('日')):02d}"
    except (TypeError, ValueError):
        return None


def _phone(value: object) -> str | None:
    digits = _digits(value)
    if digits and len(digits) == 9 and digits.startswith("9"):
        return f"0{digits}"
    return digits


def _digits(value: object) -> str | None:
    text = _text(value)
    if text is None:
        return None
    return "".join(character for character in text if character.isdigit()) or None


def _text(value: object) -> str | None:
    return None if value is None or pd.isna(value) or not str(value).strip() else str(value).strip()


def _blank_row(row) -> bool:
    return all(value is None or pd.isna(value) or not str(value).strip() for value in row.values)


def _source_identity(digest: str, row_number: int) -> str:
    return f"client-beclass-workbook:{digest}:row:{row_number}"


def _require_same_fingerprint(stored, fingerprint: str) -> None:
    if stored["request_fingerprint"] != fingerprint:
        raise ClientBeClassWorkbookConflict("client_beclass_source_identity_conflict")


def _assert_conservation(row_count: int, outcomes: Counter[str]) -> None:
    if sum(outcomes.values()) != row_count:
        raise RuntimeError("client_beclass_workbook_outcomes_not_conserved")
