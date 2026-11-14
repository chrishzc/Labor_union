"""Direct version-checked replacement of one case's imported account mappings."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Callable, Protocol

from domains.client_finance.virtual_account import (
    allows_case_account_edit,
    allows_historical_non_citizen_account,
    canonical_virtual_account,
)
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork


class CaseVirtualAccountError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(message)


@dataclass(frozen=True)
class AccountMapping:
    id: int
    virtual_account: str


@dataclass(frozen=True)
class AccountOccupant:
    id: int
    case_no: str
    cancelled: bool
    cancellation_event_id: int | None = None


@dataclass(frozen=True)
class CaseVirtualAccountView:
    case_no: str
    imported_virtual_accounts: tuple[str, ...]
    built_in_virtual_account: str | None
    mapping_ids: tuple[int, ...]
    editable: bool
    effective_virtual_account: str | None


@dataclass(frozen=True)
class CaseVirtualAccountReceipt:
    case_no: str
    before: tuple[str, ...]
    virtual_account: str
    transferred_from_case_nos: tuple[str, ...] = ()


class CaseVirtualAccountRepository(Protocol):
    def acquire_lock(self, key: str) -> bool: ...
    def release_lock(self, key: str) -> None: ...
    def load_case_mappings(self, case_no: str, *, lock: bool) -> tuple[AccountMapping, ...] | None: ...
    def resolve_formula_account(self, case_no: str) -> str | None: ...
    def resolve_effective_account(self, case_no: str) -> str | None: ...
    def account_occupants(self, case_no: str, account: str, *, lock: bool) -> tuple[AccountOccupant, ...]: ...
    def load_case_account_receipt(self, key: str) -> dict | None: ...
    def replace_case_account(self, case_no: str, account: str, digest: str, actor: str) -> None: ...
    def replace_historical_non_citizen_account(
        self, case_no: str, account: str, digest: str, actor: str, source_row: int,
        mapping_ids: tuple[int, ...], occupants: tuple[AccountOccupant, ...],
    ) -> None: ...
    def save_case_account_receipt(self, key: str, command: str, actor: str, result: dict) -> None: ...


class CaseVirtualAccountApplication:
    def __init__(self, repository: CaseVirtualAccountRepository, unit_of_work_factory: Callable[[], UnitOfWork]):
        self._repository = repository
        self._unit_of_work_factory = unit_of_work_factory

    def _mappings(self, case_no: str, *, lock: bool = False) -> tuple[AccountMapping, ...]:
        mappings = self._repository.load_case_mappings(case_no, lock=lock)
        if mappings is None:
            raise CaseVirtualAccountError("case_virtual_account_not_found", "查無此案件。", 404)
        return mappings

    def query(self, case_no: str) -> CaseVirtualAccountView:
        mappings = self._mappings(case_no)
        return CaseVirtualAccountView(
            case_no,
            tuple(row.virtual_account for row in mappings),
            self._repository.resolve_formula_account(case_no),
            tuple(row.id for row in mappings),
            allows_case_account_edit(case_no),
            self._repository.resolve_effective_account(case_no),
        )

    def apply(self, case_no: str, virtual_account: str, expected_mapping_ids: tuple[int, ...], key: str, actor: str) -> CaseVirtualAccountReceipt:
        account = canonical_virtual_account(virtual_account)
        command = fingerprint_payload({"case_no": case_no, "virtual_account": account, "expected_mapping_ids": expected_mapping_ids}).value
        if not self._repository.acquire_lock(key):
            raise CaseVirtualAccountError("case_virtual_account_lock_timeout", "目前有人正在更新虛擬帳號，請稍後再試。", 503)
        try:
            with self._unit_of_work_factory() as unit:
                stored = self._repository.load_case_account_receipt(key)
                if stored is not None:
                    if stored["request_fingerprint"] != command or stored["actor"] != actor:
                        raise CaseVirtualAccountError("case_virtual_account_idempotency_conflict", "相同操作識別碼已用於不同內容或操作人員。")
                    payload = json.loads(stored["result_snapshot"])
                    return CaseVirtualAccountReceipt(
                        payload["case_no"], tuple(payload["before"]), payload["virtual_account"],
                        tuple(payload.get("transferred_from_case_nos", ())),
                    )
                mappings = self._mappings(case_no, lock=True)
                if not allows_case_account_edit(case_no):
                    raise CaseVirtualAccountError("case_virtual_account_read_only", "本案依內建公式配號，無法修改。")
                if tuple(row.id for row in mappings) != expected_mapping_ids:
                    raise CaseVirtualAccountError("case_virtual_account_stale", "本案虛擬帳號已變更，請重新讀取後儲存。")
                occupants = self._repository.account_occupants(case_no, account, lock=True)
                transferable = allows_historical_non_citizen_account(case_no)
                conflicts = tuple(item.case_no for item in occupants if not transferable or not item.cancelled)
                if conflicts:
                    raise CaseVirtualAccountError(
                        "case_virtual_account_in_use", f"此虛擬帳號已對應其他案件：{'、'.join(conflicts)}，請核對後重新輸入。"
                    )
                receipt = CaseVirtualAccountReceipt(
                    case_no, tuple(row.virtual_account for row in mappings), account,
                    tuple(item.case_no for item in occupants),
                )
                source = json.dumps({"市府訂單號碼": case_no, "虛擬帳號": account}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                source_digest = sha256(source).hexdigest()
                if transferable:
                    self._repository.replace_historical_non_citizen_account(
                        case_no, account, source_digest, actor, 2, expected_mapping_ids, occupants,
                    )
                else:
                    self._repository.replace_case_account(case_no, account, source_digest, actor)
                self._repository.save_case_account_receipt(key, command, actor, asdict(receipt))
                unit.commit()
                return receipt
        finally:
            self._repository.release_lock(key)
