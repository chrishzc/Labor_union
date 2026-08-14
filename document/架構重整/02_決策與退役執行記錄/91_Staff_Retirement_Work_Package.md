---
doc_type: work-package
declared_status: proposed
date: 2026-08-14
owner: Staff / Matching / Scheduling
priority: P1
---

# 91 Staff 退役 Work Package

## 已確認 business scenario

月嫂停止參與公會後，必須保留其既有 Staff、BeClass、訂單、薪資與歷史配對資料；但不再加入新的
Matching 等後續系統流程。

## 範圍

- 建立 Staff 退役能力的正式代辦與後續裁決入口。
- 實作前必須明定 state machine、既有與未來指派的處理、Matching／Scheduling／LINE 等各 consumer 的
  排除邊界、typed command、交易／outbox、replay、migration 與驗收。

## 非範圍

- 本包目前不授權 schema、API、UI、資料 mutation、既有 Staff 狀態變更或任何排班取消。
- 不預先裁決退役原因、日期、未來已確認服務、再啟用或通知行為。
