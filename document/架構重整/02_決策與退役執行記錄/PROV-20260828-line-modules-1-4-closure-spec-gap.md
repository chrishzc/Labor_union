# LINE 模組 1～4 前後端與 UI 閉環規格缺口

- `spec_id`: `PROV-20260828-line-modules-1-4-closure-spec-gap`
- `declared_status`: `approved`
- `convergence`: `AUTHORITY_REQUIRED`
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
| M1 LIFF／安全表單／身分 | verified binding、provisional registration、staff query／leave、identity review／revocation | Client profile owner fields/version、雙失敗、dual-role restore、Staff retirement、mobile substitute review | verified identity、profile owner approval、leave stale/replay、mobile owner review、closure restore |
| M2 deterministic routing／客服 | protected alias、unknown fallback、cited Knowledge、durable delivery、ticket escalation／hold | navigation/event catalog owner、feedback root；full AI仍正式`REJECT` | tier priority、wrong/human/hold safety、source citation、server revision、feedback receipt |
| M3 matching／coordination／substitution | typed backend Q/P/A、criteria/rematch/leave/service-date workflows、React workbench source | Workbench未mount；zero-pool delivery intent與recipient/postback contract未定；跨頁runtime evidence不足 | criteria diff、zero pool不自動改單、selection lineage、substitution invariants、stale零旁路 |
| M4 ops／alerts／human handoff | Customer Service state machine、runtime alert target CAS、LINE query surfaces、leave substitution | safe short-link、two-failure trigger、mobile review、substitution→Payroll→Payables跨域UI readback | hold/resolve、target CAS、masked alert、owner mobile review、payable/anomaly chain |

## 3. Authority blockers

- `M1_PROFILE_OWNER_FIELDS_AND_VERSION`
- `M1_TWO_FAILURE_DUAL_ROLE_RETIREMENT_CONTRACTS`
- `M1_LEAVE_SUBSTITUTE_MOBILE_REVIEW_CONTRACT`
- `M2_PHASE2_AI_CURRENTLY_REJECTED`（未經明確推翻不得施工）
- `M2_NAVIGATION_CATALOG_AND_FEEDBACK_ROOT`
- `M3_ZERO_POOL_DELIVERY_INTENT_CONTRACT`
- `M4_SAFE_ALERT_LINK_CONTRACT`

convergence：`NOT_READY`。因此目前不得建立正式整包 `PACKAGE_READY`。

## 4. Future package partition

| Candidate | Scope | Current status |
|---|---|---|
| `LINE14-P0-COVERAGE` | canonical node/edge coverage manifest與validation scenarios | convergence後可編譯 |
| `LINE14-P1-M1-CURRENT` | current identity／registration／staff query／leave／identity review UI證據 | 可獨立收斂 |
| `LINE14-P2-M1-PROFILE` | Client profile request→admin owner approval | `AUTHORITY_REQUIRED` |
| `LINE14-P3-M1-LIFECYCLE` | two-failure、dual-role/menu restore、retirement、mobile substitute review | `AUTHORITY_REQUIRED` |
| `LINE14-P4-M2-DETERMINISTIC` | webhook→Tier1→durable reply/manual fallback | 可獨立收斂 |
| `LINE14-P5-M2-CATALOG-FEEDBACK` | server-owned navigation/event catalog與feedback | `AUTHORITY_REQUIRED` |
| `LINE14-P6-M2-PHASE2` | confidence／AI provider | 正式`REJECT`；不得包裝 |
| `LINE14-P7-M3-WORKBENCH` | mount typed MatchingCoordinationWorkbench與owner Q/P/A | 最接近ready |
| `LINE14-P8-M3-RECIPIENT` | zero-pool、雙方通知、recipient postback | 部分`AUTHORITY_REQUIRED` |
| `LINE14-P9-M3-LEAVE-SHIFT` | leave/due shift→substitution/rematch | dependency blocked |
| `LINE14-P10-M4-OPS` | Customer Service hold/escalation與runtime target真UI | 最接近ready |
| `LINE14-P11-M4-MOBILE-LINK` | mobile owner review與短效安全連結 | `AUTHORITY_REQUIRED` |
| `LINE14-P12-M4-PAYABLE` | substitution→Payroll→Payables/export/anomaly readback | dependency blocked |

owner或public contract不唯一、schema未過完整DB gates、target非development `lu_test_*`、unknown commit未完成
reconcile，或provider target／recipient／quota未精確回讀時固定停止。fixture、mock、頁面存在與單一HTTP 200
都不能作為節點完成證據。

Terminal status：`AUTHORITY_REQUIRED`；`SPEC_READY=NOT_READY`；`PACKAGE_READY=NOT_READY`。
