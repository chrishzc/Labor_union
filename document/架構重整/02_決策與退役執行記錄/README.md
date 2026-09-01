# 決策與退役執行記錄索引

本目錄只保留 current task register、仍具約束力的 approved decision，以及 proposed／blocked／
in-progress Work Package。completed／superseded 文件確認無 current consumer 後自工作樹移除，
由 Git 歷史保存，不得繼續出現在日常 active 表。

正式業務語意以 `../01_規格基線/` 為準；Task 96已達repository-local acceptance，其
[`terminal register`](96_Current_剩餘代辦任務總表.md)因治理validator仍有直接consumer而保留，但不再是
施工清單。2026-08-30 Task 97亦已完成repository-local architecture closeout。舊 session、舊 gap register、
已封存 Work Package 與 archive evidence 不得重新建立待辦或完成 gate。

依 [Agent 任務分級與交付規範](../00_Agent任務分級與交付規範.md)，本目錄不是每個 implementation
slice 的日誌區。T1 不建立 Work Package；T2 只有確需跨步驟 coverage／handoff 時才維護一份 living parent
package；T3 才要求 current spec＋package。相同 owner／scenario／scope 應更新既有文件，不建立完成版複本。

## Current active working set

| 文件 | 類型 | 狀態 | 正確用途／下一個 gate |
|---|---|---|---|
| [匯入入口與 Legacy Writer 退役](Import_Entry_and_Legacy_Writer_Retirement_工作包.md) | work-package | `blocked` | Client LIFF 與 writer replacement 未全數閉合；不得直接移除入口。current LIFF 功能由 96 列管。 |
| [React Phase 6 retirement release gate](PROV-20260817-react-admin-phase6-retirement-release-gate-work-package.md) | work-package | `blocked` | 使用者目前禁止 entry switch／retirement；維持 fail closed。 |
| [React Phase 6C per-entry readiness gap](PROV-20260817-react-admin-phase6c-per-entry-retirement-readiness-gap.md) | gap-package | `blocked` | 未達逐入口 replacement／regression gate，不得啟動 retirement。 |
| [Warning Transition Streamlit bridge](PROV-20260822-react-admin-phase3d-warning-transition-streamlit-compatibility-bridge-work-package.md) | work-package | `proposed` | 非目前優先；須另行核准 exact scope 才可施工。 |
| [Access Control production cutover／external alert](Access_Control_Production_Cutover_and_External_Security_Alert_Work_Package.md) | work-package | `proposed` | production target、external sink、operator 與 rollback scope 未指定；維持 deferred。 |

## Retained current decisions／validation sources

下列文件不再是active施工包，但仍被正式規格、Arch Map或versioned validation scenario直接引用，因此保留：

- [歷史案件作業基準](PROV-20260827-historical-order-operational-baseline-spec.md)與
  [versioned scenario packages](PROV-20260827-historical-order-operational-work-packages.md)；
- [歷史付款與owner結清規格](PROV-20260828-historical-payment-and-owner-settlement-spec.md)及其
  [驗收package](PROV-20260828-historical-payment-and-owner-settlement-work-packages.md)；
- [Staff Payables completion readback裁決](PROV-20260827-historical-staff-payables-completion-root-spec-gap.md)；
- [Historical storage／supplement裁決](PROV-20260827-historical-operational-storage-and-supplement-spec-gap.md)；
- [營運前端真實資料優先裁決](PROV-20260822-operations-frontend-real-data-readiness-priority-amendment.md)。

這些文件的current consumer只限既有正式契約、navigation與validation identity；舊execution ledger、
package readiness或未完成snapshot不得覆蓋Task 96 terminal register與live verification。

## Task 97 repository-local closeout

[任務97架構一致性計畫](97_架構一致性修復與全域驗收計畫.md)及
[97B current successor](97B_Task97_current_head_stabilization_amendment.md)已依2026-08-30人工Authority完成
repository-local closeout；aggregate evidence由
[repository-local closeout receipt](../03_追蹤清單與證據/evidence/task97_repository_local_closeout_receipt_a48caa8.md)
保存。Current terminal result為`TASK97_REPOSITORY_LOCAL_COMPLETE`。

`PRODUCTION_ACCEPTANCE_NOT_RUN`及`DB_ENGINE_ACCEPTANCE_NOT_RUN`不是Task 97 local blocker，也不代表已通過。
Access T3／external provider／deployment／cutover仍由上列proposed Access Work Package或未來獨立production task
承接；真MySQL fresh／preserve驗證由未來獨立DB acceptance task承接。External caller未知的public entry維持
typed 410或`blocked_external_evidence`，不得physical delete。

## Retained terminal register

[`96 Current register`](96_Current_剩餘代辦任務總表.md)的狀態是
`repository-local-and-remote-ci-acceptance-complete`，只保留terminal結果、明示external exclusions及治理validator契約。
它不再授權續跑舊Task 96 Work Package；LIFF／provider、NAS、production／deployment與1019 preserve-upgrade
若要恢復，必須建立新的current successor。

## 2026-08-25 歷史 closeout

本輪將已由正式規格記錄完成，或已被較新規格／successor 取代的舊 Work Package、gap register 與
功能計畫已完成歷史收斂；其低頻副本現已自工作樹移除，需要時從移除前 Git commit
`5c43e847e016fb8d64ada4ac63fe2bee4b4a7a65` 精準取回。本索引不重列長清單。

M1 binding ownership、M3 matching coordination、M4 human escalation 的 backend closeout 已封存；
其尚未完成的 verified LIFF、provider、UI 或資料情境由 96 的 current tasks 接管，不能因舊包封存而
宣稱通過，也不能重開舊 Work Package。

2026-09-01第二批再封存已完成的Task 96 bounded Work Package、被single-code Anomalies契約取代的
42／33-code計畫，以及沒有current consumer的per-slice中間文件。移除前基準為
`06b1c72de2a49bebfeb6d75fe6ef077f98fafd4d`；current owner語意只讀`01_規格基線/`，不得從Git歷史
復活舊package Authority。

## 維護規則

- 新文件狀態限 `draft | proposed | approved | in-progress | blocked | completed | superseded`，並具 owner、
  scenario、scope、dependencies、write set、acceptance、tests 與 evidence／正式規格路由。
- `completed`／`superseded` 必須確認 successor、remaining task、inbound links 與 restore trigger 後從工作樹移除。
- Git 歷史是低頻追溯區，不是 current SSOT、代辦或實作授權；日常不得整批載入。
- provider、production DB、schema／migration、deployment、entry switch 與 destructive removal 仍須個別授權。
- 建立文件前必須有 current consumer、owner、close condition 與不能由 current spec／code／test 取代的理由。
