"""Direct version-checked replacement of one case's imported account mappings."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Callable, Protocol

from domains.client_finance.virtual_account import canonical_virtual_account
from shared_kernel.fingerprints import fingerprint_payload
from shared_kernel.ports import UnitOfWork
from subsystems.client_finance.virtual_account_resolution import build_client_virtual_account


class CaseVirtualAccountError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code, self.status = code, status
        super().__init__(message)


@dataclass(frozen=True)
class AccountMapping:
    id: int
    virtual_account: str


@dataclass(frozen=True)
class CaseVirtualAccountView:
    case_no: str
    imported_virtual_accounts: tuple[str, ...]
    built_in_virtual_account: str | None
    mapping_ids: tuple[int, ...]


@dataclass(frozen=True)
class CaseVirtualAccountReceipt:
    case_no: str
    before: tuple[str, ...]
    virtual_account: str


class CaseVirtualAccountRepository(Protocol):
    def acquire_lock(self, key: str) -> bool: ...
    def release_lock(self, key: str) -> None: ...
    def load_case_mappings(self, case_no: str, *, lock: bool) -> tuple[AccountMapping, ...] | None: ...
    def account_used_by_other_case(self, case_no: str, account: str, *, lock: bool) -> bool: ...
    def load_case_account_receipt(self, key: str) -> dict | None: ...
    def replace_case_account(self, case_no: str, account: str, digest: str, actor: str) -> None: ...
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
        return CaseVirtualAccountView(case_no, tuple(row.virtual_account for row in mappings), build_client_virtual_account(case_no), tuple(row.id for row in mappings))

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
                    return CaseVirtualAccountReceipt(payload["case_no"], tuple(payload["before"]), payload["virtual_account"])
                mappings = self._mappings(case_no, lock=True)
                if tuple(row.id for row in mappings) != expected_mapping_ids:
                    raise CaseVirtualAccountError("case_virtual_account_stale", "本案虛擬帳號已變更，請重新讀取後儲存。")
                if self._repository.account_used_by_other_case(case_no, account, lock=True):
                    raise CaseVirtualAccountError("case_virtual_account_in_use", "此虛擬帳號已對應其他案件，請核對後重新輸入。")
                receipt = CaseVirtualAccountReceipt(case_no, tuple(row.virtual_account for row in mappings), account)
                source = json.dumps({"市府訂單號碼": case_no, "虛擬帳號": account}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
                source_digest = sha256(source).hexdigest()
                self._repository.replace_case_account(case_no, account, source_digest, actor)
                self._repository.save_case_account_receipt(key, command, actor, asdict(receipt))
                unit.commit()
                return receipt
        finally:
            self._repository.release_lock(key)
