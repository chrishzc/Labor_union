# Task 96 HCAT／RPRE aggregate final receipt

- `date`: 2026-08-28
- `scope`: HCAT catalog-v2 domain／vector／six-owner composition／concrete adapters，以及 RPRE domain／QPA／persistence／API／projector／runtime slices
- `status`: `passed-with-open-gates`
- `authority`: current formal Global／Domain contracts、HCAT adopted catalog-v2 decision、RPRE approved owner-successor contract與其 task packs
- `database_boundary`: 僅隔離 `lu_test_*` development evidence；未操作 `union_db`、production、provider 或 deployment

## Summary

本 receipt 收斂 HCAT／RPRE 同一 initiative 的 domain、subsystem、adapter、persistence、API contract、projector 與 no-auth runtime evidence。它保留各 slice 的 accepted invariants、owner boundaries、failure semantics、驗證結果與未完成 gate；不把單層 source、negative readback 或局部 runtime evidence 升格為整體完成。

## Current authority and accepted contract

- HCAT 的 catalog-v2 是 current adopted authority：每一步可有多個 owner descriptor，每個 descriptor 可有多筆 typed observation；完整 21 descriptors、owner identity、source event／version、cardinality、all-required predicate 與 whole-vector fingerprint 必須精確保留。v1 compatibility 只供既有相容入口，不得讓 scalar 或 placeholder 冒充 v2。
- HCAT owner boundary 固定為 Orders、Matching、Contract Signing、Scheduling、Client Finance、Staff Payables；Scheduling 擁有 effective generation／official service facts，Orders 擁有 lifecycle／completion，Matching 擁有 candidate／decision／plan，Contract Signing 擁有 external report／document lineage，Finance owners 各自擁有 settlement roots。owner adapter 不得換 owner、猜資料或建立 derived root。
- RPRE 是 Scheduling-owned service-before-replacement successor flow。Query／Preview 零寫入；Apply 重新鎖定 fresh owner facts，在單一 outer Unit of Work 建立 successor lineage、receipt 與 outbox，並以 canonical root delta／fingerprint／fresh readback 對帳。actual-service proof 只能導向 substitution referral，不得建立 replacement。
- 所有 adapters 使用 caller-borrowed connection；locked read 傳遞 `FOR UPDATE`，adapter／repository／composition 不 begin、commit、rollback 或 close。commit 後 readback 不明確時回 `outcome_unknown`，不得回滾已提交 transaction 或偽造成功。
- identity、source tuple、expected version、reason／evidence、root set、receipt／outbox lineage、same-key replay 與 cross-case／stale／malformed／ambiguous input 均 fail closed；legacy manual Contract Signing recovery 的 fingerprint 缺口仍回 typed unavailable，未授權補洞。

## Covered owner and adapter results

| Slice | Accepted result | Verification | Remaining boundary |
|---|---|---|---|
| HCAT domain／catalog-v2／vector | 21-descriptor owner map、multi-observation collection、v1 compatibility、deterministic fingerprint與typed referral通過 | domain／vector／boundary focused suites、random permutations、fresh Luna/high；P0/P1/P2=0 | concrete positive runtime、projector與完整 HCAT scenario仍未完成 |
| HCAT six-owner composition | 六 owner 同一 borrowed connection、lock mode、read order與typed error propagation通過；Staff event identity drift已修正 | static/focused `174 passed`；fresh composition與cross suites、MySQL negative/mixed readback通過；P0/P1/P2=0 | adopted-positive、projector、API／React、另一台 developer acceptance 未完成；compact schema 的 Staff Payables live-drift 保留 |
| HCAT concrete adapters | Orders、Matching、Staff Payables、Client Finance、Contract Signing 與 Scheduling 的 owner-specific root／lineage／cardinality rules通過 | 各 adapter fresh focused／cross／adversarial suites通過；P0/P1/P2=0 | 六 owner full positive integration 尚未由 HCAT receipt 宣稱完成 |
| RPRE domain／subsystem／persistence | exact R-01～R-04／R-07 roots、Matching successor、generation transition、receipt／outbox與same-key replay通過 | parent／cross regression、fresh Luna/high、strict compile／UTF-8／diff checks通過 | projector／API／React 的完整 production-loader adoption仍受各自 gate 控制 |
| RPRE MySQL／runtime | 隔離 development `lu_test_*` positive readback與replacement lineage exact；R-01／R-03／R-04／R-07 no-auth Browser chain完成，actual-service referral回409且零寫入 | MySQL readback、replay、rollback rehearsal、React build與true Browser均通過；P0/P1/P2=0 | 只代表受控 scenario；不代表 production、provider、另一台 developer 或 anomaly-wide completion |

## Persistence／API acceptance

- RPRE persistence verified generation／aggregate／event transition、retained／superseded／created root sets、Matching numeric FK、immutable receipt與post-commit outbox；source／candidate snapshot drift、missing prior effective generation、cross-case、duplicate與incomplete lineage均在首次 insert 前拒絕。
- RPRE API authority 已由人工核准，沿用既有 capability；public typed contract 僅接受 closed scenario／reason／evidence vocabulary，success/error envelope strict，incomplete readback固定為 typed `503 replacement_source_unavailable` 或 `outcome_unknown`，不得把 `rematch_required` 當 terminal success。
- HCAT MySQL composition 的已驗證 target 包含既有 mixed owner-data readback與 canonical-current negative；因 adopted-positive HCAT scenario、projector與完整 runtime 尚未完成，aggregate 不宣稱 HCAT end-to-end PASS。

## Rollback, limitations and verification commands

- 所有 positive DB evidence 均限定 development `lu_test_*`；未執行 schema／migration、seed、backfill、reset、`--switch`、`union_db`、production 或 provider side effect。
- 未提交 transaction 的 diagnostic work 已 rollback；已提交 immutable scenario rows、receipt、outbox、owner history 與 source evidence 依其保留責任保存，不可用 DELETE 作 cleanup。
- 另一台實體 developer acceptance、部分 HCAT positive integration、完整 HCAT projector／API／React acceptance、Contract Signing legacy recovery 與 production/provider acceptance 仍 `NOT_RUN`／`AUTHORITY_REQUIRED`。
- Reproducible checks retained by this aggregate：affected focused `pytest` suites（pytest cache disabled、temporary basetemp）、Python compile／strict UTF-8／structured-header checks、adversarial root／cardinality／replay probes、MySQL read-only owner readback、React TypeScript／build、true FastAPI＋Browser Query／Preview／Apply、以及 `git diff --check`。

## Canonical source set

本 aggregate 取代本 initiative 的 20 份同系列 slice receipts；原始檔案內容由 Git history 保留，active index、active Work Package 與本任務報告只指向本 receipt。未列入本 aggregate 的 HPROJ／1013／1014 後續 evidence 仍維持原檔與原 owner，因其代表不同 release／source-contract boundary。
