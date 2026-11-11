# Staff Roster Case Preference Read Model 正式補充契約

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Staff Roster Read Projection
- 單一負責範圍：月嫂名冊「接案偏好」與 Staff 詳細 read projection 的 bounded response shape、UI fallback 規則、read-only 邊界與敏感欄位排除契約；不擁有偏好寫入或 Matching/Scheduling 規則。
- 關聯引用：見 [Staff Matching Preferences](24_Staff_Matching_Preferences與不可服務期間正式規格.md)、[Staff Roster Ownership Clarification](24B_Staff_Roster_Case_Preference_Ownership_Clarification.md)、[Global 效能與 UX 體感架構](12_Global_效能與UX體感架構.md)、[案件與月嫂整合名冊正式規格](33_案件與月嫂整合名冊正式規格.md)

月嫂名冊不得從 Case Import workbook、relation tables 或前端 local mapping 臨時拼出偏好，UI 只能讀取 Staff domain 提供的 bounded typed read projection。

## 2. 現況邊界與 BeClass relation 對應

### 2.1 既有 Staff roster summary 與 detail

- `subsystems/staff/summary_query.py` 的 `StaffSummary` 維持 bounded 欄位：`id`、`name`、`phone`、`education`，不隨 BeClass 題目擴張。
- 選取單一月嫂時以 `GET /api/v1/staff/{staff_id}/profile` 讀取 Staff-owned `StaffProfile`（含報名時間、完整身分證、行動電話、市話／分機、Email、生日、地址、學歷、完整緊急聯絡人電話、內部行政註記與銀行帳戶）。銀行完整帳號查閱與遮蔽邊界依 [案件與月嫂整合名冊正式規格](33_案件與月嫂整合名冊正式規格.md) §6 辦理；response 嚴禁包含 IP、LINE User ID、raw workbook／JSON 或 credential。空值顯示「尚未登錄」。
- 一般資格證明由 `staff_certifications` 擁有，與 `has_massage_cert` 投影到 qualification master 的 `certifications` section。

### 2.2 BeClass 已採納 relation facts 與交通方式 gap

| BeClass 母題 | canonical relation | 現行 `[其它]` source | 本契約 logical other owner |
|---|---|---|---|
| 希望服務地區 | `staff_regions` | `[其它].1` | `service_region_other_detail` |
| 服務時段 | `staff_time_slots` | `[其它].2` | `service_period_other_detail` |
| 如何排休 | `staff_weekly_rest` | `[其它].3` | `rest_schedule_other_detail` |
| 通常接幾胞胎 | `staff_baby_types` | `[其它].4` | `baby_count_other_detail` |
| 特殊節日可接案 | `staff_holiday_availability` | `[其它].5` | `holiday_availability_other_detail` |
| 交通方式／其他交通方式 | `staff_transportation` | 無 `[其它]` 來源採納 | `transportation_other_detail`（回 `source_not_ready`） |

`staff_cooking_skills` 的 `[其它]` 屬料理能力母題，嚴禁借填 `transportation_other_detail`。在 `staff_transportation` 補齊 persistence 前，`transportation_other_detail` 必須回 `source_not_ready`，不得猜測或顯示為「未填」。

## 3. Canonical read model

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

1. `values` 只能來自該母題 canonical relation facts，固定去重並採 owner-defined deterministic order。
2. `other_detail` 只能來自同一母題 local `[其它]` ownership；只有 detail 時仍是合法 read fact。
3. `other_detail_status=ready` 時 `other_detail` 須為非空 canonical text；`not_recorded` 與 `source_not_ready` 時皆為 `null`。
4. 禁止 generic `other_note`；六組 detail 永遠不合併。

## 4. API／Application owner 與 UI 呈現規則

- Application owner：`StaffCasePreferenceSummaryQueryApplication`（`subsystems/staff/`）。HTTP adapter 與 React 不得呼叫 Case Import mapper 重解 workbook。
- HTTP route：`GET /api/v1/staff/{staff_id}/case-preference-summary`（同 Staff roster read 權限，不擴大為 public API）。
- UI 呈現：
  1. `values` 非空依序顯示；空陣列顯示「尚未登錄」。
  2. `ready` 於同母題顯示 `其它：{other_detail}`；`not_recorded` 不另顯示其它列；`source_not_ready` 於 detail surface 顯示「其它來源尚未就緒」（不得誤標「未填」）。
  3. 任一母題不可讀只降級該母題；roster 不因偏好缺失隱藏人員。

## 5. Read / Write 邊界與敏感欄位排除

- 本投影為 read-only，不提供接案偏好的 `POST`/`PUT`/`PATCH` write route；資料與銀行修改依 [案件與月嫂整合名冊正式規格](33_案件與月嫂整合名冊正式規格.md) 及各 root owner 辦理。
- `StaffCasePreferenceSummary` 嚴禁包含：`identity_card`、銀行帳號／分行、IP address、credential／password／token／secret／key、`emergency_contact_name`/`phone`、`admin_notes`、raw workbook row／raw JSON／fingerprint／idempotency key。

## 6. 驗收標準

1. 六母題與 `PreferenceTopicSummary` shape 具確定性且 bounded；`values` 與六組 `[其它]` 各自隔離不合併。
2. `transportation` 在無正式來源前穩定回傳 `source_not_ready`，禁止挪用料理能力 `[其它]`。
3. Read projection 零敏感欄位洩漏、零寫入能力、UI 不直接 join relation tables。
