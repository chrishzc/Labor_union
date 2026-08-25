# 決策與退役執行記錄索引

本目錄只保留 current task register、仍具約束力的 approved decision，以及 proposed／blocked／
in-progress Work Package。completed／superseded 文件通過 archive gate 後移至
`../04_已完成與上線封存/`，不得繼續出現在日常 active 表。

正式業務語意以 `../01_規格基線/` 為準；跨功能 current 待辦只看
[`96_Current_剩餘代辦任務總表.md`](96_Current_剩餘代辦任務總表.md)。舊 session、舊 gap register、
已封存 Work Package 與 archive evidence 不得重新建立待辦或完成 gate。

## Current active working set

| 文件 | 類型 | 狀態 | 正確用途／下一個 gate |
|---|---|---|---|
| [96 Current 剩餘代辦任務總表](96_Current_剩餘代辦任務總表.md) | gap-register | `in-progress` | 唯一跨功能 current task register；完成後先同步 owner 正式規格，再關閉該列。 |
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
