# Rich Menu processing／published readonly drift 規格

- `spec_id`: `PROV-20260828-rich-menu-readonly-drift-spec`
- `declared_status`: `approved`
- `convergence`: `SPEC_READY`
- `owner`: LINE Rich Menu configuration read model／React administration surface
- `authority`: `CUR-LINE-RICHMENU-01`、正式規格 `17` §3.5、`20` §6，以及 Task 96 no-auth Browser 持續驗收授權
- `research`: `NO_RESEARCH (R0)`；current spec、application、route、fixture 與 runtime receipt 已足以裁決

## Objective 與 observable contract

補齊管理端對合法 `processing`／`published` exact-revision snapshot 的 server-owned readonly projection，
校正 fixture 中同一 menu/revision 同時 `published + editable` 的 live-drift，並以 development
`local_bypass` 做真 Browser 唯讀驗收。

1. Query 依 exact `(menu_definition_id, configuration_revision)` 投影
   `editable | processing | published`。
2. provider task `publishing` 映射為 `processing`；同 tuple 同時存在 `publishing`／`published` 時，
   `published` 優先。
3. `processing`／`published` 必須帶非空 readonly reason；React 不掛載 draft Preview／Apply、背景圖
   上傳／刪除或 provider mutation controls。
4. 舊 revision publication 不得鎖住 current draft，但仍可留在 publication history。
5. fixture 的 publication row 與 lock state 必須一致；unknown state、menu/revision mismatch、missing／extra
   lock 或缺 reason 固定 fail closed。

Canonical reasons：

- processing：`此版本正在發布處理中，為避免變更已送出的內容，目前只能查看。`
- published：`此版本已正式發布，為保留發布快照，目前只能查看；請建立新的草稿版本再調整。`

## Failure semantics 與 effect ceiling

| 情境 | 結果 |
|---|---|
| editable | `200`、reason `null`、draft controls可見 |
| processing／published | `200`、reason非空、mutation controls不可見 |
| same tuple processing＋published | 只投影 `published` |
| old revision publication | current draft仍editable |
| malformed／mismatch／missing lock | typed unavailable／readonly fail closed，不猜測editable |
| local bypass嘗試provider publication | `403`、不建queue、不wake worker |

允許本機 source/tests/fixtures/docs 與 development `lu_test_*` 唯讀驗收；禁止 provider publication、
正式登入、`union_db`／production、direct derived-state seed、schema/migration/reset/replacement/`--switch`。
`published` Browser fixture 只能來自既有合法 publication lineage；不存在時保持 `blocked/not_run`。

## Acceptance

- `RM-RO-A1`：processing、published、precedence、old revision 均由 exact server lock 投影。
- `RM-RO-A2`：readonly reason 精確顯示，所有 mutation controls 不存在。
- `RM-RO-A3`：fixture publication row／lock一致，malformed projection fail closed。
- `RM-RO-A4`：no-auth Browser 無 POST／PUT、provider request或worker wakeup，console error/warning為0。
- `RM-RO-A5`：缺合法 lineage 時不 direct seed、不假造 published evidence。

```yaml
convergence:
  status: READY
  blockers: []
```

Terminal status：`SPEC_READY`。
