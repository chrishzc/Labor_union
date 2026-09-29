# 七天緩衝提醒：本機保留資料升級

Authority：2026-09-29 使用者明確要求候選階段可協調、正式排班不得有實際服務重疊，並授權程式與 migration 一併修正。只驗證本機合成資料，不操作另一台主機。

Owner：Scheduling；業務語意依 `../01_規格基線/02_Assignments_Scheduling_Domain.md`。Global Migration 只擁有 release、descriptor、備份／還原與驗證流程。

## Write set 與資料效果

- 候選 Query／聯繫池與 React 顯示：保留衝突候選，顯示需協調；不建立正式排班。
- 每週服務 Preview：核對約定服務天數，已確認日期優先於偏好休假，不寫入。
- Scheduling domain／repository／writer：buffer 不參與 hard occupancy；實際服務仍 fresh-lock 驗證，並保留資料庫唯一限制。
- `1047_scheduling_buffer_advisory.sql` 與對應 manifest／完整 descriptor／fresh assembly／validation release／migration classifier：純 schema 變更，無 seed、backfill、DELETE 或資料重建。
- 正式 owner spec、相關 `.arch-map` leaf 及直接回歸測試同步更新。

`scheduling_buffer_days` 的人員／日期／active index 改為非唯一；assignment／日期唯一鍵不變。effective occupancy 主鍵增加既有 type，讓歷史 buffer projection 與新的 actual interval 可共存；同人同日 `assignment_interval` 仍唯一。新 writer 的 buffer facts 僅寫在 buffer 表，歷史 rows 全保留。

## Replay、rollback 與 unresolved policy

兩個 index 均為 exact predecessor 才分類 absent、均為 exact successor 才 exact；單一完成為 partial，未知欄位／索引／FK／CHECK 為 drift。partial／drift 須停止，不盲目重跑 DDL。

升級前依既有本機 updater 取得 read-only plan 與 source backup。升級保留每個 business row、assignment identity、服務日、buffer history、FK 與 CHECK。候選驗證失敗時保留 source，不切換；尚未切換可丟棄候選。出現重疊 buffer facts 後不得直接恢復舊 unique index，須走另案保留資料處理。

部署主機需程式與此 schema release 同版，依 `scripts/launchers/update_local_database.bat` 的既有保留資料流程操作。此任務不包含部署、遠端 Apply、production 或 entry switch。

## Acceptance

Focused tests、實際瀏覽器、fresh disposable MySQL、前版 source dump → 新 candidate restore → release Apply → all-row preservation，並證明 buffer 重疊可共存、實際服務重複仍拒絕。測試資料僅存於此次新建 `lu_test_buffer_*`；證據存於 `scratch/contract-preview/`，不得當作另一主機的 backup。

Reusable qualification：`validation/receipts/PROV-SCHEDULING-BUFFER-ADVISORY-local-additive-qualification-20260929-lf.json`。由實際 MySQL evidence collector 與 strict builder 產生，綁定 Git 的 LF artifact bytes；其他主機仍須取得自己的升級前備份與檢查結果。

原 `PROV-SCHEDULING-BUFFER-ADVISORY-local-additive-qualification-20260929.json` 保留為初次本機驗證的不可變紀錄。發布前 descriptor／assembly 行尾校正為 Git LF 並更新校驗碼後，以新隔離 candidate 重新升級及驗證，current updater 使用上述 LF 資格回條；原回條不再代表 current artifact identity。
