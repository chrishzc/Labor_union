---
doc_type: decision-package
declared_status: decision-complete-removal-not-authorized
---

# Legacy Retirement Wave 1 Decision Package

## 1. 狀態與授權邊界

- 狀態：`decision-complete-removal-not-authorized`
- 建立日期：2026-08-03
- Repository：`codex/refactor-api-streamlit-architecture`
- HEAD：`4081a9b40c91a030c64f1d488411287ec6c01bdc`
- 正式架構依據：已核准的 `15`～`18`
- 現況依據：Inventory v2 final、live source、production caller 與 router wiring
- 本文件只裁決第一波退役範圍，不授權修改或移除 production code、pytest、schema、
  資料、部署或 Git state。

弱模型 semantic evidence 只作 discovery 參考；本裁決不採用其 disposition。

## 2. 第一波結果

Wave 1 選定一個可獨立退役的 production module：

`services/caregiver_availability_lock_conversion_service.py`

理由：

1. 正式 Scheduling 規格已把第一個 assignment bootstrap 收斂到 Assignment Plan
   Preview／Apply；第一個正式 assignment 必須在該 outer Unit of Work 內轉換同案
   waiting-deposit lock。
2. legacy conversion API 已固定回
   `410 legacy_availability_lock_conversion_retired`，並指向 Assignment Plan
   Query／Preview／Apply。
3. live production roots 沒有 import 或呼叫本 module；唯一程式引用是它自己的 legacy
   pytest。
4. module 仍包含跨 Orders、Scheduling 與舊付款投影的直接 SQL 及 hidden commit；
   保留它只會留下可被誤接回 production 的第二套規則。
5. module 與 paired legacy test 都是 tracked、clean paths，沒有 dirty overlap。

本裁決將它標為 `remove-candidate`，但仍維持
`effective_disposition=blocked`、`approved_to_remove=false`，等待獨立 removal
Work Package 的人工核准。

## 3. 裁決表

| path／symbol | 裁決 | 原因 | 本波動作 |
|---|---|---|---|
| `services/caregiver_availability_lock_conversion_service.py` | `remove-candidate` | production caller=0；正式 Assignment Plan 已取代整個 direct-conversion workflow | 下一個 removal WP 才可刪除 |
| `tests/test_caregiver_availability_lock_conversion_service.py` | `remove-candidate` | 只驗證已退役的第二套規則；不能在 production module 移除後繼續把舊行為當契約 | 與 production module 同一 removal WP 移除 |
| `subsystems/scheduling/assignment_plan_workflow.py` | `retain` | 正式 Assignment Plan outer workflow | 不修改 |
| `infrastructure/mysql/assignment_plan_repository.py` | `retain` | 正式 Scheduling persistence adapter | 不修改 |
| `api/routes/assignment_plan.py` | `retain` | 正式 typed Query／Preview／Apply HTTP adapter | 不修改 |
| `ui/api_clients/assignment_plan_api_client.py` | `retain` | 薄 UI 的 typed client | 不修改 |
| `ui/pages/scheduling/assignment_plan_panel.py` | `retain` | 正式 Assignment Plan UI | 不修改 |
| `api/routes/caregiver_availability_locks.py::convert_availability_lock` | `migrate-then-remove` | 目前只提供 410 與 replacement paths；屬 public deprecation adapter，不是 writer | 本波保留；依 API expiry 治理另行退役 |
| `services/caregiver_availability_lock_service.py` | `retain` | 正式 waiting-deposit lock acquire Preview／Apply 仍有 live route caller | 不修改 |
| `services/caregiver_availability_lock_release_service.py` | `retain` | 正式 waiting-deposit lock release Preview／Apply 仍有 live route caller | 不修改 |

## 4. Inventory v2 精確身分

Source SHA-256：

`b333693fcaf9c5dd0f6914d69021966d0e27137471e90c89b2ec5948671a1838`

