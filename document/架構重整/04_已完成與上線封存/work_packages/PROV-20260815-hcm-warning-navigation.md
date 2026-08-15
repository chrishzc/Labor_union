---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: Anomalies / Case Import
priority: P0
---

# HCM 匯入警示中心導航 Work Package

## 人工裁決與場景

使用者於 2026-08-15 明確裁決：異常中心只提供去敏警示、處理追蹤與跳轉至 owning Domain 的業面；
不得在異常中心修正來源、接收外部更正值、建立正式根事實，或直接執行 HCM field completion、
linking、reimport 或 field change。後續管理前端預定以 React 重寫；本包 API 必須維持 UI 無關，
使目前 Streamlit 與未來 React 都只能消費 typed view 與 action descriptor。
使用者同日補充裁決：未滿足 HCM 最低 import 條件的列不進異常中心，因此不存在
`HCM-CASE-001`；欄位缺漏／格式錯誤保持通用 logical code，改由人可讀顯示文字指出欄位。

操作員在異常中心查看 HCM 欄位級警示，記錄聯絡進度後，取得去敏的下一步說明與受控跳轉資訊；
實際修正只能在 HCM owning UI／typed command 中重新讀取、驗證與提交。

## Scope

- 未滿足 HCM 最低 import 條件的 review 只完成 durable 稽核交付，不建 occurrence、task
  或 canonical anomaly。HCM review/outbox 只為已進入匯入流程的問題建立 field-level 警示；
  不能只留下 umbrella `IMPORT-004`。
- 異常中心 Query 僅回傳 masked subject、logical code、field path、人可讀 `display_message`、
  狀態與下一步 action identifier；
  本切片不回傳 navigation context，未知資料一律 fail closed。
- 未登錄 HCM issue 必須回滾整筆投影，錯誤只含 lane 與 issue digest；outbox 總嘗試
  最多 3 次、相鄰嘗試至少間隔 1 秒，後 dead-letter 停止熱迴圈，不建立部分待辦或伪裝成 field warning。
- HCM navigation action 只允許導向已存在且可驗證的 owning UI route；目標 command 不存在時回
  `no_action_available`，不得建立 generic correction form 或假跳轉。既有 BeClass review 也只提供
  導向資料匯入中心，不再於異常頁嵌入 corrected-payload 表單。
- Preview／Apply 僅限既有 warning tracking status transition；navigation Query 零寫入。
- API response 及 Streamlit adapter 不得傳遞 raw workbook、完整個資、外部回覆、corrected fields、
  candidate picker 或任何 root mutation payload。
- HCM review durable evidence 僅允許計數與 boolean metadata；任意文字一律拒絕，避免來源值、姓名、
  電話或外部回覆進入 warning occurrence。
- future React adapter 只能重用相同 typed API；本包不新增 React 專案、bundle、route 或部署。

## Non-goals

- 不實作 HCM field completion、Client linking、resubmission association、field change、
  auto-resolve predicate 或 WarningReferral root command。
- 不改寫 immutable source row、HCM review root、Client、Order、Anomalies source event 或 bank row。
- 不新增 schema、migration、backfill、LINE delivery、React runtime 或 deployment。

## Invariants

1. `closed` 只表示聯絡／追蹤結束，永遠不表示來源或正式 root 已修正。
2. navigation action 不攜帶 source/root identity；不得由 masked name、case label、電話或 raw workbook
   row 猜測 root。
3. 目標 UI／command 必須自行驗證 actor、fresh facts、version 與 business rule；異常中心不得替代。
4. 同一 HCM review 的 field-level warning occurrence identity 必須穩定；沒有可追溯 source event 時
   不顯示可操作 action。
5. logical code 表示問題類型，不表示單一欄位；欄位語意由 `field_path` 與
   `display_message` 承接，未來 React 不得重新發明一組欄位代號。

## Exact write set

- `domains/case_import/hcm_import_review.py`
- `subsystems/anomalies/hcm_import_review_outbox_consumer.py`
- `subsystems/anomalies/import_warning_tracking_workflow.py`
- `infrastructure/mysql/import_warning_tracking_repository.py`
- `api/schemas/import_warning_tracking.py`
- `api/routes/import_warning_tracking.py`
- `ui/api_clients/import_warning_tracking_api_client.py`
- `ui/pages/06_finance_alerts.py`
- 對應 focused Module／Subsystem／API client／disposable MySQL tests
- 本 Work Package、`02`／`03` 索引及 evidence receipt

任何 schema、HCM root command、public HCM mutation endpoint、React project、LINE side effect 或其他
owning lane 皆超出本包範圍，必須另立 successor Work Package。

## Acceptance

- HCM field-level warning 可由 committed HCM review outbox 投影並顯示於既有 Query，且不洩漏 raw data；
  未達 import 門檻者只留稽核，零 anomaly／warning／task。
- 缺漏與格式錯誤使用通用 logical code，顯示文字正確產生「缺少{欄位}」與
  「{欄位}格式錯誤」。
- 未知 HCM issue 零部分投影、錯誤不含 raw issue，第 3 次失敗後持久化 dead-letter 並停止領取；
  每次實際領取必須間隔至少 1 秒。
- Query 對可導航與不可導航 action 回傳 stable typed result；未知／stale／closed warning 不會產生
  mutation 或假 action。
- Streamlit 僅顯示 typed action descriptor；未來 React 可以消費同一 schema，無 UI-specific raw dict。
- existing status Preview／Apply 的 replay、conflict、stale 與 zero-write Preview 保持通過。
- `git diff --check`、focused tests及必要 disposable MySQL projection evidence通過；本包無 schema
  mutation，不能借用此驗收宣稱 HCM root 修正能力已完成。

## Closure

WP90 已承接此包的 warning projection／navigation 範圍，WP95 已承接其 HCM owner scoped
workbook correction。完成證據見 `2026-08-15_wp90_wp95_completion_receipt.md`；本文件不再保有 active
write set。
