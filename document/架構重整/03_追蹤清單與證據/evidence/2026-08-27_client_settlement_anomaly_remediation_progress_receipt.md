# 2026-08-27 Client Settlement 異常人工修正 final receipt

## 範圍與環境

- codes：`RECEIVABLE-001`、`CLIENTPAYABLE-001`、`RETURN-001`；三碼均完成真 MySQL／API／Browser 正向驗收。
- target：`APP_ENV=development`、`127.0.0.1`、`lu_test_task96_clientsettle2_20260827`、development root credential；未操作 `union_db`、production、provider、replacement、reset 或 `--switch`。
- fresh schema：canonical bootstrap release `labor-union-validation-schema-2026-08-27-v14`。
- scenarios：`T96-CS-20260827-01`（refund NT$500、adjustment NT$700、subsidy_return NT$900）及 `115000096`（receivable NT$600）；bank facts 均以 purpose／direction／recipient 或 virtual-account 精確綁定。
- 保留策略：保留上述隔離 DB 與唯一 scenarios，作為本 final receipt 的可重現 owner-rulebook／version-binding 證據；誤建且只有 base schema 的 `lu_test_task96_clientsettle_20260827` 已精確刪除，無業務資料且不需復原。

## 規則書 oracle 與結果

| 階段 | owner root readback | anomaly result |
|---|---|---|
| before | refund NT$500 open；adjustment NT$700 open；account version 0 | `CLIENTPAYABLE-001` active；detail 顯示兩筆 identity/type/due/amount 與「同碼全部歸零才解除」。 |
| partial Apply | refund settled=0；adjustment NT$700 open；account version 1 | workbench 明示另有同碼義務，異常保留；receipt/電話核對不被當成解除。 |
| terminal Apply | refund/adjustment 皆 settled=0；account version 2 | fresh owner Query 顯示同碼逾期義務空集合；正式 process-reminder worker recheck 將 predicate 設為 false、workflow resolved；Browser active list 由 4 筆降為 3 筆且本碼消失。 |
| receivable Apply | incoming allocation 後 receivable remaining=0；account version 1 | `RECEIVABLE-001` 經正式 worker fresh recheck 成為 predicate=false／resolved，Browser active list 不再顯示本碼。 |
| subsidy-return Apply | 只選 subsidy_return obligation 與 subsidy purpose outgoing fact；account version 2→3 | `RETURN-001` 成為 predicate=false／resolved；一般 refund/payable 分支未被重新開啟，證明 cross-purpose isolation。 |

一般退款分支的真 Browser 第二次 Preview 曾回 `client_refund_recipient_account_ambiguous`。根因是 Query 與 Domain 已允許 payable `adjustment`，但 MySQL owner loader 仍硬編碼 `refund/subsidy_return`。修正後 loader 依 purpose 使用 `refund + adjustment` 或單獨 `subsidy_return`，避免一般退款與補助退還互抵；同一真 Browser scenario 重試 Preview/Apply PASS。

`RETURN-001` 首次開啟曾被 stale guard 擋下。根因是 MySQL `COALESCE(BIGINT, 0)` 經 PyMySQL 回傳 `Decimal`，source adapter 只接受 `int`，錯把 owner account version 2 綁成 0。修正為以整數 NTD/version guard 接受無小數的 `Decimal`，並新增 MySQL-typed regression；重新投影後 action binding 為 version 2，真 Browser Preview/Apply PASS。這項修正保留 stale fail-closed，不放寬版本一致性。

FastAPI 不內嵌 Incident/Anomaly Worker；只啟動 API/React 時 active projection 不會自行更新，符合分離服務架構。執行正式 `consume_process_reminder_anomaly_sources` worker cycle 後才解除；不得用前端 terminal 文案取代 projector readback。

## 驗證摘要

- Backend final owner/anomaly regression：`127 passed, 1 skipped`。
- Backend Decimal-version focused：`9 passed`。
- React focused：`26 passed`。
- React production build：PASS（293 modules；既有 chunk-size warning）。
- React lint：PASS with existing warnings；本包無新增 lint error。
- Browser：三碼 detail、CLIENTPAYABLE partial retain、三碼 terminal owner readback、worker predicate=false、active-list removal與 RETURN/refund type isolation 全部 PASS；最終活動清單三碼 locator 均為 0。
- DB/schema inventory：本包 production/schema diff 為 0；只 bootstrap canonical schema 到新的 `lu_test_*` disposable DB，因此不構成新 schema release 或 migration。

## Package completion 與 Task 96 後續

- 本三碼 package 的 WP-A／WP-B／WP-C 均 `completed`。解除依據是 fresh owner root predicate，不是 tracking status、通知送達或前端文案。
- Task 96 整體仍 `in-progress`：其他 anomaly codes 仍須各自依 owner 規則書完成 bounded action、人工 Query／Preview／Apply、partial/stale/readback failure 反例與真實 runtime evidence。
