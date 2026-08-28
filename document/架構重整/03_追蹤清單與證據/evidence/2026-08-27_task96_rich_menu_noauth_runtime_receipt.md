# Task 96 Rich Menu canonical no-auth runtime receipt

- Date：2026-08-27
- Current item：`CUR-LINE-RICHMENU-01`
- Result：`passed`（editable draft runtime slice）
- Overall Rich Menu item：`in-progress`
- Target：`APP_ENV=development`、`ACCESS_CONTROL_PROFILE=local_bypass`、`ENABLE_ADMIN_AUTH=false`、`lu_test_task96_scenarios_20260827`
- Non-goals：provider publication、production／`union_db`、schema／migration、uploaded media、假 publication task。

## Root cause and controlled initialization

初始唯讀回讀證明 `line_configuration_current` 完全沒有 row。Repository 因而對 `rich_menus` 回 revision 0／`{}`；Domain normalizer 產生空 menu list，而 typed public view 要求恰有一個 enabled default menu，因此 `GET /api/v1/line/rich-menus/draft` 正確 fail closed 為 422 `line_rich_menu_draft_invalid`。這是 canonical configuration seed gap，不是 route／decoder defect。

先執行零寫入 JSON validation：

```text
.venv/bin/python scripts/bootstrap_line_configuration.py
LINE configuration bootstrap JSON validation passed; no DB write performed.
```

再以正式 operator entrypoint、明確 development／allowlisted target 執行 `--apply`。命令只透過 `LineConfigurationApplication.bootstrap_missing()` append 缺失 revision，不直接寫 SQL、不覆寫 non-zero revision、不呼叫 provider：

```text
Applied 5 missing canonical LINE configuration revision(s).
```

after readback：`message_templates`、`message_schedules`、`rich_menus`、`liff`、`customer_service` 均為 revision 1、64-character fingerprint、actor `system:line-configuration-bootstrap`，並各有 `line.configuration.bootstrap` audit event。

## API／React／Browser acceptance

1. Bootstrap 後 `GET /api/v1/line/rich-menus/draft` 回 200；Rich Menu revision 1，customer／staff／union_staff 三個 menu 均為 `editable`。
2. Browser 顯示三角色選單、完整四熱區 geometry、typed URI／message actions、系統色彩背景與合法零筆 media／publication 狀態；原 422 alert 消失。
3. 以 `TASK96-RICHMENU-NOAUTH-20260827 草稿驗收` 修改 customer menu 名稱，完成 server Preview → 明確 checkbox 確認 → Apply → committed readback，建立 revision 2。
4. 以 `TASK96-RICHMENU-NOAUTH-20260827 驗收後還原` 走相同正式流程還原 `一般用戶選單`，建立 revision 3。current readback 為 baseline name、64-character fingerprint。
5. `line.rich_menu.draft.apply` audit lineage 精確為 `rich_menus:2`、`rich_menus:3`；`line_rich_menu_publication_tasks` count 為 0。
6. UI 明示「本機免驗證模式不可發布」；本輪未點擊或繞過 publication gate。Browser console 只有 Vite debug 與 React DevTools info，無 warning/error。

## Verification

| Gate | Result | Evidence |
|---|---|---|
| Bootstrap source validation | `passed` | JSON-only command明示 no DB write；五種 config source均通過 typed validation。 |
| Canonical DB initialization | `passed` | before current rows=0；after五種 revision 1＋fingerprint＋fixed idempotency＋audit readback。 |
| Draft API | `passed` | 422 seed gap → 200；revision 1，三個 exact editable locks。 |
| Browser Q/P/A/readback | `passed` | revision 1→2→3，baseline restored；status明示尚未發布。 |
| Provider／publication | `not_run` | task count 0；local bypass publication仍鎖定。 |
| Drift／readonly Browser | `not_run` | 沒有合法 processing／published fixture；不得直接 seed 或假發布。 |
| Parent focused regression | `passed` | Python 53、React 18、React production build PASS；只有既有 chunk-size warning。 |
| Fresh Luna High E3 | `passed`（source）／`not_run`（live API） | 78 Python、36 React、build、JSON validation、`git diff --check` PASS；verifier隔離環境 curl 8016 exit 7，故未把 live API算成獨立驗證。P0=0；live API/auth/provider缺口如實保留。 |

## DB gate classification

本輪沒有 schema、migration、release metadata、DDL、business-row backfill 或 destructive effect。五筆 baseline 是既有正式 operator command 對全空 canonical test DB 的 runtime configuration initialization，不是新的 release system-seed artifact；revision 2／3 是正式 draft Q/P/A business configuration history。

| Gate | Status | Evidence |
|---|---|---|
| Scope | `PASS` | `CUR-LINE-RICHMENU-01` 與 `17` §3.5 明列 draft Query／Preview／Apply／readback。 |
| Change inventory | `PASS` | schema-only=`none`；release system-seed artifact=`none`；business-row-backfill=`none`；destructive=`none`；runtime config append-only。 |
| Static release | `NOT_RUN` | 無 schema／release diff，非本輪必要 gate。 |
| Descriptor | `NOT_RUN` | 無 owned schema object變更。 |
| Read-only migration plan | `NOT_RUN` | 無 migration。 |
| Engine migration verification | `NOT_RUN` | 無 schema／migration。 |
| Developer replacement acceptance | `NOT_RUN` | 未執行 replacement／`--switch`，且不屬本 runtime slice。 |

DB summary：`NO_SCHEMA_CHANGE`。未操作 `union_db`、production、provider、reset、replacement 或 `--switch`。

## Remaining truth

本 receipt 只完成 editable draft 的 canonical no-auth runtime slice。完整 `CUR-LINE-RICHMENU-01` 尚缺 processing／published exact-revision drift／readonly Browser evidence；provider sandbox queue／worker／receipt/readback與 enabled persisted-human authorization 由獨立 current items列管，不能由本輪 bootstrap、草稿 success status或 publication count 0 冒充完成。
