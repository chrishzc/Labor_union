---
doc_type: work-package
declared_status: in-progress
date: 2026-08-13
owner: Orders / Scheduling / Payroll
priority: P0
---

# 80 Historical Order Adoption Work Package

## 1. 恢復 active 的原因

本文件於 2026-08-13 曾被誤封存。現有 parser、Preview、successor schema part 193 與 release metadata
不等於完成：242-row 實際形狀只取得 Preview（111 adopted、131 unmatched、8 review），尚無完整
disposable MySQL Apply、exact replay、rollback、API／資料匯入中心 UI 與 Chrome receipt evidence。
因此 archive identity `ARCH-20260813-070` 僅保留歷史追溯，本文件恢復為唯一 active execution
record；正式業務語意仍以 `01_Orders_Domain.md` 與 `15_正式規格索引與裁決總表.md` 為 SSOT。

## 2. 已核准的行為

- 只以 `case_no + client_name` 精確匹配既有 Order；未匹配零寫入、零警示。
- `0／1／2` 採納歷史 asserted status；空白／未知值 durable review。
- 開始與結束日期可為 `NULL`；Excel 1900／1904 serial 正確轉換。
- 單月嫂有唯一個人區間才建立正式 assignment；多月嫂缺個人區間只存配對 evidence。
- 既有 direct-SQL `scripts/import_historical_orders.py` 保持 retired；目前 CLI 是
  `scripts.imports.adopt_historical_orders`，預設 Preview、明確 Apply 才可寫入。

## 3. 剩餘 scope

1. 建立 typed API／client，使資料匯入中心卡片不呼叫 CLI。
2. 以 disposable MySQL 驗證 Apply、exact replay、same-key conflict、transaction rollback與
   case／status／assignment evidence。
3. 更新 UI receipt 與異常導向，並以 Chrome 對實際 API／Streamlit 驗收。

第 1、3 項的 Web composition 由 `86_Historical_Order_Status_and_Caregiver_Evidence_Web_Transition_Work_Package.md`
執行；本包保留 Orders Domain、schema release、disposable MySQL 與歷史採納語意的唯一 owner。

## 4. Completion gate

只在本文件第 3 節、相關 release gate、focused tests、disposable MySQL及 Chrome evidence 都
完成後，才可重新封存。不得以 parser 或 Preview 成功代替 Apply evidence。
