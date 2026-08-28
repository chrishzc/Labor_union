# Anomaly Rulebook Auto-resolution Guard Receipt

- 日期：2026-08-27
- Current item：`CUR-ANOMALY-MANUAL-REMEDIATION-01`
- Scope：42-code canonical registry 的自動解除發布門、legacy import-warning 旁路、已確認的
  IMPORT-006／PAYOUT-001／Client Settlement predicate drift
- Authority：`06_Anomalies_Domain.md`、各 code 在
  `2026-08-27_anomaly_rulebook_oracle_matrix.md` 引用的 owner 正式規則書
- DB／schema write set：無；未啟動 Docker、FastAPI、Vite 或 MySQL

## Result

| 驗證項目 | 狀態 | 證據 |
|---|---|---|
| 42-code coverage | passed | current registry=42；rulebook allowlist=10；fail-closed=32；兩集合互斥且聯集完整；`IMPORT-004` 依後續 multi-occurrence package 加入 |
| 無規則書 contract 不得自動解除 | passed | `tests/test_anomaly_rulebook_auto_resolution_guard.py`；既有 active 保持 active，tracking resolved 會 reopen |
| fail-closed detail 一致性 | passed | generic projector 保留上一份 actionable snapshot；finance projector 保存 active root 與 contract-missing reason |
| 已確認 owner terminal 可解除 | passed | `GOVSUB-003` 正向 oracle；contract 同時保存 rulebook reference、terminal predicate、version |
| IMPORT-006 duplicate integrity | passed | duplicate-only mismatch 使 `integrity_inconsistent_count=1` |
| PAYOUT／Client status drift | passed | positive current balance/remaining 即使標成 settled/completed 仍 active |
| legacy warning contract isolation | passed | unknown predicate、跨 logical code 均在任何 tracking write 前失敗 |
| HCM current owner readback | passed | event／prior occurrence／case／client／review binding或current root fingerprint任一不一致即拒絕auto-resolve |
| HCM review aggregate | passed | 同 review occurrence 逐筆解除；3→2→1仍 active，0 才 inactive；tracking close、缺 task／alert或同 review 亂序皆 fail closed |
| focused regression | passed | fresh-root／registry integration 50 passed；PAYOUT＋Client cross-lane verification 45 passed |
| import-warning guard | passed | 已納入上述 focused 59 tests，含跨 event／occurrence／case／client／review binding 負例 |
| broad anomaly/warning/reminder/historical regression | passed | 373 passed, 18 skipped in 4.22s |
| Python compile／patch／encoding | passed | 9個本輪production Python files與3個主要新增測試`compileall -q`；`git diff --check`；17檔strict UTF-8 |
| Luna High E3 independent verification | passed | PAYOUT＋Client四碼current cross-lane verification：45 passed，P0/P1=0；Historical verifier未收斂並中止，不列PASS且不在白名單 |
| MySQL／API／Browser runtime | not_run | 使用者已說明本機服務與 DB 尚未啟動；本包沒有啟動或建立資料 |

## Business-rule reconciliation

本輪一度依 live-risk 摘要提出「GOVSUB-004 只能全額 reversal」與「GOVSUB-006 remaining=0 才解除」，
但逐條回讀 `14_Government_Subsidy_Domain.md` 後撤回：單一 allocation 的 partial reversal可合法且無歧義；
GOVSUB-006 的異常終點是 authorized offset／return disposition已提交。其後專項稽核再區分「合法 owner 操作」
與「足以解除特定 alert 的正式契約」：GOVSUB-004仍缺後者，因此撤出白名單，並非否定 partial reversal合法性。

## DDH topology record

初始投影為 E4 三條 read-only owner-family lanes，實際成功建立兩條，且均明確使用
`gpt-5.6-luna`／`high`；第三條由 Host thread quota 拒絕。reconciliation 如實保存 2 completed／1 blocked，
隨後提交 capability delta，將剩餘工作動態重投影為 E2 主代理單寫整合。未發生競寫，也未把未啟動 lane
計為多代理成果。scratch lifecycle／plan／reconciliation artifacts 位於 ignored
`scratch/task96-auto-resolution-rulebook/`。

candidate freeze 後沿用既有 `gpt-5.6-luna`／`high` agent 做 E3 read-only verification。第一輪回報包含
stale source 判讀，並把 GOVSUB alert predicate 與 successor remaining terminal 混為一談；要求 fresh recheck
current filesystem 與 `14` 後，第二輪 `PASS`、P0/P1=0。P2 的 exact allowlist coverage observation已修正。
final-delta round 3 曾對當時14-code candidate得到`PASS`。後續兩條新的Luna/high owner-family稽核找到：
Historical、LINE、PAYOUT、IMPORT-006與Client三種逾期的fresh-root/version競態，以及GOVSUB-004 alert binding
仍為SPEC_GAP。這些material evidence使舊PASS失效；計畫由E4唯讀稽核動態切回E2單一writer，當時白名單收斂為5碼。
其後E4三條互斥Luna/high writer分別處理Historical、PAYOUT、Client；PAYOUT與Client四碼完成locked owner
readback與daily-root版號後，由非原writer的cross-lane verifier確認45 passed、P0/P1=0，current白名單增為9碼。
Historical全snapshot候選因可能阻擋合法後續Orders進展，且兩次verifier未按監控期限收斂，固定不列PASS／不進白名單。

後續 `IMPORT-004` 同 review 3→2→1→0 aggregate package 已以 Luna High E3 獨立驗證無
P0／P1，current candidate 因此為10碼白名單；詳見
`2026-08-27_hcm_multi_occurrence_umbrella_resolution_receipt.md`。

## Completion boundary

本 receipt 只證明自動解除的發布門與本輪明列 predicate 修正；不代表 42 codes 的人工
Query／Preview／Apply 都已完成。所有 `SPEC_GAP`／`AUTHORITY_GAP` codes 仍須依 owner 規則書逐碼完成
人工修正入口與 runtime acceptance，current item 維持 `in-progress`。
