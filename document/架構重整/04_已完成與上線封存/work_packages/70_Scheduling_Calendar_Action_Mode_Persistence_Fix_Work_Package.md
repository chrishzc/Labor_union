---
doc_type: work-package
declared_status: completed
date: 2026-08-12
owner: Scheduling
priority: P1
domain: Scheduling
subsystem: Staff Monthly Calendar UI
---

# 70 Scheduling Calendar Action Mode Persistence Fix

## Business scenario

排班人員在服務人員月曆直接選取年份或月份後，仍應維持目前的工作意圖；若尚未選擇操作模式，應預設進入「出勤天數精算」，不得因 Streamlit widget state 重建而改為「訂單匹配」。

## Scope

- 將 `calendar_action_mode` 的有效值限定為「訂單匹配」與「出勤天數精算」。
- 缺少或無效 state 時初始化為「出勤天數精算」。
- 月份切換不得覆寫既有的有效操作模式。

## Out of scope

- 不改變訂單候選查詢、請假／代班 Preview／Apply 或行事曆服務日計算。
- 不修改已封存 WP67、WP69 的內容或 archive identity。

## Acceptance

- 直接修改年月後，既有「出勤天數精算」模式維持不變。
- 新 session 進入月曆時預設為「出勤天數精算」。
- 選擇「訂單匹配」後再切換月份，模式仍維持「訂單匹配」。

## Required evidence

- UI 操作驗收：年份／月份直接切換與兩種模式保留。
- 回歸範圍：服務人員月曆操作模式初始化與現有請假／代班 UI 流程。

## 2026-08-12 完成與 UI 驗收

- 修正：僅在 `calendar_action_mode` 缺少或無效時初始化為「出勤天數精算」；月份切換不寫入此 state。
- Chrome 新 session：服務人員月曆初始模式為「出勤天數精算」。
- Chrome 情境一：2026 年 8 月直接改選 7 月，模式仍為「出勤天數精算」。
- Chrome 情境二：手動改選「訂單匹配」後直接改選 6 月，模式仍為「訂單匹配」。
- release identity：本機 Streamlit `127.0.0.1:8502` 受控 UI 驗收；無 production deployment release。
- current successor：`document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md`；本文件不再作為 current 行為授權。
- restore triggers：月曆操作模式在 rerun 或年月切換後被覆寫、或 Streamlit session-state 初始化回歸。
