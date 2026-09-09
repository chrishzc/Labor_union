# 15B — 2026-09-09 Multi-Caregiver Admin UI Closeout 裁決

## 1. 文件狀態

- 狀態：`approved-current-index-amendment`
- 生效日期：2026-09-09
- 補充文件：`15_正式規格索引與裁決總表.md`
- 前一 amendment：`15A_20260909_SourceReview_Closeout與ControlledFile正式化裁決.md`

本文件只更新 `document/管理端UI/` 多月嫂 UX 文件的 current Authority 與 lifecycle；不重寫 `15` 保存的其他歷史裁決。

## 2. Current formal baseline 增補

自本裁決起，正式規格基線另納入：

- `31_MultiCaregiver_Admin_UI正式規格.md`

`31` 單一擁有多月嫂管理端的 UI composition／interaction contract；正式業務語意仍由 `02_Assignments_Scheduling_Domain.md` 及 Orders／Payroll／Client Finance owning specs 擁有。

## 3. Source closeout

下列四份文件退出 current working tree，由 Git history 保存：

- `document/管理端UI/多月嫂排班UX改善討論紀錄.md`
- `document/管理端UI/多月嫂排班UX目標指南.md`
- `document/管理端UI/多月嫂排班UX驗收矩陣.md`
- `document/管理端UI/多月嫂排班與行事曆規格.md`

理由：

1. 討論紀錄本身明示「不是最終實作規格」，其已確認 UI 決策已由後續 goal／acceptance、current code 與本次 `31` 收斂。
2. goal guide 仍標 draft，但其 `MCSUX-AC-001`～`008` 已由完成驗收矩陣逐項對到 live implementation／tests 並記錄通過；它不應繼續作為與 formal baseline 並列的 current Authority。
3. 完成驗收矩陣屬 point-in-time closeout evidence。current regression 由正式 spec、live tests 與必要 current receipt 擁有；矩陣退出 working tree 不取消歷史 evidence。
4. `多月嫂排班與行事曆規格.md` 自稱「現行實作契約」，會與 formal `02` 形成 competing Authority；其仍有效的 UI-specific 條款已搬入 `31`，Domain 語意由 `02` 擁有。

## 4. 不受本裁決影響的 `管理端UI` 資產

本裁決不自動刪除二進位模板／附件。`表格需求模板/*.xlsx` 與 `資料庫原始資料瀏覽_頁面欄位開放權限建議表.xlsx` 必須另依內容、current consumer 與 formal successor 判斷；不能只因目錄清理而刪除。

## 5. Authority order

若 Git history 中上述四份來源文件與 current `31`／`02` 衝突，以日期較新的人工裁決、`31`、`02` 及其他 owning formal spec 為準。不得從歷史來源恢復舊 page、formula、writer 或 workflow Authority。
