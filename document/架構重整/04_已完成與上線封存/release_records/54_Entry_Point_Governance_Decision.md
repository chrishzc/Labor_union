# 54. Entry Point Governance Decision

## Decision

- Decision date: 2026-08-09
- Decision maker: system business owner
- Related baseline: `01_規格基線/19_Global_Entry_Point_Governance.md`

API、UI、CLI entry 採逐項治理。router mount、page loader 或 CLI `__main__` 只證明可達，不能證明
仍有業務用途。每個 entry 必須在 review queue 有 status、業務情境、操作者與 canonical owner；
未審 entry 保持 `review_required`，不由 Agent 猜測為 active 或刪除。

## Retirement rule

- HTTP legacy entry 先固定 typed `410 Gone` 與 replacement，完成外部契約裁決後才可移除。
- UI page 先確認實際管理流程與替代導航，再移除 page source。
- CLI 先確認維運場景、權限與 replacement；沒有直接 caller 不構成刪除授權。
- 不是 API/UI/CLI 的零 caller module 仍依 caller graph、replacement evidence 與明確 retirement
  decision 退役。
