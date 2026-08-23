---
doc_type: gap-package
declared_status: blocked
identity: PROV-20260817-react-admin-phase6c-per-entry-retirement-readiness-gap
date: 2026-08-17
owner: Entry Governance / Release Integration Owner
priority: P0
source_template: PROV-20260817-react-admin-phase6c-per-entry-retirement-template
---

# Phase 6C：十個 Streamlit entry 退役 readiness 缺口

## Current result

`READY 0 / GAP 10`。本文件是active retirement backlog，不授權刪除或建立可執行retirement WP。

共同缺口已有部分基礎完成但仍不足以啟動退役：Phase5A inventory／rollback及Phase5B Windows dual-run已PASS，
Phase6B-HOST亦已完成；current entrypoint queue為568筆，但readiness aggregate尚未重新產生。尚未閉合的是Phase5 production switch
successor與逐entryswitch／closed observation receipts、Phase6B-RUN release、Phase6A
`PHASE6_READY_FOR_ENTRY_RETIREMENT`、逐entry真browser／forward-data／rollback retention與deletion authority。

current registry有15個React identities與12筆rollback mapping，12-entry file-backed static control plane已安裝；
`#system-status`的durable runtime state仍未provision。Queue仍有37筆`review_required`，structural discovery exact
不等於semantic one-entry review完成。HOST已有artifact evidence，但RUN及
per-entry production switch／observation release receipts不存在，因此validator仍只能是
`VALIDATOR_INSTALLED_NOT_READY`／`PHASE6_NOT_READY`。

## Per-entry backlog

| Legacy entry | Replacement group | Current status | 必須先關閉的gap | Future provisional retirement identity |
|---|---|---|---|---|
| `ui:01_data_browser.py` | `ui-react:#data-browser` | BLOCKED | masked typed query、raw payload/PII移除、source-correction owner、browser rollback | `PROV-20260817-react-admin-phase6c-retire-data-browser` |
| `ui:02_orders.py` | `ui-react:#orders`＋`#order-tracker` | PARTIAL | SOP/notification/matching/settlement lineage、兩mutation runtime、one-to-two rollback/forward-data | `PROV-20260817-react-admin-phase6c-retire-orders` |
| `ui:03_calendar.py` | `ui-react:#scheduling` | BLOCKED | 3B1/3B2/Holiday、occupancy/leave outer-UoW、mock removal、browser rollback | `PROV-20260817-react-admin-phase6c-retire-scheduling` |
| `ui:04_finance.py` | `ui-react:#finance`＋`#reports` | BLOCKED | AP/Client Finance/Payout/Subsidy authority、PII、exports、all workspace receipts | `PROV-20260817-react-admin-phase6c-retire-finance` |
| `ui:05_form_management.py` | none approved | BLOCKED | dedicated identity、five-owner split、template/document/PII public contract | 不得建立WP |
| `ui:06_finance_alerts.py` | `ui-react:#anomalies` | PARTIAL | detail/recovery/claim/resolve/warning transition、disposable closed-loop、rollback | `PROV-20260817-react-admin-phase6c-retire-anomalies` |
| `ui:07_line_management.py` | `ui-react:#line-management` | PARTIAL | Delivery/Knowledge/rules/menu mutations、controlled identities/provider boundary、six-tab parity | `PROV-20260817-react-admin-phase6c-retire-line-management` |
| `ui:08_system_status.py` | `ui-react:#system-status` | PARTIAL | identity／dedicated page／rollback mapping與12-entry static control plane已安裝；仍缺durable runtime provision、production switch／observation與retention | `PROV-20260817-react-admin-phase6c-retire-system-status` |
| `ui:09_access_management.py` | `ui-react:#account-management` | BLOCKED | Account public contract/root auth/typed receipts、secret removal、true TOTP browser | `PROV-20260817-react-admin-phase6c-retire-access-management` |
| `ui:09_data_import.py` | `ui-react:#data-import` | BLOCKED | queue identity、six families、archive/atomicity/job outcome/warnings/replay/forward-data | `PROV-20260817-react-admin-phase6c-retire-data-import` |

## Source/caller ownership constraints

- `ui/app.py::PAGE_REGISTRY`、`ui/pages/shared.py`、`ui/request_state.py`、`ui/nav_helper.py`不得由單一entry包刪除。
- Scheduling matching panels、Finance Import panels、LINE managers與shared API clients須逐檔證明single owner；
  不明即retain。
- local/ngrok launcher、preflight、smoke、monitor、migration rehearsal、`pyproject.toml`與`uv.lock`是Phase6B-RUN／
  Phase6C-F shared responsibilities，不得放入任何單entry retirement包。
- 每個Streamlit test逐筆標`retain | migrate_then_remove | remove`並具replacement test；禁止skip/xfail。

## Promotion rule

某列只有在Phase5 candidate receipt、`phase5_navigation_switch_production_receipt`、
`phase5_observation_receipt`、Phase6A PASS、HOST/RUN獨立release approval、真browser、entry-specific rollback、
mutation forward-data（如適用）與path-level caller manifest全部PASS後，才能依Phase6C template建立
一份proposed exact retirement WP。真正移除仍須等待`expired_approved`，依序完成G7A candidate authority、
G7B隔離candidate removal及G8正式移除後回歸；Form Management另須先有approved successor identity與owner。

任何模型不得從本表自動產生刪除命令、修改queue為removed、配canonical ordinal或批次推進下一entry。

## Option A首筆候選：System Status preflight

本節只是non-authorizing checklist，不是retirement Work Package，也不含刪除命令。目前狀態：

| Required input | Current state | Disposition |
|---|---|---|
| React identity／dedicated page／rollback mapping | PASS（static installed） | 保留current evidence；不冒充target switch |
| 第12筆file-backed control-plane target | PASS（static installed） | `PROV-20260821-react-admin-system-status-control-plane-target-successor`已完成；不冒充runtime provision或switch |
| Durable 12-entry runtime state | NOT_RUN | provisioning tooling已完成，但deployment-owned state、lock、backup／restore drill與launcher readback尚未執行 |
| API compatibility／manifest identity | PARTIAL | Option C static focused 51 PASS；G6 runtime attestation與G7 React final gate仍NOT_RUN |
| Phase6B-RUN release | BLOCKED | 需HOST/local與private attestation一致、queue/state before-after不變 |
| Production same-origin single-entry switch | NOT_RUN | 必須另有exact switch successor與CAS receipt；本gap不授權 |
| Switch-back rehearsal／closed observation | NOT_RUN | 必須保留previous artifact與Streamlit exact rollback URL |
| Retention `expired_approved` | NOT_RUN | observation closed_success後才可開始；須BusinessClock與release-owner approval |
| G7A candidate removal authority | NOT_RUN | 需exact path/caller/test/source digest/restore provenance；只產authority不刪除 |
| G7B～G9 removal／regression／release | NOT_RUN | 只能在隔離candidate PASS後串行執行；失敗不得改正式source或queue |

在上述全部前置完成前，不建立`PROV-20260817-react-admin-phase6c-retire-system-status`實體檔案；只保留其
future provisional identity。這符合已核准Option A「READY 0時禁止啟動第一包」及exactly-one-candidate規則。

## DB gate

本gap是readiness backlog，0 DB change。Scope PASS、Change inventory PASS，其餘NOT_RUN；
`DB_CHANGE_NOT_READY`。
