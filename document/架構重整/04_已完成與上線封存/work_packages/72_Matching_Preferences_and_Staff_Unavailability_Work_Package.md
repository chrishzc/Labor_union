---
doc_type: work-package
declared_status: completed
date: 2026-08-13
owner: Scheduling Staff Matching Profile / Orders / Assignments / Matching / Case Import
scope: Custom staff matching preferences, numeric service-day and daily-hour preferences, canonical imported cooking requirement, staff long-leave and temporary-unavailability periods, Matching and Calendar integration
write_set: [document/架構重整/01_規格基線/01_Orders_Domain.md, document/架構重整/01_規格基線/02_Assignments_Scheduling_Domain.md, document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md, document/架構重整/01_規格基線/24_Staff_Matching_Preferences與不可服務期間正式規格.md, domains/scheduling/, domains/case_import/, subsystems/case_import/, subsystems/scheduling/, api/routes/, api/schemas/, api/dependencies/, ui/api_clients/, ui/pages/scheduling/, infrastructure/mysql/, db/schema_parts/, db/schema.sql, db/migration_releases/, tests/, validation/]
acceptance: Internal users can define numeric matching preferences, set caregiver ranges, import an unambiguous cooking requirement into Orders, manage unavailable periods, and observe one typed result across Matching and Calendar with replay/stale/rollback evidence.
out_of_scope: Production deployment, production-data migration, arbitrary executable filter formulas, half-day unavailability, automatic LINE delivery, and real-person LINE acceptance.
---

# 72 Matching Preferences and Staff Unavailability Work Package

完成證據：[WP72 completion receipt](../receipts/2026-08-13_wp72_matching_preferences_staff_availability_receipt.md) 與 [matching residual closeout receipt](../receipts/2026-08-13_matching_residual_closeout_receipt.md)。本包與 residual plan 均已完成 local Browser／regression 驗收；胎數如未來取得 canonical Orders 條款，只能是可取消的月嫂偏好，不能由自由文字推測或成為 hard eligibility。

## 1. 人工裁決與授權

2026-08-13 使用者裁決並授權：

1. 在 Case Import 邊界把明確的下廚需求轉成 Orders 正式條款。
2. 新增由公會人員輸入的月嫂偏好功能；偏好欄位名稱可自訂並可加入配對篩選。
3. 將既有月嫂每日服務時段可明確解析者轉成數字時數，之後由偏好功能維護。
4. 長假／暫停接案納入本計畫，建立正式 Work Package 並同時整合 Matching 與 Calendar。

本授權不包含 production schema apply、production data migration、deployment 或真人 LINE 驗收。

## 2. Business scenarios

- `MATCH-PREF-001`：建立「可承接服務天數」偏好，為月嫂設定整數 range，配對案件時依希望服務天數篩選。
- `MATCH-PREF-002`：既有時段明確轉成數字時數；無法解析者進人工補登，不猜值。
- `MATCH-PREF-003`：新增自訂欄位名稱並選擇支援的 Orders matching source，啟用後加入配對 filter。
- `MATCH-COOK-001`：BeClass 明確下廚需求在 Import Preview／Apply 成為 Orders root；歧義資料進 Review。
- `SCH-UNAVAILABLE-001`：公會人員建立長假／暫停接案；暫停可 open-ended，Calendar 顯示且 Matching 排除 exact overlap。
- `SCH-UNAVAILABLE-002`：取消不可服務期間保留歷史；重新 Query 後恢復候選。

## 3. 實作順序

1. Additive schema、Domain modules 與 deterministic migration candidate。
2. Staff Preference Definition／Value Query、Preview、Apply。
3. Staff Unavailability Query、Preview、Apply、Calendar projection。
4. Case Import cooking normalization 與 Orders term persistence。
5. Matching typed Query：五項內建 filter、自訂 filters、actual conflict／buffer-only 分類。
6. Streamlit typed clients 與 UI。
7. Module → Subsystem → Domain → Browser 驗收、receipt 與 archive gate。

## 4. Schema 與 migration 安全

- schema 僅 additive，經 `db/schema_parts/` 組裝至 `db/schema.sql` 並建立 versioned release metadata。
- preference definition identity 與 versions 穩定；display name 可改但歷史語意不可覆寫。
- Staff Matching Profile 由 Scheduling 擁有，不新增獨立 Staff Domain；Staff identity 仍引用 `staff.id`。
- legacy `staff_time_slots` 只產生 migration candidate；正式資料 migration 不在本包自動執行。
- `其他`、空白或非唯一數字時段固定列為 unresolved；不得以預設 8 小時補值。
- 不可服務期間與取消／恢復事件 append-only；不得刪除歷史。長假必須有結束日；暫停接案恢復時
  以 `resume_date - 1 day` 封閉 open-ended current interval。

## 5. Required tests

- pure validators／comparators／normalizers；
- API typed request／response／error；
- MySQL exact replay、different payload、stale、concurrent overlap、rollback；
- Matching actual occupancy、waiting service lock、buffer-only、unavailability、偏好缺值；
- Calendar current／cancelled unavailability；
- Import clean／ambiguous／review／replay；
- Browser：偏好管理、月嫂值、不可服務期間、五項篩選與 Calendar；不保存截圖或影片。

## 6. 完成與封存 gate

- 正式規格、schema、release metadata、API、typed UI、tests 與 receipt 可追溯。
- production code 不再使用 `staff_time_slots` 作每日時數 matching SSOT。
- Matching／Calendar 只消費同一不可服務期間 Query。
- 五項預設篩選與啟用的自訂篩選均可解釋且 fresh-check。
- focused、Domain、必要 Global regression 及 Browser checklist 全部通過。
- completion receipt 明示 production deployment／migration 與真人 LINE 為 `not-in-scope`。
