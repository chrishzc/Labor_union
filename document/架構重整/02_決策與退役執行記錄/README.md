# 決策與退役執行記錄索引

本目錄只保留 current task register、仍具約束力的 approved decision，以及 proposed／blocked／
in-progress Work Package。completed／superseded 文件通過 archive gate 後移至
`../04_已完成與上線封存/`，不得繼續出現在日常 active 表。

正式業務語意以 `../01_規格基線/` 為準；跨功能 current 待辦只看
[`96_Current_剩餘代辦任務總表.md`](96_Current_剩餘代辦任務總表.md)。舊 session、舊 gap register、
已封存 Work Package 與 archive evidence 不得重新建立待辦或完成 gate。

依 [Agent 任務分級與交付規範](../00_Agent任務分級與交付規範.md)，本目錄不是每個 implementation
slice 的日誌區。T1 不建立 Work Package；T2 只有確需跨步驟 coverage／handoff 時才維護一份 living parent
package；T3 才要求 current spec＋package。相同 owner／scenario／scope 應更新既有文件，不建立完成版複本。

## Current active working set

| 文件 | 類型 | 狀態 | 正確用途／下一個 gate |
|---|---|---|---|
| [96 Current 剩餘代辦任務總表](96_Current_剩餘代辦任務總表.md) | gap-register | `in-progress` | 唯一跨功能 current task register；完成後先同步 owner 正式規格，再關閉該列。 |
| [全異常人工 remediation 收斂缺口](PROV-20260826-all-anomaly-manual-remediation-spec-gap.md) | spec-gap | `in-progress` | 96 新增 P0；先收斂每個 anomaly code 的 owner action／completion predicate，再分 owner package 實作。 |
| [歷史訂單 review 人工更正工作包](PROV-20260826-historical-order-review-remediation-work-package.md) | work-package | `in-progress` | 96 P0 的第一個 owner slice；尚缺 enabled persisted-human Browser 與 developer acceptance。 |
| [歷史案件作業基準與狀態感知異常規格](PROV-20260827-historical-order-operational-baseline-spec.md) | spec | `approved`／`SPEC_READY` | Historical-only baseline、無額外違約金、Orders／Finance 分離、服務中代班不要求新契約／簽回或客戶變更簽署（optional supplement 不阻擋代班／排班 lineage／薪資），以及 Client Finance cancellation `direction` 與 action mapping 均已裁決；剩餘為實作／runtime 驗收，不是 authority blocker。 |
| [歷史案件作業基準與狀態感知異常工作包](PROV-20260827-historical-order-operational-work-packages.md) | work packages | `PACKAGE_READY` | B1／S1／S2已裁決；六包契約ready，但各包source／schema／runtime完成度仍以包內snapshot為準。 |
| [歷史付款證據與 owner 帳務結清規格](PROV-20260828-historical-payment-and-owner-settlement-spec.md) | spec | `approved`／`SPEC_READY` | 對帳單優先；pre-system historical人工fallback；payment、Client settlement、Staff payout與Step 11分離；客戶補助退款固定歸Client Finance。 |
| [歷史付款證據與 owner 帳務結清工作包](PROV-20260828-historical-payment-and-owner-settlement-work-packages.md) | work package | `PACKAGE_READY` | HPROJ finance/staff adapter的必要前置；先完成兩owner Q/P/A、additive persistence、異常頁與readback，再恢復six-owner runtime。 |
| [Historical Staff Payables case completion readback 裁決](PROV-20260827-historical-staff-payables-completion-root-spec-gap.md) | decision record | `approved`／`SP2-Q_APPROVED` | 人工已採用query-only typed source vector；internal source candidate為`78 passed`＋真MySQL唯讀SQL解析PASS。fresh verifier與API／projector／React／runtime仍未完成；`SP1-M`無必要性證據。 |
| [Historical baseline storage 與 substitution supplement 裁決記錄](PROV-20260827-historical-operational-storage-and-supplement-spec-gap.md) | decision record | `approved` | B1 baseline三表append-only storage、S1 Scheduling-owned note與S2 method enum已採用；S1／S2只是備註，不影響流程運行。 |
| [異常必要性移轉工作包](PROV-20260827-anomaly-necessity-migration-work-package.md) | work-package | `approved`／A～C ready、D `SPEC_GAP` | 42-code inventory→33 active target；先建 immutable migration disposition，再安全移轉六個工作項、退役 SCHEDULE-005、去重 Staff overpayment successor。 |
| [六個一般工作項 owner target 契約](PROV-20260827-anomaly-work-item-owner-target-spec.md) | spec-gap | `proposed`／`AUTHORITY_REQUIRED` | 固定六碼 migration 的 owner root／version／fresh-lock／fail-closed 契約；Candidate Pool 版本、LINE task 版本與 ORDER-001/002 target 尚待確認。 |
| [CUR-FILE-NAS-01 受控檔案儲存基礎工作包](PROV-20260826-controlled-file-storage-foundation-work-package.md) | work-package | `approved` | 96 O1 專用工作包；限制於 controlled-file capability、本機 additive DB gates 與 typed 驗收。 |
| [營運前端真實資料優先裁決](PROV-20260822-operations-frontend-real-data-readiness-priority-amendment.md) | decision-work-package | `approved` | 保留 current 操作優先與真實資料／完整 continuation 原則；不是重跑已完成 Orders／Staff／Reports 的授權。 |
| [匯入入口與 Legacy Writer 退役](Import_Entry_and_Legacy_Writer_Retirement_工作包.md) | work-package | `blocked` | Client LIFF 與 writer replacement 未全數閉合；不得直接移除入口。current LIFF 功能由 96 列管。 |
| [React Phase 6 retirement release gate](PROV-20260817-react-admin-phase6-retirement-release-gate-work-package.md) | work-package | `blocked` | 使用者目前禁止 entry switch／retirement；維持 fail closed。 |
| [React Phase 6C per-entry readiness gap](PROV-20260817-react-admin-phase6c-per-entry-retirement-readiness-gap.md) | gap-package | `blocked` | 未達逐入口 replacement／regression gate，不得啟動 retirement。 |
| [Warning Transition Streamlit bridge](PROV-20260822-react-admin-phase3d-warning-transition-streamlit-compatibility-bridge-work-package.md) | work-package | `proposed` | 非目前優先；須另行核准 exact scope 才可施工。 |
| [Access Control production cutover／external alert](Access_Control_Production_Cutover_and_External_Security_Alert_Work_Package.md) | work-package | `proposed` | production target、external sink、operator 與 rollback scope 未指定；維持 deferred。 |

