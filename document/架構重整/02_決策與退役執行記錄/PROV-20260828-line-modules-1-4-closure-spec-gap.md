# LINE 模組 1～4 前後端與 UI 閉環規格缺口

- `spec_id`: `PROV-20260828-line-modules-1-4-closure-spec-gap`
- `declared_status`: `approved`
- `convergence`: `PARTIAL_M1_ROLE_SCOPE_APPROVED`
- `task_id`: `CUR-LINE-MODULES-1-4-CLOSURE-01`
- `priority`: Historical H/R/C/A → DB 1003→current → Rich Menu → 本項
- `canonical_source`: `01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md`
- `diagram_ids`: M1 `9vI_ssJZUHa59Yw7LXc0d`；M2 `xS5rOAuuQCUL139Tp4RA`；M3
  `IXLp95YCVlOmYlkS1gBkl`；M4 `bYdfiEJlAm-XhTLuLoJ-`

## 1. Current interpretation

流程圖定義 operator scenario 與驗收節點，不授權復活已被 current spec 取代的直接 DB 寫入。Client／Staff
profile、Scheduling、Assignment、Customer Service、Payroll、Staff Payables 與 LINE provider 都只能由各自
owner Query／Preview／Apply、receipt、fresh readback 與 durable side-effect boundary完成。

development `local_bypass` no-auth 只能驗管理端 M3/M4 與受控 development identity；真 LIFF token、mobile
admin、webhook/postback、recipient delivery與provider publication仍須各自正式驗證，不能由no-auth代替。

## 2. Module coverage

| Module | Current capability | Material gap | Acceptance focus |
|---|---|---|---|
| M1 LIFF／安全表單／身分 | verified binding、provisional registration、staff query／leave、identity review／revocation、role-scoped persistence、bounded streak、Staff retirement typed revocation effect | Client profile owner fields/version、mobile substitute review；DB engine evidence仍受合法`lu_test_*` gate阻塞 | verified identity、profile owner approval、leave stale/replay、mobile owner review、closure restore |
| M2 deterministic routing／客服 | protected alias、unknown fallback、cited Knowledge、durable delivery、production-injected ticket escalation／hold；repository-local focused `43 passed` | navigation/event catalog owner、feedback root；full AI仍正式`REJECT` | tier priority、wrong/human/hold safety、source citation、server revision、feedback receipt |
| M3 matching／coordination／substitution | typed backend Q/P/A、criteria/rematch/leave/service-date workflows、已掛載於Scheduling管理頁的React workbench；既有current schedule recipient snapshot／durable delivery intent／recipient-bound postback與React send/readback已repository-local閉環 | provider／真runtime evidence仍未驗收；新zero-pool／candidate-delivery語意固定`deferred-after-96` | current日期版本、exact recipient、postback token／rejection reason、fresh readback、stale零旁路 |
| M4 ops／alerts／human handoff | Customer Service state machine、hold/resolve、human escalation、runtime alert target CAS與LINE管理頁真UI；substitution完成後以既有Staff Payables typed GET回讀受影響人員的本案義務，失敗只重查GET、不重送Apply；focused Python `104 passed`、React `45 passed` | safe short-link、Scheduling owner mobile review | hold/resolve、target CAS、owner mobile review、payable/anomaly chain |

## 3. Authority blockers

- `M1_PROFILE_OWNER_FIELDS_AND_VERSION`
- `M1_LEAVE_SUBSTITUTE_MOBILE_REVIEW_CONTRACT`
- `M2_PHASE2_AI_CURRENTLY_REJECTED`（未經明確推翻不得施工）
- `M2_NAVIGATION_CATALOG_AND_FEEDBACK_ROOT`
- `M3_ZERO_POOL_DELIVERY_INTENT_CONTRACT`（`deferred-after-96`，不是Task 96 blocker）
- `M4_SAFE_ALERT_LINK_CONTRACT`

convergence：`NOT_READY`。因此目前不得建立正式整包 `PACKAGE_READY`。

## 4. Future package partition

