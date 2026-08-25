---
doc_type: gap-package
declared_status: superseded
identity: PROV-20260817-react-admin-phase3b1-staff-remaining-controls-gap
date: 2026-08-17
owner: Staff / Scheduling
domain: Staff Preferences / Availability
---

# Phase 3B1 Staff剩餘控制缺口

## Business scenario

Phase3B1只安全啟用staff profile偏好、long leave／pause建立與cancel、retirement／reactivation。既有backend
另有availability `end_pause`與preference definition administration，但目前React槽、operator、權限及
Preview→Apply契約未被本包核准。

## Required successor decisions

1. `end_pause`的操作者、effective time、fresh version、與active assignment/waiting/buffer mutex規則；
2. preference definition create/update/retire是否屬Account／Staff設定，以及所有enabled users或特定維運入口；
3. 各自stable control ID、typed errors、receipt、replay、browser controlled data與rollback。

在successor核准前，`staff.availability.end-pause`及definition mutations必須native-disabled/unavailable；不得
藉Phase3B1 profile flow測試宣稱整個route family完成。

2026-08-22已建立最小、仍待exact核准的
`PROV-20260822-react-admin-phase3b1-staff-end-pause-successor-work-package.md`；它只處理結束open-ended
`paused_service`，不包含definition administration、Staff master、PII、銀行、證照或附件。核准前control仍維持
native disabled。

## DB gate

Scope `BLOCKED`（owner/public contract未裁決）；Change inventory與其餘gates `NOT_RUN`；
`DB_CHANGE_NOT_READY`。
