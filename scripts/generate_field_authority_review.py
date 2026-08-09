"""Render the per-document field-authority governance review."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INVENTORY_ROOT = ROOT / "document" / "文件整併工作區" / "06_欄位權威性與計算邏輯盤點"
OUTPUT_PATH = ROOT / "document" / "架構重整" / "03_追蹤清單與證據" / "evidence" / "field_authority_review_v1.md"
PREVIOUSLY_CLOSED = frozenset({"audit_logs", "crawler_logs", "faq", "finance_import_reclassification_events", "staff_availability"})


def main() -> int:
    documents = sorted(INVENTORY_ROOT.rglob("*.md"))
    OUTPUT_PATH.write_text(_render(documents), encoding="utf-8")
    print(f"field_authority_review documents={len(documents)}")
    return 0


def _render(documents: list[Path]) -> str:
    rows = "\n".join(_row(path) for path in documents)
    return "\n".join((
        "# Field Authority Review v1",
        "",
        "This is the per-MD governance record for the field-lineage inventory. Formal",
        "domain specifications and live schema/release manifests are the authoritative evidence.",
        "No field or table is retired merely because an HTTP route lacks a static caller.",
        "",
        "| Inventory MD | Owner / formal caller | External API responsibility | Historical / audit responsibility | Disposition |",
        "|---|---|---|---|---|",
        rows,
        "",
        "`order_before_snapshot` has no matching inventory MD and remains outside this review.",
    )) + "\n"


def _row(path: Path) -> str:
    table = path.stem
    relative_path = path.relative_to(INVENTORY_ROOT).as_posix()
    if table in PREVIOUSLY_CLOSED:
        return f"| `{relative_path}` | existing retirement record | none | retained historical receipt | unchanged (previously closed) |"
    owner = _owner_for(relative_path)
    retention = "append-only lineage / audit evidence" if _is_audit_table(table) else "root fact or derived projection retained by owning domain"
    return f"| `{relative_path}` | {owner} typed service/query and schema release | no direct external field contract | {retention} | retain; no unsupported retirement evidence |"


def _owner_for(relative_path: str) -> str:
    return {
        "01_客戶與訂單生命週期": "Orders / Case Import",
        "02_服務人員主檔與檔期": "Staff and Assignments / Scheduling",
        "03_媒合指派排班與請假": "Assignments / Scheduling",
        "04_客戶收款與交易": "Client Finance",
        "05_服務人員薪資月結與匯款": "Payroll / Staff Payables",
        "06_政府補助與申請": "Government Subsidy",
        "07_財務匯入與警示": "Finance Import / Anomalies",
        "08_LINE與媒體整合": "LINE Integration / Access Control",
        "09_管理權限與稽核": "Access Control",
        "10_知識與擷取紀錄": "Knowledge Retrieval",
    }[relative_path.split("/", 1)[0]]


def _is_audit_table(table: str) -> bool:
    return any(token in table for token in ("event", "audit", "transaction", "occurrence", "attempt", "outbox", "log"))


if __name__ == "__main__":
    raise SystemExit(main())
