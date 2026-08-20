---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase3b2-leave-request-date-coverage-decision-gap
date: 2026-08-17
owner: Scheduling / Staff Leave Intake
domain: Scheduling
---

# Leave request日期／案件覆蓋關係裁決缺口

## Current authority

Staff leave request root fact包含staff、leave start/end與reason，但沒有canonical `case_no`。正式已知不變量只足以
驗證request為accepted、expected version一致、original outcome staff相同，且一筆request只能連結一筆
Leave/Substitution receipt。

## Decision required

是否要求所有substitution/extension outcome日期落在request interval，以及一份request能否涵蓋多個case，尚未
裁決。任何predicate都會改變Domain rejection semantics，不得由route、workflow或React自行推導。

Phase3B2在本缺口未裁決時只執行已知state/version/staff/unique-link驗證；不得把request反向標記為原先屬於
某case。若未來採date coverage，須另立exact Domain/public-contract successor與controlled scenarios。

## DB gate

Scope `BLOCKED`（business invariant未裁決）；Change inventory與其餘gates `NOT_RUN`；
`DB_CHANGE_NOT_READY`。
