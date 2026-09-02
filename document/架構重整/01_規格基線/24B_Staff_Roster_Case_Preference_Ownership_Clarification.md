# Staff Roster Case Preference Ownership Clarification

## 1. 文件定位

- Issue：`#104 [月嫂接案偏好] 定義 canonical 資訊架構與 ownership 邊界`
- Parent spec：`24_Staff_Matching_Preferences與不可服務期間正式規格.md`
- Read-model supplement：`24A_Staff_Roster_Case_Preference_Read_Model正式補充契約.md`
- 本文件只補正 #104 的 topic classification、現存六組 `[其它]` ownership 與 read/write 邊界；不新增 runtime、schema、migration、UI 或 production data change。

## 2. Topic classification

### 2.1 屬於 Staff matching preference owner 的可寫偏好

Parent spec 的 `Scheduling / Staff Matching Profile` 是偏好定義與月嫂偏好值的 root owner。第一版正式內建：

| topic | canonical owner | data shape | write owner |
|---|---|---|---|
| 可承接服務天數 | Scheduling / Staff Matching Profile | `integer_range` | `StaffPreferenceValueWorkflow` |
| 可承接每日服務時數 | Scheduling / Staff Matching Profile | `integer_set` | `StaffPreferenceValueWorkflow` |

這兩個 preference definition 與下列 BeClass relation facts 是不同 root；不能因名冊同時展示就合併 storage 或共用 write API。

### 2.2 屬於 roster case-preference read projection 的既有 Staff facts

`24A` 定義的 `StaffCasePreferenceSummary` 是 bounded read projection，不是新 root owner：

| topic | canonical values owner | shape in read projection | #104 write boundary |
|---|---|---|---|
| 希望服務地區 | `staff_regions` | `PreferenceTopicSummary` | read-only；不得由 roster 直接寫 relation |
| 服務時段 | `staff_time_slots` | `PreferenceTopicSummary` | read-only；不得由 roster 直接寫 relation |
| 如何排休 | `staff_weekly_rest` | `PreferenceTopicSummary` | read-only；不得由 roster 直接寫 relation |
| 通常接幾胞胎 | `staff_baby_types` | `PreferenceTopicSummary` | read-only；不得由 roster 直接寫 relation |
| 特殊節日可接案 | `staff_holiday_availability` | `PreferenceTopicSummary` | read-only；不得由 roster 直接寫 relation |
| 交通方式 | `staff_transportation` | `PreferenceTopicSummary` | read-only；不得由 roster 直接寫 relation |

Case Import 只負責 historical workbook normalization/adoption，不是 roster query owner，也不是 preference editing owner。

### 2.3 料理能力是獨立 matching capability root

`staff_cooking_skills` 維持「料理能力」母題 ownership。Parent spec 在案件需要下廚時由 Matching 消費此 root；它不因 #104 被併入 `StaffCasePreferenceSummary` v1，也不得拿來當交通方式 fallback。

是否未來要把料理能力加入 roster case-preference read model，必須另有明確需求與契約；#104 不把這個可能性升格成 UI / storage requirement。

### 2.4 明確不是接案偏好

下列資料不因已有 canonical storage 或可被 Staff 查詢就成為接案偏好：

- `education`
- `emergency_contact_name` / `emergency_contact_phone`
- `admin_notes`
- `has_massage_cert`
- 一般資格證明 `staff_certifications`
- 身分證明、銀行資料、IP、credential、password、token、session secret、encryption key
- raw workbook row / raw JSON / source fingerprint / idempotency key
- BeClass `項次` / `查詢序號`；兩者不保存

## 3. 現存六組 `[其它]` 的母題 ownership

現行 `staff_historical_workbook.py` 的 relation mapping 只有以下六組 `[其它]` source；每一組固定留在自己的母題：

| source column | 母題 / relation | ownership rule |
|---|---|---|
| `[其它]` | 料理能力 / `staff_cooking_skills` | 只屬料理能力；不得借給交通或其他 topic |
| `[其它].1` | 希望服務地區 / `staff_regions` | 只屬服務地區 |
| `[其它].2` | 服務時段 / `staff_time_slots` | 只屬服務時段 |
| `[其它].3` | 如何排休 / `staff_weekly_rest` | 只屬排休 |
| `[其它].4` | 通常接幾胞胎 / `staff_baby_types` | 只屬胎數 |
| `[其它].5` | 特殊節日可接案 / `staff_holiday_availability` | 只屬節日意願 |

禁止建立 generic `other_note`，也禁止跨母題 fallback。

## 4. Transportation other 的精確邊界

現行 importer 對 `staff_transportation` 的 other source 是 `None`。因此：

- 交通方式**不是**現存六組 `[其它]` 的其中一組。
- `24A` 的 `transportation_other_detail` 是 read-model 的 logical placeholder / implementation gap，不代表目前已有 canonical persistence field。
- 在正式 source/persistence owner 補齊以前，transportation detail 只能是 `source_not_ready`。
- 不得把料理能力 `[其它]`、其他任一 `[其它].N`、空字串或推測值填入 transportation detail。
- 若未來要新增 transportation other persistence/write capability，必須另開 runtime scope，明確定義 owner、migration、validation、Preview/Apply、audit 與 regression；#104 不預先宣告其 storage implementation。

## 5. Read / write API boundary

### Read

- 基本名冊摘要維持既有 bounded `StaffSummary`。
- roster case-preference facts 依 `24A` 使用獨立 `StaffCasePreferenceSummary` read boundary。
- React 只能消費 Staff-owned typed response；不得自行 join relation tables 或重新解析 BeClass headers。

### Write

- #104 不新增 `POST` / `PUT` / `PATCH` route。
- Parent spec 已定義的自訂 matching preference values 仍由 `StaffPreferenceValueWorkflow` 擁有。
- BeClass adoption relation facts 不因被 roster read projection 展示而自動變成可寫 preferences。
- 任何 relation root 的後續編輯都必須回到該 root 正式 owner，另行定義 validation、Preview/Apply、version、audit 與 idempotency。

## 6. #104 acceptance mapping

- [x] 包含／排除主題：matching preferences、roster read facts、料理能力、個資／資格／敏感資料已分開列出。
- [x] canonical owner 與 shape：每個納入 read projection 的 topic 與兩個既有 writable matching preferences 均已明確。
- [x] read/write boundary：roster projection read-only；既有 matching preference write owner 不變；沒有新增 write route。
- [x] 六組 `[其它]`：`[其它]`、`[其它].1`～`[其它].5` 均固定在原母題，沒有 generic other。
- [x] unknown 不升格：transportation other 明確標記為尚無 source/persistence 的 gap，不宣告成現存 storage；料理能力是否納入未來 roster read model亦不預設。

## 7. Safety

本 clarification 只有文件變更；沒有 production DB mutation、migration/backfill、production re-import、deploy、cutover、runtime/API implementation 或 UI implementation。
