# 決策與退役執行記錄索引

依編號（時間序）記錄已核准的退役／修復決策與其驗收證據。每份文件開頭都有
`doc_type`／`declared_status`／`date`（如原文有明確標示）的 YAML frontmatter，
可供腳本快速篩選；文字內容才是唯一權威來源，frontmatter 只是索引輔助。

`doc_type` 意義：`decision-package`（已核准但可能尚未授權實作/移除）、
`receipt`（已完成並驗收的執行記錄）、`gap-package`（記錄現況與目標的落差，
非退役性質）、`contract`（單一場景的正式規格補充）。

本索引以 active、blocked、awaiting execution／release 與 current recovery 文件為主。不再 active
的 completed Work Package、已有 successor 的 superseded 舊規格與 closed release／receipt，通過
`../04_已完成與上線封存/README.md` 的 archive gate 後移出本表，僅保留必要的一行 archive
pointer。2026-08-11 已完成多輪保守封存；歷史文件以
[`archive_manifest.json`](../04_已完成與上線封存/archive_manifest.json) 精準查找，不再列入日常索引。

| 檔案 | doc_type | declared_status | 一句話摘要 |
|---|---|---|---|
| [58_未實作_未落地_未上線規格總表.md](58_未實作_未落地_未上線規格總表.md) | gap-register | `completed` | 已確認正式規格的未實作、已實作未落地、已驗證未上線與刻意不自動化之集中盤點。 |
| [WP72（封存）](../04_已完成與上線封存/work_packages/72_Matching_Preferences_and_Staff_Unavailability_Work_Package.md) | work-package | `completed` | 自訂月嫂偏好、匯入下廚條款、長假／暫停接案及 Matching／Calendar 同源整合已完成；residual plan 另有胎數裁決。 |
| [73_ADR001_HCM_Web_Upload_and_Historical_Import_Lanes_Work_Package.md](73_ADR001_HCM_Web_Upload_and_Historical_Import_Lanes_Work_Package.md) | work-package | `in-progress` | HCM 收斂為 authenticated Web upload；Client／Staff BeClass current entry 改走 LIFF typed API，scripts 保留為 historical-only。 |
| [WP74（封存）](../04_已完成與上線封存/work_packages/74_Developer_Local_Database_Update_and_Rebuild_Work_Package.md) | work-package | `completed` | 開發者本機 DB 更新工具與兩方向真實 MySQL 驗收完成；來源 DB 維持唯讀，operator update 仍需明確確認。 |
| [WP75（封存）](../04_已完成與上線封存/work_packages/75_Startup_Launcher_Convergence_and_Retirement_Work_Package.md) | work-package | `completed` | Windows canonical launcher 實跑與 PID／port cleanup 通過；LINE 缺個人憑證時安全略過，長期入口規則由開發者導覽承接。 |
| [WP76（封存）](../04_已完成與上線封存/work_packages/76_Migration_Release_Integrity_and_Local_Startup_Readiness_Repair_Work_Package.md) | work-package | `completed` | full-chain、part 61／153、disposable engine 與無 Git 目標主機 readiness／API／UI 驗收均已通過。 |
| [77_Staff_Historical_Adoption_and_HCM_Review_Work_Package.md](77_Staff_Historical_Adoption_and_HCM_Review_Work_Package.md) | work-package | `in-progress` | Staff 歷史來源依較新報名時間可覆寫姓名、銀行帳戶與關聯集合；HCM／Client BeClass獨立匯入，缺對方投影時建立 partial formal case 並標記 warning。 |
| [WP78（封存）](../04_已完成與上線封存/work_packages/78_Knowledge_Partial_Local_Database_Recovery_Work_Package.md) | work-package | `completed` | 安全恢復舊本機 DB 的 Knowledge 148/163 partial statement boundary，驗收與備份復原通過。 |
| [WP79（封存）](../04_已完成與上線封存/work_packages/79_LINE_Runtime_Release_Catalog_Recovery_Work_Package.md) | work-package | `completed` | candidate 實證 179 需在 186 後；Docker MySQL preserve-data 驗證與同名替換已完成。 |
| [ARCH-20260815-086 WP80 Historical Order Adoption](../04_已完成與上線封存/work_packages/80_Historical_Order_Adoption_Work_Package_20260815_closeout.md) | work-package | `completed` | archive pointer；保留舊 archive 副本，WP89 Web transition 與 WP92 最新採納語意由 successor 承接。 |
| [WP81（封存）](../04_已完成與上線封存/work_packages/81_LINE_Rich_Menu_Empty_Configuration_Recovery_Work_Package.md) | work-package | `completed` | 精確 `{}` Rich Menu DB revision 受控修復，並退役檔案設定旁路的 legacy CLI 驗收通過。 |
| [82_LINE_Service_Registration_LIFF_and_Docker_Client_Work_Package.md](82_LINE_Service_Registration_LIFF_and_Docker_Client_Work_Package.md) | work-package | `in-progress` | 服務登記改為客戶登記 LIFF URI，Docker MySQL client；exact write set 已補齊。 |
| [ARCH-20260815-088 WP83 Data Import Center](../04_已完成與上線封存/work_packages/83_Data_Import_Center_and_Web_Apply_Work_Package_20260815_closeout.md) | work-package | `completed` | archive pointer；保留舊 archive 副本，LIFF typed writer 與 temporary Web-entry retirement 仍由 successor gate 承接。 |
| [ARCH-20260815-075 WP84 Legacy Knowledge recovery](../04_已完成與上線封存/work_packages/84_Legacy_Knowledge_Empty_Schema_Recovery_Work_Package.md) | work-package | `completed` | archive pointer；candidate rebuild、同名 developer-local replacement 與 current-release 驗收均已完成。 |
| [ARCH-20260815-078 WP85 Client Refund Snapshot upgrade](../04_已完成與上線封存/work_packages/85_Client_Refund_Recipient_Snapshot_Local_Upgrade_Work_Package.md) | work-package | `completed` | archive pointer；successor releases 189/190、engine verification 與 developer-local replacement 已完成。 |
| [ARCH-20260815-080 WP86 API-only runtime readiness](../04_已完成與上線封存/work_packages/86_API_Only_DB_Runtime_Local_Readiness_Work_Package.md) | work-package | `completed` | archive pointer；API-only DB boundary、credential fallback 與 authorized launcher smoke 均已完成。 |
| [ARCH-20260815-082 WP87 runtime supervision](../04_已完成與上線封存/work_packages/87_Cloud_Ready_Runtime_Supervision_Work_Package.md) | work-package | `completed` | archive pointer；runtime security focused verification 與 authorized launcher smoke 均已完成。 |
| [ARCH-20260815-076 WP88 LINE Staff Self-Service merge repair](../04_已完成與上線封存/work_packages/88_LINE_Staff_Self_Service_Merge_Repair_Work_Package.md) | work-package | `completed` | archive pointer；release chain、candidate migration、service smoke 與 focused runtime evidence 已完成。 |
| [ARCH-20260815-087 WP89 Historical Order Web Transition](../04_已完成與上線封存/work_packages/89_Historical_Order_Status_and_Caregiver_Evidence_Web_Transition_Work_Package.md) | work-package | `completed` | archive pointer；WP92 持續承接已取代的 historical-adoption 語意。 |
| [90_Import_Review_External_Confirmation_Work_Package.md](90_Import_Review_External_Confirmation_Work_Package.md) | work-package | `approved` | 匯入異常採外部確認、去敏狀態追蹤與受驗證重新提交。 |
| [ARCH-20260815-073 WP91 Staff Retirement](../04_已完成與上線封存/work_packages/91_Staff_Retirement_Work_Package.md) | work-package | `completed` | archive pointer；developer-local acceptance、fresh bootstrap 與 preserve-data verification 均已完成。 |
| [ARCH-20260815-084 WP92 Import Warning Tracking](../04_已完成與上線封存/work_packages/92_Import_Warning_Tracking_and_Lane_Recovery_Work_Package.md) | work-package | `completed` | archive pointer；part 195 engine and authorized developer-local acceptance completed. |
| [PROV-20260815-schema-baseline-drift-recovery.md](PROV-20260815-schema-baseline-drift-recovery.md) | work-package | `superseded` | 低階 CLI 未載入 canonical release chain 的 false-positive；完整 snapshot 證實六個 artifacts 均為 `exact`。 |
| [WP93（封存）](../04_已完成與上線封存/work_packages/93_Schema_Assembly_and_Migration_Archive_Retirement_Work_Package.md) | work-package | `completed` | 唯一 schema assembly、view descriptor、candidate upgrade、local launcher 與九頁 UI 收尾驗收完成。 |
| [ARCH-20260815-089 WP94 Import Warning Tracking](../04_已完成與上線封存/work_packages/94_Import_Warning_Query_and_Manual_Tracking_Work_Package.md) | work-package | `completed` | archive pointer；WP90/WP92 的 typed Query 與人工狀態追蹤已驗收，WarningReferral 仍待 owner-specific successor。 |

