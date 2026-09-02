# Staff Roster Case Preference Read Model 正式補充契約

## 1. 文件定位

- Issue：`#104 [月嫂名冊] 建立接案偏好資訊架構與 UI owner`
- Parent spec：`24_Staff_Matching_Preferences與不可服務期間正式規格.md`
- Owner：`Staff roster read projection`；Matching / Scheduling 的 root ownership 仍以 Parent spec 為準。
- 本文件只定義月嫂名冊「接案偏好」的 canonical read model、response contract、UI owner 與 fallback 規則。
- 本文件不新增 production DB schema、不建立 write API、不 deploy、不執行 production re-import。

本補充契約的核心原則是：月嫂名冊不得從 Case Import workbook、relation tables 或前端 local mapping 臨時拼出偏好。UI 只能讀取 Staff domain 提供的 bounded typed read projection。

## 2. 現況邊界

### 2.1 既有 Staff roster summary

`subsystems/staff/summary_query.py` 的 `StaffSummary` 是名冊基本摘要，canonical fields 固定為：

- `id`
- `name`
- `phone`
- `education`

這個 DTO 保持 bounded，不直接加入接案偏好 relation fields。接案偏好使用本文件定義的獨立 read model，避免基本名冊摘要隨 BeClass 題目擴張。

### 2.2 BeClass 已採納 relation facts

目前 `subsystems/case_import/staff_historical_workbook.py` 已將下列母題正規化為 Staff relation facts：

| BeClass 母題 | canonical relation | 現行 `[其它]` source | 本契約 logical other owner |
|---|---|---|---|
| 希望服務地區 | `staff_regions` | `[其它].1` | `service_region_other_detail` |
| 服務時段 | `staff_time_slots` | `[其它].2` | `service_period_other_detail` |
| 如何排休 | `staff_weekly_rest` | `[其它].3` | `rest_schedule_other_detail` |
| 通常接幾胞胎 | `staff_baby_types` | `[其它].4` | `baby_count_other_detail` |
| 特殊節日可接案 | `staff_holiday_availability` | `[其它].5` | `holiday_availability_other_detail` |
| 交通方式／其他交通方式 | `staff_transportation` | **目前沒有 other source 採納** | `transportation_other_detail` |

`staff_cooking_skills` 的 `[其它]` 屬「料理能力」母題，不是交通方式 fallback，固定不得拿來填 `transportation_other_detail`。

### 2.3 已知 implementation gap

現行 importer 的 `staff_transportation` 只採納 canonical transportation values，沒有綁定交通方式的 `[其它]` source。故本文件先正式保留 `transportation_other_detail` ownership，但在 persistence/read owner 補齊前，read model 必須回 `source_not_ready`，不得猜測、不得搬用其他母題 detail、不得把空值誤判為「月嫂沒有填寫」。

補齊 transportation other persistence 屬後續 runtime implementation；不在 #104 內修改 production DB 或 production data。

## 3. Canonical read model

月嫂名冊接案偏好使用獨立、唯讀、bounded 的 typed projection：

```text
StaffCasePreferenceSummary {
  staff_id: integer
  service_regions: PreferenceTopicSummary
  service_periods: PreferenceTopicSummary
  rest_schedule: PreferenceTopicSummary
  baby_counts: PreferenceTopicSummary
  holiday_availability: PreferenceTopicSummary
  transportation: PreferenceTopicSummary
}

PreferenceTopicSummary {
  values: string[]
  other_detail: string | null
  other_detail_status: "ready" | "not_recorded" | "source_not_ready"
}
```

契約規則：

1. `values` 只能來自該母題 canonical relation facts；固定去重並使用 owner-defined deterministic order。
2. `other_detail` 只能來自同一母題的 local `[其它]` ownership。
3. 有 detail 時不得要求 `values` 同時存在；「只填其它」仍是合法 read fact。
4. `other_detail_status=ready` 時 `other_detail` 必須是非空 canonical text。
5. `other_detail_status=not_recorded` 表示 owner 有能力判斷該欄位、但此 Staff 沒有採納值；此時 `other_detail=null`。
6. `other_detail_status=source_not_ready` 表示正式來源或 persistence 尚未能可靠提供；此時 `other_detail=null`，UI 不得把它當成使用者明確未填。
7. 不增加 generic `other_note`；六組 detail 永遠不得合併。

## 4. API / application owner

### 4.1 Application owner

正式 application owner 為 Staff domain 的獨立 query facade：

`StaffCasePreferenceSummaryQueryApplication`

建議放置於 `subsystems/staff/`，與 `StaffSummaryQueryApplication` 同屬 Staff read boundary，但兩者 DTO 不互相擴張。

Repository/read projection 可以 join Staff-owned canonical relation facts，但 Case Import importer 本身不是 UI query owner。HTTP adapter 與 React 都不得 import 或呼叫 Case Import mapper 來重新解析 workbook 語意。

### 4.2 HTTP contract