## 2026-08-25 archive closeout

本輪將已由正式規格記錄完成，或已被較新規格／successor 取代的舊 Work Package、gap register 與
功能計畫移至 `../04_已完成與上線封存/work_packages/` 或 `superseded_specs/`。精確 source path、
archive path、digest、successor 與 restore trigger 只查 `archive_manifest.json`；本索引不重列長清單。

M1 binding ownership、M3 matching coordination、M4 human escalation 的 backend closeout 已封存；
其尚未完成的 verified LIFF、provider、UI 或資料情境由 96 的 current tasks 接管，不能因舊包封存而
宣稱通過，也不能重開舊 Work Package。

## 維護規則

- 新文件狀態限 `draft | proposed | approved | in-progress | blocked | completed | superseded`，並具 owner、
  scenario、scope、dependencies、write set、acceptance、tests 與 evidence／正式規格路由。
- `completed`／`superseded` 必須確認 successor、remaining task、inbound links 與 restore trigger 後封存。
- archive 是低頻追溯區，不是 current SSOT、代辦或實作授權；日常不得整批載入。
- provider、production DB、schema／migration、deployment、entry switch 與 destructive removal 仍須個別授權。
- 建立文件前必須有 current consumer、owner、close condition 與不能由 current spec／code／test 取代的理由。
