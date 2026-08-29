# Task 96 LDU 1003→1012 aggregate final receipt

- `date`: 2026-08-28
- `package`: `LDU-1003-CURRENT-01`
- `scope`: listed Task 96 LDU ordered-chain／launcher、1006～1012 engine qualification、macOS no-auth runtime、Windows supervision source、1011／1012 static release slices
- `status`: `passed-with-open-gates`
- `current_scope_limit`: 本 aggregate 僅承接 1003→1012；repository 另有後續 1013／1014 release evidence，故不將本 receipt 命名或解讀為 repository current terminal
- `database_boundary`: development `lu_test_*` evidence only；未操作 `union_db` 或 production

## Gate table

| Gate | Result | Accepted evidence／limitation |
|---|---|---|
| migration／engine version | `PASS` for this scope | baseline 1003；1004／1005 existing qualification plus 1006→1012 sequential schema-only qualification；每步 exact predecessor、source／candidate dump、fresh target、resume／verify與`backfills=[]` |
| qualification result | `PASS` for 1006→1012 | deterministic final evidence producer、strict qualification builder、canonical validator round-trip與各 release payload identity一致；無 generic DROP、seed、row backfill、reset、replacement或`--switch` |
| MySQL result | `PASS` for disposable evidence | representative preserve-data source→candidate→sequential apply→verify、fresh per-release bootstrap、canonical table count／stable fingerprint preservation與source re-read通過；只限隔離 `lu_test_*` |
| launcher/runtime result | `PASS` for macOS local slice | exact-1003 zero-child gate阻擋未升級 DB；current-1012 no-auth launcher啟動 FastAPI、React與required workers，health／proxy／Browser readback及owned cleanup通過；dry-run在無 Docker 時安全回 side-effect-free blocked |
| Windows-specific result | `PASS` for source contract; `NOT_RUN` for native runtime | PID／ParentPid／CreationDate lineage、required／optional worker survival、readiness、unknown cleanup與UTF-8 no-BOM writer通過 source／focused／fresh verification；原生 PowerShell與實體 Windows runtime未執行 |
| static release result | `PASS` for 1011／1012 in this scope | canonical manifest、descriptor、assembly、cutover catalog、builder與full-release freshness相互一致；不承接 repository 後續 1013／1014 evidence |
| blockers／exceptions | `BLOCKED` | 另一台實體 developer acceptance、Windows native runtime與其 own exact-1003 DB 尚未驗收；後續 1013／1014 evidence 仍是 separate current-chain boundary |
| final accepted state | `ACCEPTED_FOR_1003_TO_1012_SCOPE` | Task 96 此 bounded release-chain slice 的 engine／macOS runtime／source gates可重播且證據已收斂；整體 DB conclusion 仍為 `DB_CHANGE_NOT_READY` |

## Accepted invariants

- latest 與 ordered chain 只由 canonical manifests／descriptors 動態解析；只接受 continuous exact prefix，hole／partial／drift／unknown／qualification mismatch fail closed且零 DDL。
- 每個 release 依序備份、journal、apply、exact readback與replan；中斷從第一個 absent release resume，不重套成功 release；source／candidate row count、PK set與stable fingerprint必須一致。
- qualification builder 只接受同 release/artifact 的 strict final backup／fresh／preserve evidence，preview zero-write、publish atomic no-overwrite、validator round-trip；supporting evidence不升格為 qualification。
- launcher 的 current-schema gate 早於 API／UI／worker children；required child failure non-zero並清理本次 owned children；PID reuse、orphan與unknown不冒充已停止或完成。
- schema effects 僅為既有 release 的 schema-only change；system seed、business-row backfill、destructive change、production cutover與`union_db`操作均不在本 scope。

## Relevant verification and retained limitations

- Relevant checks：affected migration／qualification／launcher pytest suites、strict JSON／schema／descriptor validation、fresh bootstrap與preserve-data MySQL readback、resume／no-repeat negative probes、`bash -n`、PowerShell parser、UTF-8／BOM／header checks、Browser GET smoke與`git diff --check`。
- 1006～1012 qualification payload digests were verified by the builder；本 aggregate 只保留必要 digest／gate summary，不保存 raw dump、HTTP dump或scratch intermediate。
- macOS local no-auth runtime與Browser通過；另一台實體 machine 的 configured exact-1003 DB、Windows Browser與developer acceptance仍 `NOT_RUN`，因此不可宣稱 full cross-machine completion。
- 本 aggregate 不取代後續 1013／1014 release receipts，也不授權任何 manual ALTER、production migration、reset、replacement、`--switch`或 deployment。

## Canonical source set

本 aggregate 承接本批指定的 11 份 LDU slice receipts；其中 10 份已完成零引用審查並可移除，`ldu_hproj_rpre_static_release_receipt.md` 因受保護的 Task 97 production inventory 仍有直接 inbound reference 而保留。其餘原始檔案內容由 Git history 保留，active index與active Work Package只指向本 receipt；後續 1013／1014、HPROJ runtime與其他 release-specific evidence 保持原 owner／retention。
