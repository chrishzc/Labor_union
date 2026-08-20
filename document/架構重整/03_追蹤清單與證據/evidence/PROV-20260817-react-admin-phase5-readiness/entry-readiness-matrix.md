# React Phase 5 entry readiness（2026-08-17）

判定需同時具備replacement contract、真browser、entry rollback URL、forward-data compatibility與focused
queue tests。畫面存在或unit tests通過不等於READY。

| Streamlit entry | React replacement | 狀態 | 主要阻擋 |
|---|---|---|---|
| `ui:01_data_browser.py` | `#data-browser` | BLOCKED | React仍mock；canonical masked query/source-correction與rollback未完成 |
| `ui:02_orders.py` | `#orders`／`#order-tracker` | PARTIAL | Phase2A query boundary已回退，須先remediation；SOP/通知/多數actions、受控資料與forward rollback缺失 |
| `ui:03_calendar.py` | `#scheduling`／`#staff` | BLOCKED | 仍mock；Staff/occupancy/leave public-contract與UoW缺口 |
| `ui:04_finance.py` | `#finance`／`#reports` | BLOCKED | 仍mock；AP auth/PII與Subsidy typed authority阻擋 |
| `ui:05_form_management.py` | 未裁決 | BLOCKED | 無exact replacement identity／owner／contract |
| `ui:06_finance_alerts.py` | `#anomalies` | PARTIAL | 兩GET有browser證據；claim/resolve/recovery與rollback未完成 |
| `ui:07_line_management.py` | `#line-management` | PARTIAL | 客服/Identity及rules/menu局部；delivery/FAQ gap、controlled data與rollback缺失 |
| `ui:08_system_status.py` | shared Shell／候選Account tab | PARTIAL | snapshot已browser驗證；無dedicated replacement/deep-link，Shell仍有硬編資料 |
| `ui:09_access_management.py` | `#account-management` | BLOCKED | Auth已真接；Account Center、masked Audit、Durable Job React三段皆未完成，MFA self-service另案 |
| `ui:09_data_import.py` | `#data-import` | BLOCKED | queue漏項；只有HCM Preview，Apply與其餘families未完成 |

## Aggregate

- Streamlit runtime entries：10；READY 0、PARTIAL 4、BLOCKED 6。
- Current queue有526筆，而current generator discovery有530筆，另漏4個已存在的API entries；UI方面仍漏
  `09_data_import.py`，React 11 hash routes全部未登錄。因此fresh已知registry gap至少16筆。
- Current Phase 5：`BLOCKED_ENTRY_REGISTRY + BLOCKED_OPERATIONAL_ROLLBACK + BLOCKED_DUAL_RUN_FORWARD_COMPATIBILITY`。
- 建議順序僅供後續候選：System Status query → Anomalies query → Orders query → LINE query；不構成cutover授權。
- `validation/scenarios/react_admin_entrypoints.json`、`ui_react/src/tests/react_entrypoint_registry.test.ts`與
  `tests/test_react_streamlit_entry_rollback.py`目前均不存在；`ui/app.py`也尚未讀取／驗證`?entry=`，因此
  10個rollback URL全部是規格候選，不是已實作能力。
- React baseline為11個hash routes；`#staff`是Scheduling deep-link，不是legacy replacement。`#system-status`
  是待核准identity amendment，Form Management則仍無replacement，故10↔11不是一對一cutover完成證據。

## Exact prerequisite closure

- 所有entry共同依賴`PROV-20260817-react-admin-phase5a-entry-governance-rollback`與
  `PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation`完成；實際切navigation另依賴
  `PROV-20260817-react-admin-phase5-entry-navigation-switch-decision`核准。
- Orders另依賴`PROV-20260817-react-admin-phase2a-orders-query-contract-boundary-remediation`；Contract Signing
  在public Query/redaction gap關閉前保持unavailable。
- Access依固定順序完成Account Center → Access Audit H/R → Durable Job Global/R；Login/TOTP成功不替代此鏈。
- LINE/Knowledge所有新Query／mutation contract都依賴
  `PROV-20260817-line-knowledge-authorization-normalization`，不得靠前端menu visibility補權限。
- Finance/Data Import依每個bounded family的backend→React successor及Durable Job；HCM historical固定410 retired。
- Form Management只依owner/public-contract gap人工裁決；未裁決前不得預先發明production successor。

## Fresh mechanical evidence

2026-08-17 Integration Owner 執行：

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase5-phase6-fresh -q tests\test_entrypoint_review_queue.py tests\test_launcher_inventory.py tests\test_local_development_launcher_smoke.py tests\test_online_script.py
```

結果：exit 1；`1 failed, 14 passed`。唯一失敗為
`test_queue_matches_current_entrypoint_discovery`，證明 current queue 與 discovery 漂移；不是測試環境失敗，
也不得刪除 assertion 或用同一 generator 產生 expected 來冒充修復。

Fresh counts為generator `530 = 443 API + 78 CLI + 9 Streamlit`，queue
`526 = 439 API + 78 CLI + 9 Streamlit`。四個缺失API identities為：

- `api:POST /api/v1/admin/auth/login/challenges`
- `api:POST /api/v1/admin/auth/login/challenges/{challenge_id}/verify`
- `api:POST /api/v1/customer-service/tickets/{ticket_id}/update/preview`
- `api:POST /api/v1/customer-service/tickets/{ticket_id}/update/apply`

再加入漏掉的Data Import Streamlit identity與11個React identities後，無其他base drift時expected queue為542。
Phase5A尚須先以exact approval擴充19號Global Entry Point Governance的`ui-react` kind；`#login`已在proposed
spec裁決為auth guard state而非第12個administrative entry。

## DB gate

Scope PASS（唯讀UI/entry盤點）；其餘DB gates NOT_RUN；結論`DB_CHANGE_NOT_READY`。
