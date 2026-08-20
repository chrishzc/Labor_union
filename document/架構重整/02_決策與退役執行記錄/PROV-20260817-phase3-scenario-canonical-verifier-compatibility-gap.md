---
doc_type: gap-package
declared_status: superseded
identity: PROV-20260817-phase3-scenario-canonical-verifier-compatibility-gap
date: 2026-08-17
owner: Global Validation Governance Integration Owner
domain: Global / Verification Baseline / Phase 3 Scenario Lineage
priority: P0
source_work_package: PROV-20260817-react-admin-phase3-scenario-lineage-governance
successor: PROV-20260817-phase3-scenario-canonical-verifier-compatibility-amendment-work-package
---

# Phase 3 Scenario canonical verifier 相容性缺口

## Business scenario and impact

`verification_gate_report` 是建立 disposable MySQL schema 前的唯讀契約門。它必須先能載入並區分
既有 dual-track baseline 與 Phase 3 lineage metadata，否則 bootstrap 會在任何 database connection
之前失敗，無法判斷真正的 DB gate 狀態。這是驗證治理缺口，不是資料庫變更授權。

## Fresh evidence (2026-08-17)

以下命令在目前 worktree 執行，均為唯讀；未建立、覆寫或連線任何資料庫：

```powershell
.\.venv\Scripts\python.exe -m scripts.verification_gate_report
```

初次結果曾為非預期 traceback：

```text
scripts/verify_verification_fixtures.py:31
scenario["scenario_id"]: set(scenario["test_kinds"])
KeyError: 'test_kinds'
```

Phase 3 metadata writer其後已在核准的scenario檔補齊canonical scenario必需欄位；fresh
`scripts.verify_verification_scenarios`現為`valid: true`，上述`KeyError`不再重現。這不代表本gap已關閉：
完整`verification_gate_report`仍為`contract_valid: false`，且loader的namespace相容性問題已轉為
可診斷但未解決的nested fixture discovery缺口。

另有兩個獨立但同一門禁的漂移：

1. `validation/fixtures/phase3/*.json` 與 `validation/expected/phase3/*.json` 位於子目錄，但
   `load_fixtures()` 只使用 `validation/fixtures/*.json`；fresh report因此誤報7個Phase 3 track-A
   scenario缺fixture。
2. Phase 3 fixture／expected 的欄位形狀是 lineage metadata contract，不能直接當作 baseline
   fixture／expected contract。若只把 `glob` 改成 `rglob` 而不做 contract-aware partition，會把
   相容性問題從「漏載入」變成「錯誤解讀」。
3. fresh report另列14個既有receipt input digest stale；它們不是Phase 3 metadata writer可重算或
   覆寫的證據。compatibility修訂必須分開呈現此既有receipt drift，不得以重產receipt讓report假綠。

## Safety finding

目前 `scripts/bootstrap_disposable_mysql_schema.py` 的 `_require_validation_gate()` 會先呼叫
`build_gate_report()`；先前失敗發生於任何DB connect/create之前，本輪沒有database created。依最新
人工裁決，本gap及successor均不建立DB，只修唯讀validator；任何修復不得吞例外、跳過Phase 3 assets、
把malformed shape當空集合，或把metadata-ready當runtime receipt。

## Required disposition

建立一個獨立的 docs-approved successor Work Package，修復 loader／validator 的 contract-aware
相容性，並以 negative tests 證明：recursive discovery、duplicate identity、dangling path、
unsupported shape 與 schema family 混用都 fail closed。修復前本 gap 維持 `proposed`；不可宣稱
Phase 3 runtime、DB 或 browser 完成。

## Out of scope

- 不建立、重設、升級或連線 `union_db` 或任何 disposable MySQL database。
- 不修改 production API、React、Domain、schema、migration、fixture內容的業務語意或 receipt結果。
- 不產生 runtime PASS、browser PASS 或偽造 bootstrap receipt。
- 不修改 shared `02/README.md`；由 Integration Owner 在核准並施工後另行做 index delta。

## Proposed successor

`PROV-20260817-phase3-scenario-canonical-verifier-compatibility-amendment-work-package.md`

Successor已於2026-08-17取得exact核准並完成；本gap標為`superseded`。14筆既有stale receipt digests
仍是獨立evidence debt，不回捲成本相容性修訂失敗。原Approval phrase為：

> 核准此 exact Phase 3 Scenario Canonical Verifier Compatibility Amendment Work Package