正式 bounded read route：

`GET /api/v1/staff/{staff_id}/case-preference-summary`

Response：

```json
{
  "staff_id": 531,
  "service_regions": {
    "values": ["北區", "新竹縣"],
    "other_detail": "偏遠地區需先確認交通",
    "other_detail_status": "ready"
  },
  "service_periods": {
    "values": ["8小時"],
    "other_detail": null,
    "other_detail_status": "not_recorded"
  },
  "rest_schedule": {
    "values": ["週休1日"],
    "other_detail": null,
    "other_detail_status": "not_recorded"
  },
  "baby_counts": {
    "values": ["雙胞胎"],
    "other_detail": null,
    "other_detail_status": "not_recorded"
  },
  "holiday_availability": {
    "values": ["中秋節"],
    "other_detail": null,
    "other_detail_status": "not_recorded"
  },
  "transportation": {
    "values": ["機車"],
    "other_detail": null,
    "other_detail_status": "source_not_ready"
  }
}
```

範例值只說明 shape，不是 production data，也不得拿來作 fallback/default。

Authorization 必須至少與現行內部 Staff roster read 權限同級；本契約不得擴大成 public Staff profile API。

## 5. UI owner 與 rendering rules

月嫂名冊 card / Drawer 是此 read projection 的 consumer，不是偏好 root owner。

UI 規則：

1. UI 只使用 Staff case-preference response；不得自行 join `staff_regions`、`staff_time_slots` 等資料表，也不得重新解析 BeClass header。
2. `values` 非空時依 API 順序顯示；空陣列時顯示「尚未登錄」。
3. `other_detail_status=ready` 時，在**同一母題**下顯示 `其它：{other_detail}`。
4. `other_detail_status=not_recorded` 時不另外顯示其它列；不得補空字串、`無`、`不限` 或推測值。
5. `other_detail_status=source_not_ready` 時，detail surface 顯示「其它來源尚未就緒」；card 可省略 detail，但不得顯示為「未填」。
6. 任一母題不可讀時，只降級該母題，不得把其他母題值搬過來。
7. 前端不得建立六組 detail 的 generic merge field，也不得用料理能力 `[其它]` 回填交通方式。
8. roster 不因偏好 source 缺失而隱藏 Staff；偏好是資訊／matching facts，不是名冊可見性的硬性資格。

## 6. Read / write boundary

本契約是 read-only。

- #104 不定義偏好編輯 UI。
- #104 不提供 `POST` / `PUT` / `PATCH` write route。
- 後續若要編輯上述 roots，必須交回各 root 的正式 owner，另行定義 Preview / Apply、validation、audit、version 與 idempotency 契約。
- roster UI 不得直接寫 canonical relation tables。
- BeClass historical facts 不因 roster 顯示需求而自動成為可編輯資料。

## 7. Sensitive-field exclusion

`StaffCasePreferenceSummary` 固定不得包含：

- `identity_card` 或其他身分證明資料
- 銀行帳號／分行資料
- IP address
- credential、password、token、session secret、encryption key
- `emergency_contact_name`
- `emergency_contact_phone`
- `admin_notes`
- raw workbook row、raw JSON、source fingerprint、idempotency key

這些欄位即使 Staff canonical storage 已存在，也不因本 read model 而成為 roster preference 資料。

## 8. Ownership / fallback 決策表

| topic | values owner | other owner | fallback |
|---|---|---|---|
| service regions | `staff_regions` | `service_region_other_detail` | 僅同母題；無值顯示尚未登錄 |
| service periods | `staff_time_slots` | `service_period_other_detail` | 僅同母題；無值顯示尚未登錄 |
| rest schedule | `staff_weekly_rest` | `rest_schedule_other_detail` | 僅同母題；無值顯示尚未登錄 |
| baby counts | `staff_baby_types` | `baby_count_other_detail` | 僅同母題；無值顯示尚未登錄 |
| holiday availability | `staff_holiday_availability` | `holiday_availability_other_detail` | 僅同母題；無值顯示尚未登錄 |
| transportation | `staff_transportation` | `transportation_other_detail` | persistence 未補齊前回 `source_not_ready`；固定不得借用 cooking other |

## 9. #104 acceptance mapping

- [x] 接案偏好的 canonical read model：`StaffCasePreferenceSummary` / `PreferenceTopicSummary` 已定義。
- [x] roster summary shape：六母題與 deterministic bounded shape 已定義。
- [x] UI owner / response contract：Staff query application、HTTP route、React consumer boundary 已定義。
- [x] 六組 `[其它]` ownership：六組 local owner 與禁止 generic `other_note` 已定義。
- [x] fallback：`ready` / `not_recorded` / `source_not_ready` 與 UI rendering 已定義。
- [x] 現況 gap：交通方式 other source 未採納已明示，禁止猜測或跨母題回填。
- [x] Safety：本 Issue 僅文件／architecture，無 production DB mutation、deploy 或 production re-import。
