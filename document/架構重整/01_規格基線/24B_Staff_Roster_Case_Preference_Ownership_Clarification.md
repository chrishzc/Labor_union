# Staff Roster Case Preference Ownership Clarification

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Staff / Scheduling Ownership Boundary
- 單一負責範圍：界定「Staff Matching Profile 可寫偏好」、「名冊接案事實 read projection」、「料理能力」與「非接案偏好個資／資格」四類主題的 root ownership、六組 `[其它]` 歸屬與讀寫邊界。
- 關聯引用：見 [Staff Matching Preferences](24_Staff_Matching_Preferences與不可服務期間正式規格.md)、[Staff Roster Read Model](24A_Staff_Roster_Case_Preference_Read_Model正式補充契約.md)

## 2. Topic 分類與所有權矩陣

### 2.1 可寫偏好 vs. 只讀投影 vs. 獨立能力 root

| 分類 | 主題 | Canonical Owner | Read/Write 邊界 |
|---|---|---|---|
| 可寫偏好（Numeric） | 可承接服務天數（`integer_range`）、可承接每日服務時數（`integer_set`） | Scheduling / Staff Matching Profile | 由 `StaffPreferenceValueWorkflow` 讀寫（不與 relation facts 共用 storage 或 write API） |
| 接案事實投影（6 項） | 希望服務地區（`staff_regions`）、服務時段（`staff_time_slots`）、如何排休（`staff_weekly_rest`）、通常接幾胞胎（`staff_baby_types`）、特殊節日可接案（`staff_holiday_availability`）、交通方式（`staff_transportation`） | Staff relation facts | 名冊投影 `StaffCasePreferenceSummary` 只讀；修改須經各 root owner 的 Q/P/A |
| 獨立能力 root | 料理能力（`staff_cooking_skills`） | Staff capability root | 由 Matching 於案件需要下廚時消費；不併入 `StaffCasePreferenceSummary` 且不得借用給交通方式 |

Case Import 只負責 workbook normalization/adoption，不是 roster query 或 preference editing owner。

### 2.2 明確排除：非接案偏好資料

下列資料不得因已有 canonical storage 而歸為接案偏好：`education`、`emergency_contact_name`/`phone`、`admin_notes`、`has_massage_cert`、`staff_certifications`、身分證與銀行資料、IP／credential／token／secret、raw workbook／JSON／fingerprint／idempotency key，以及不保存的 BeClass `項次`／`查詢序號`。

## 3. 現存六組 `[其它]` 母題鎖定與交通方式邊界

| 來源欄 | 母題／Relation | Ownership 規則 |
|---|---|---|
| `[其它]` | 料理能力／`staff_cooking_skills` | 只屬料理能力，嚴禁借給交通或其他 topic |
| `[其它].1` | 希望服務地區／`staff_regions` | 只屬服務地區 |
| `[其它].2` | 服務時段／`staff_time_slots` | 只屬服務時段 |
| `[其它].3` | 如何排休／`staff_weekly_rest` | 只屬排休 |
| `[其它].4` | 通常接幾胞胎／`staff_baby_types` | 只屬胎數 |
| `[其它].5` | 特殊節日可接案／`staff_holiday_availability` | 只屬節日意願 |

現行 importer 對 `staff_transportation` 的 other source 為 `None`：

- `transportation_other_detail` 屬 read-model logical placeholder，在補齊專屬 persistence owner 前固定回 `source_not_ready`。
- 嚴禁把料理能力 `[其它]`、其他 `[其它].N`、空字串或推測值填入 transportation detail。

## 4. 驗收標準

1. Matching preferences、roster read projection、料理能力與個資／資格四類邊界清楚分離，不共用 write API。
2. `[其它]` 與 `[其它].1`～`[其它].5` 嚴格鎖定原母題，無 generic `other_note`。
3. 交通方式 `other_detail` 保持 `source_not_ready`，不與其他母題交叉回填。
