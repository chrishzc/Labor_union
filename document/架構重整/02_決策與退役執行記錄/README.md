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
| [WP73（封存）](../04_已完成與上線封存/work_packages/73_ADR001_HCM_Web_Upload_and_Historical_Import_Lanes_Work_Package.md) | work-package | `completed／archived` | HCM Web upload 與歷史過渡入口已完成；current 語意由正式規格 15／17 承接。 |
| [WP74（封存）](../04_已完成與上線封存/work_packages/74_Developer_Local_Database_Update_and_Rebuild_Work_Package.md) | work-package | `completed` | 開發者本機 DB 更新工具與兩方向真實 MySQL 驗收完成；來源 DB 維持唯讀，operator update 仍需明確確認。 |
| [WP75（封存）](../04_已完成與上線封存/work_packages/75_Startup_Launcher_Convergence_and_Retirement_Work_Package.md) | work-package | `completed` | Windows canonical launcher 實跑與 PID／port cleanup 通過；LINE 缺個人憑證時安全略過，長期入口規則由開發者導覽承接。 |
| [WP76（封存）](../04_已完成與上線封存/work_packages/76_Migration_Release_Integrity_and_Local_Startup_Readiness_Repair_Work_Package.md) | work-package | `completed` | full-chain、part 61／153、disposable engine 與無 Git 目標主機 readiness／API／UI 驗收均已通過。 |
| [WP77（封存）](../04_已完成與上線封存/work_packages/77_Staff_Historical_Adoption_and_HCM_Review_Work_Package.md) | work-package | `completed／archived` | Staff historical adoption 與 HCM intake 邊界已完成；current 語意由正式規格 15／17／24 承接。 |
| [78_Knowledge_Partial_Local_Database_Recovery_Work_Package.md](78_Knowledge_Partial_Local_Database_Recovery_Work_Package.md) | work-package | `blocked` | 程式與 focused regression 已完成；仍缺安全目標 DB 的 read-only plan、engine 與 developer acceptance，故撤回封存。 |
| [WP79（封存）](../04_已完成與上線封存/work_packages/79_LINE_Runtime_Release_Catalog_Recovery_Work_Package.md) | work-package | `completed` | candidate 實證 179 需在 186 後；Docker MySQL preserve-data 驗證與同名替換已完成。 |
| [WP80 completion（封存）](../04_已完成與上線封存/work_packages/80_Historical_Order_Adoption_Work_Package_Completed_20260814.md) | work-package | `completed／archived` | Historical Order adoption 已完成；同號舊 Preview-only 版另保留於 archive lineage。 |
| [WP81（封存）](../04_已完成與上線封存/work_packages/81_LINE_Rich_Menu_Empty_Configuration_Recovery_Work_Package.md) | work-package | `completed` | 精確 `{}` Rich Menu DB revision 受控修復，並退役檔案設定旁路的 legacy CLI 驗收通過。 |
| [82_LINE_Service_Registration_LIFF_and_Docker_Client_Work_Package.md](82_LINE_Service_Registration_LIFF_and_Docker_Client_Work_Package.md) | work-package | `in-progress` | 服務登記改為客戶登記 LIFF URI，並提供每位開發者可配置的 Docker MySQL client。 |
| [WP83（封存）](../04_已完成與上線封存/work_packages/83_Data_Import_Center_and_Web_Apply_Work_Package.md) | work-package | `completed／archived` | 五個 typed lane 已完成；temporary-card removal trigger 留在正式規格 15／17。 |
| [84_Legacy_Knowledge_Empty_Schema_Recovery_Work_Package.md](84_Legacy_Knowledge_Empty_Schema_Recovery_Work_Package.md) | work-package | `in-progress` | exact 且九張 owned tables 全空的歷史 Knowledge schema，只在隔離 candidate 重建為 canonical 148／163。 |
| [WP85（封存）](../04_已完成與上線封存/work_packages/85_Historical_Order_Status_and_Caregiver_Evidence_Web_Transition_Work_Package.md) | work-package | `completed／archived` | Orders historical typed Web card 已完成；current 規則由 Orders 正式規格承接。 |
| [86_Import_Review_External_Confirmation_Work_Package.md](86_Import_Review_External_Confirmation_Work_Package.md) | work-package | `approved` | 各類匯入異常統一採公會外部確認、去敏狀態追蹤與重新提交；警示中心不直接改寫來源資料。 |
| [87_Staff_Retirement_Work_Package.md](87_Staff_Retirement_Work_Package.md) | work-package | `proposed` | 保留退役月嫂所有歷史資料，但停止加入新的 Matching 等後續流程；細節尚未裁決。 |
| [88_Import_Warning_Tracking_and_Lane_Recovery_Work_Package.md](88_Import_Warning_Tracking_and_Lane_Recovery_Work_Package.md) | work-package | `in-progress` | 第一階段正實作欄位級匯入警示與追蹤基礎；後續仍包含各 lane recovery。 |
| [89_Schema_Assembly_and_Migration_Archive_Retirement_Work_Package.md](89_Schema_Assembly_and_Migration_Archive_Retirement_Work_Package.md) | work-package | `approved` | 先建立 WP80 pre-190 → part 190 的可驗證 release chain；不授權改寫已發布 artifact 或刪除 migration。 |

所有 completed／superseded 歷史文件統一由
[`archive_manifest.json`](../04_已完成與上線封存/archive_manifest.json) 依 archive identity 查找；
本 active 索引不再逐筆重列封存內容。

> `29_` 原本被三份文件重複使用（無明確時間序，只能靠檔名區分），2026-08-07
> 已重新編號為 `32`～`34`（依原檔名字母序指派，不代表已還原真實時間序）。
> 之後新增文件請直接使用下一個未用過的整數（目前最大為 `88`，下一個為 `89`）。

> 注意：本表不是只保留字面上的 `in-progress`。仍需實作、等待 release／migration、保留人工操作
> 邊界、缺少 completion evidence，或仍約束現行操作的文件都屬 active working set。作為目前缺口
> SSOT 的 `58` 依封存規則保留；其餘完成文件只在本索引保留 archive pointer。

2026-08-12 人工指示暫緩 Durable Job Worker 主機 supervision；原 `41` 已降級並移至
[`document/功能開發計畫/Durable_Job_Worker_Supervision_延後開發計畫.md`](../../功能開發計畫/Durable_Job_Worker_Supervision_延後開發計畫.md)，
不再構成 active deployment contract 或主機操作授權。

2026-08-12 人工選定 Scheduling 請假方案三；`60` ownership 裁決已封存，後續功能範圍移至
[`document/功能開發計畫/Scheduling_月嫂請假申請待辦與管理端處理開發計畫.md`](../../功能開發計畫/Scheduling_月嫂請假申請待辦與管理端處理開發計畫.md)。
LINE 申請只建立待辦 evidence，正式排班仍由既有 leave-substitution Preview／Apply 擁有；目前尚未授權實作。