| Inventory row | finding digest | symbol | operation | table |
|---:|---|---|---|---|
| 337 | `7e1530fced0bd526b0f7d088528a0cabdaf6120ed01a31db381ab9f7e5833434` | `_load_preflight_lock_days` | `DYNAMIC` | `unknown` |
| 338 | `4b04abd8a759ddb541af9bcd64369566561320141c13422eb863686aa5d3bf36` | `convert_availability_lock_to_assignments` | `COMMIT` | `-` |
| 339 | `8b69ef4bf38658ec2303ee9abe3b30eb1c3c2a0c1e87a3abdb53d95187ccb778` | `convert_availability_lock_to_assignments` | `COMMIT` | `-` |
| 340 | `dbf2356c98a1571c8a6e7e322459bf07de8c88aa3ab8b4b65d2cca394f9eeeca` | `convert_availability_lock_to_assignments` | `INSERT` | `caregiver_availability_lock_events` |
| 341 | `0dca55ec7f5b5938965eb10d5f004ad8664db50743071f49570d6fb7350b53c0` | `convert_availability_lock_to_assignments` | `INSERT` | `case_staff_assignments` |
| 342 | `69faca2972f4e843dc84f14eb6c4798bec5bc860497cb98a6e28c56212de816a` | `convert_availability_lock_to_assignments` | `UPDATE` | `caregiver_availability_lock_days` |
| 343 | `b5f98d6bc3b0e1d79492b4724d9c8942ebab9441412713b11581e45e5ddb649c` | `convert_availability_lock_to_assignments` | `UPDATE` | `caregiver_availability_locks` |
| 344 | `312c3a34b2ca00e212a2b6c7708f606b3670365b96c27fd599f6623db7c561f1` | `convert_availability_lock_to_assignments` | `UPDATE` | `orders` |

Row 337 是 locking read scanner finding，不是 writer；它會隨整個 dead module 一起退出，
不能拿來宣稱移除了額外 mutation。預期 writer inventory 變化是此 exact source 的
rows 337～344 全部消失，其他 finding identity 不變。

## 5. Caller 裁決

### 5.1 Production caller

搜尋範圍：

- `api`
- `infrastructure`
- `line`
- `scripts`
- `services`
- `subsystems`
- `ui`
- `start.bat`
- `pyproject.toml`

精確 module name、import form、公開函式
`convert_availability_lock_to_assignments` 均未找到 owning module 外的 production
caller。`ui/app.py` 的 dynamic import 只掃描 `ui/pages/*.py`，不會載入 `services`
module。

結論：`production_caller_zero_candidate=true`。

### 5.2 非 production 引用

- `tests/test_caregiver_availability_lock_conversion_service.py` 直接 import legacy module。
- legacy `system_map*.md`／`system_map*.yaml` 只屬歷史 metadata，不是 runtime caller；
  退役後應留下 archive notice 或移除 active source 宣稱，但不得把更新 legacy map
  當 production removal gate。
- `api/routes/caregiver_availability_locks.py::convert_availability_lock` 名稱相似，但不
  import 或呼叫 legacy service；它只回 410。

Machine-readable caller evidence 位於
`evidence/legacy_retirement_wave_1/caller_manifest.json`。

## 6. 依賴切斷順序

未來取得 removal 授權後，必須依序執行：

1. fresh-read branch、HEAD、status、兩個 removal paths 與 replacement paths。
2. 驗證 source／test hashes仍與本文件一致；任何漂移立即停止並重做裁決。
3. 重跑 caller scan，確認 production caller 仍為 0。
4. 先執行 replacement 的 Module／Subsystem／API 測試，證明正式路徑在移除前健康。
5. 同一 patch 移除 legacy production module 與只驗舊規則的 paired test。
6. 保留 410 compatibility route、replacement paths、正式 waiting-lock acquire／release
   及 Assignment Plan 所有 production paths。
7. 執行下節驗證矩陣。
8. fresh-run writer inventory；只允許上述八個 exact findings 消失，不得出現新 writer。
9. 產出 post-removal receipt，交由人工決定是否接受；不得自動 stage／commit／push。

