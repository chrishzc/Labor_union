"""
File: client_beclass_binding.py
Description: 分類 Client BeClass 姓名手機與案件候選，保留可稽核的唯一綁定結果。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ClientCaseBindingStatus(StrEnum):
    NO_CLIENT = "no_client"
    MULTIPLE_CLIENTS = "multiple_clients"
    CASE_NOT_UNIQUE = "case_not_unique"
    UNIQUE = "unique"


@dataclass(frozen=True, slots=True)
class ClientCaseBindingResolution:
    status: ClientCaseBindingStatus
    client_candidate_count: int
    case_candidate_count: int
    client_id: int | None = None
    case_no: str | None = None

    def __post_init__(self) -> None:
        if self.client_candidate_count < 0 or self.case_candidate_count < 0:
            raise ValueError("Client BeClass candidate counts must be non-negative")
        if self.status is ClientCaseBindingStatus.UNIQUE:
            if (
                self.client_candidate_count != 1
                or self.case_candidate_count != 1
                or not isinstance(self.client_id, int)
                or self.client_id <= 0
                or not str(self.case_no or "").strip()
            ):
                raise ValueError("unique Client BeClass binding is incomplete")
        elif self.client_id is not None or self.case_no is not None:
            raise ValueError("non-unique Client BeClass binding cannot expose a root")

    @property
    def issue_code(self) -> str | None:
        return {
            ClientCaseBindingStatus.NO_CLIENT: "client_case_binding_no_client",
            ClientCaseBindingStatus.MULTIPLE_CLIENTS: (
                "client_case_binding_multiple_clients"
            ),
            ClientCaseBindingStatus.CASE_NOT_UNIQUE: (
                "client_case_binding_case_not_unique"
            ),
            ClientCaseBindingStatus.UNIQUE: None,
        }[self.status]

    def bound_root(self) -> dict[str, object]:
        if self.status is not ClientCaseBindingStatus.UNIQUE:
            raise ValueError("Client BeClass binding root is not unique")
        return {"id": self.client_id, "case_no": self.case_no}


def classify_client_case_binding(
    client_ids: tuple[int, ...], case_nos: tuple[str, ...]
) -> ClientCaseBindingResolution:
    canonical_clients = tuple(sorted(set(client_ids)))
    canonical_cases = tuple(sorted({case_no.strip() for case_no in case_nos if case_no.strip()}))
    if not canonical_clients:
        return ClientCaseBindingResolution(ClientCaseBindingStatus.NO_CLIENT, 0, 0)
    if len(canonical_clients) > 1:
        return ClientCaseBindingResolution(
            ClientCaseBindingStatus.MULTIPLE_CLIENTS,
            len(canonical_clients),
            0,
        )
    if len(canonical_cases) != 1:
        return ClientCaseBindingResolution(
            ClientCaseBindingStatus.CASE_NOT_UNIQUE,
            1,
            len(canonical_cases),
        )
    return ClientCaseBindingResolution(
        ClientCaseBindingStatus.UNIQUE,
        1,
        1,
        canonical_clients[0],
        canonical_cases[0],
    )


__all__ = [
    "ClientCaseBindingResolution",
    "ClientCaseBindingStatus",
    "classify_client_case_binding",
]
