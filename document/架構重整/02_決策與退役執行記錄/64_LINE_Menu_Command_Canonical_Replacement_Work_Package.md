---
doc_type: work-package
declared_status: completed
date: 2026-08-12
owner: LINE Integration
---

# LINE Menu Command Canonical Replacement

使用者確認保留 union menu 與 `esc`。`LineMenuCommandApplication` 使用 canonical
`line_identity_bindings`：只有 bound admin 可要求 `union_staff_menu`；任何 LINE user 可用 `esc`
要求 `default_menu`。每個命令以 inbox event ID 建立 outbox idempotency identity，並附 audit intent。

此包不切換 runtime default、不刪除 legacy route、不變更 Rich Menu publication。focused tests 證明
role guard、payload、idempotency 與既有 binding worker 共 `26 passed`。