所有 completed／superseded 歷史文件統一由
[`archive_manifest.json`](../04_已完成與上線封存/archive_manifest.json) 依 archive identity 查找；
本 active 索引不再逐筆重列封存內容。

> `29_` 原本被三份文件重複使用（無明確時間序，只能靠檔名區分），2026-08-07
> 已重新編號為 `32`～`34`（依原檔名字母序指派，不代表已還原真實時間序）。
> 之後新增文件請直接使用下一個未用過的整數（目前最大為 `94`，下一個為 `95`）。

> 注意：本表不是只保留字面上的 `in-progress`。仍需實作、等待 release／migration、保留人工操作
> 邊界、缺少 completion evidence，或仍約束現行操作的文件都屬 active working set。作為目前缺口
> SSOT 的 `58` 依封存規則保留；其餘完成文件只在本索引保留 archive pointer。

2026-08-12 人工指示暫緩 Durable Job Worker 主機 supervision；原 `41` 已降級並移至
[`document/功能開發計畫/Durable_Job_Worker_Supervision_延後開發計畫.md`](../../功能開發計畫/Durable_Job_Worker_Supervision_延後開發計畫.md)，
不再構成 active deployment contract 或主機操作授權。

2026-08-12 人工選定 Scheduling 請假方案三；`60` ownership 裁決已封存，後續功能範圍移至
[`document/功能開發計畫/Scheduling_月嫂請假申請待辦與管理端處理開發計畫.md`](../../功能開發計畫/Scheduling_月嫂請假申請待辦與管理端處理開發計畫.md)。
LINE 申請只建立待辦 evidence，正式排班仍由既有 leave-substitution Preview／Apply 擁有；目前尚未授權實作。