| Candidate | Scope | Current status |
|---|---|---|
| `LINE14-P0-COVERAGE` | canonical node/edge coverage manifest與validation scenarios | convergence後可編譯 |
| `LINE14-P1-M1-CURRENT` | current identity／registration／staff query／leave／identity review UI證據 | 可獨立收斂 |
| `LINE14-P2-M1-PROFILE` | Client profile request→admin owner approval | `AUTHORITY_REQUIRED` |
| `LINE14-P3-M1-LIFECYCLE` | role-scoped binding／active role／two-failure／Staff retirement owner接線；不含mobile substitute review | `in-progress`；repository-local passed，DB engine仍`DB_CHANGE_NOT_READY` |
| `LINE14-P4-M2-DETERMINISTIC` | webhook→Tier1→durable reply/manual fallback | `repository-local passed`；provider/runtime外部 evidence不得由本結果外推 |
| `LINE14-P5-M2-CATALOG-FEEDBACK` | server-owned navigation/event catalog與feedback | `AUTHORITY_REQUIRED` |
| `LINE14-P6-M2-PHASE2` | confidence／AI provider | 正式`REJECT`；不得包裝 |
| `LINE14-P7-M3-WORKBENCH` | mount typed MatchingCoordinationWorkbench與owner Q/P/A | `repository-local passed`；不外推recipient/postback或真runtime evidence |
| `LINE14-P8-M3-RECIPIENT` | 既有current日期表雙方recipient snapshot／delivery intent／postback／React readback | `repository-local passed`；provider／真runtime evidence未驗；新zero-pool／candidate delivery排除並`deferred-after-96` |
| `LINE14-P9-M3-LEAVE-SHIFT` | leave/due shift→substitution/rematch | dependency blocked |
| `LINE14-P10-M4-OPS` | Customer Service hold/escalation與runtime target真UI | `repository-local passed`；不外推safe link、mobile review或provider delivery |
| `LINE14-P11-M4-MOBILE-LINK` | mobile owner review與短效安全連結 | safe link=`deferred-after-96`；LINE Identity已有owner mobile review，Scheduling review新增mobile public entry仍`BOUNDARY_REQUIRED` |
| `LINE14-P12-M4-PAYABLE` | substitution→Payroll→Payables readback；不新增export／provider effect | `repository-local passed`；existing committed Payroll facts + Staff Payables typed GET，focused React `2 passed` |
| `LINE14-P13-LINE-006` | LINE Notification owner Query／readback與Anomalies current predicate | `repository-local passed`；公開identity不變，typed zero-write logical group readback組合Notification applicability／exact manual-replay lineage與Delivery terminal result，owner mutation排bounded recheck，Anomalies只消費predicate／completeness |

owner或public contract不唯一、schema未過完整DB gates、target非development `lu_test_*`、unknown commit未完成
reconcile，或provider target／recipient／quota未精確回讀時固定停止。fixture、mock、頁面存在與單一HTTP 200
都不能作為節點完成證據。

M1 role-scoped binding／active role／two-failure與Staff retirement owner接線已由`23_LINE身分管理與解除正式規格.md` §9
及`24` §5.1收旂；不得將這項收旂外推到mobile substitute review、`LINE-006`
或其他M1～M4缺口。

`LINE-006` current closure evidence（2026-08-31）：最新人工裁決保持公開subject
`case_no + notification_reason`，以`subsystems/line/notification_failure_current_fact.py`及
`MySqlLineNotificationRepository.current_failure_fact`提供無aggregate persistence的typed owner readback。
同group只計currently-applicable source；exact `manual-replay:{source_event_id}:{idempotency_key}`目前lineage必須
fresh驗證recipient／binding／configuration並取得LINE Delivery terminal success才解除。manual replay、規則變更及
replay delivery result都在既有outer UoW排`anomaly.recheck`；Anomalies adapter／consumer不查LINE tables，
readback incomplete／unavailable固定fail closed。canonical focused tests與既有受影響tests合計`70 passed`，
formal architecture baseline、strict UTF-8、compile與diff check通過；Arch Map validator對本slice
沒有新增錯誤，global仍只有既存24個duplicate root及2個無關LINE source owner gap。本slice沒有schema、route、
provider實送或entry switch。

Terminal status：`PARTIAL_SPEC_READY`；M1 role-scoped package `PACKAGE_READY`；M2 deterministic、M3
Workbench／current schedule recipient-postback與M4 Ops／Payables readback已repository-local passed；deferred-after-96項目不構成Task 96 blocker，其餘current runtime／owner-specific工作仍依exact environment與dependency gate執行。
