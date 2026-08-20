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

共同缺口：Phase5A registry/rollback、Phase5B dual-run、Phase5 navigation switch production successor與逐entry
switch/observation receipts、Phase6B-HOST、Phase6B-RUN、
Phase6A PASS、逐entry真browser/forward-data/observation receipts均尚未閉合。Current queue仍漏Data Import與全部
React identities，且不存在approved production artifact／previous artifact。
Phase6A requirements與source inventory也尚無獨立producer/revision receipts；HOST/RUN尚無machine-readable
release approval receipts，故validator即使安裝成功也只能是`VALIDATOR_INSTALLED_NOT_READY`。

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
| `ui:08_system_status.py` | proposed `ui-react:#system-status` | PARTIAL | identity amendment、dedicated page、artifact health、rollback | `PROV-20260817-react-admin-phase6c-retire-system-status` |
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

## DB gate

本gap是readiness backlog，0 DB change。Scope PASS、Change inventory PASS，其餘NOT_RUN；
`DB_CHANGE_NOT_READY`。