不需要先改接 caller，因為 live production caller 已是 0。真正的切斷點是移除 legacy
test 對第二套規則的契約地位。

## 7. 驗證矩陣

| 層級 | 必驗證內容 | 建議命令／證據 | Pass 條件 |
|---|---|---|---|
| Static | legacy module 不再存在且無 import／symbol caller | `rg` exact module＋symbol；Python compile/import collection | production caller=0；無 import error |
| Module | Assignment Plan pure rules／impacts | `tests/domains/test_assignment_plan.py`、`tests/subsystems/scheduling/test_assignment_plan_impacts.py` | 全通過 |
| Subsystem | Assignment Plan Preview／Apply、waiting-lock bootstrap、replay／stale／rollback | `tests/subsystems/scheduling/test_assignment_plan_workflow.py` | 全通過 |
| Infrastructure | 正式 repository transaction、locks、receipt | `tests/infrastructure/test_assignment_plan_repository.py` | 全通過 |
| Domain MySQL | 第一個 assignment 必須消費 waiting lock；無 lock fail closed | `tests/domains/test_assignment_plan_mysql.py`，只用 disposable MySQL | 全通過；不得使用 `union_db` |
| API | legacy convert 保持 410；正式 Assignment Plan routes 可用 | `tests/test_caregiver_availability_lock_router.py`、`tests/test_assignment_plan_router.py` | 410 contract 與 typed replacement 同時通過 |
| UI | 薄 UI 只呼叫 typed replacement | `tests/test_assignment_plan_api_client.py`、`tests/test_assignment_plan_ui_panel.py` | 無 legacy service import |
| Global | writer inventory exact delta | fresh Inventory v2 before／after diff | 只少 rows 337～344 對應 identities；無新增 finding |

Removal WP 不得為了讓測試通過而修改業務語意、schema、fixture snapshot 或正式資料。

## 8. Rollback plan

本波不做 schema 或資料變更，因此 rollback 只涉及 code：

1. removal 前保存兩個 exact source blob SHA 與 patch。
2. 若任一驗證失敗，只恢復：
   - `services/caregiver_availability_lock_conversion_service.py`
   - `tests/test_caregiver_availability_lock_conversion_service.py`
3. 恢復後重跑同一驗證矩陣與 writer inventory，確認八個 findings 完整返回且沒有其他
   source 漂移。
4. 不回滾或改動 Assignment Plan、waiting-lock、schema、資料、410 route 或其他 dirty
   paths。

Production 若已部署才需要 deployment rollback；本 Decision Package 與下一個建議的
code-removal WP 都不含部署。

## 9. 本波排除項目

下列四個 Orders legacy modules 雖然目前也沒有 production caller，但它們與 paired
tests 都是 untracked 使用者檔案，不能在 dirty-worktree 保護下併入本波：

- `services/order_actual_start_reconfirmation.py`
- `services/order_cancellation_command.py`
- `services/order_lifecycle_hold_commands.py`
- `services/order_lifecycle_manual_correction.py`

它們維持 `remove-candidate-held-for-dirty-overlap`。若要退役，必須由使用者另行明確
指定 exact untracked paths、保存方式及 rollback artifact；不得因「無 caller」直接刪除。

Client Finance、Staff Payables、Finance Import、Anomalies、Access／LINE／BreezySign 與
deployment／expiry paths 也不在本波；它們的交易、外部副作用及治理風險需要各自獨立
Wave。

## 10. 下一個可核准 Work Package

下一步只能核准 `Wave 1A code removal`，exact writable paths 限於：

- `services/caregiver_availability_lock_conversion_service.py`
- `tests/test_caregiver_availability_lock_conversion_service.py`

允許刪除這兩個檔案並執行第 7 節有限測試與 read-only fresh inventory；不得修改其他
production／test path、schema、資料、部署或 Git state。
