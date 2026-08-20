---
doc_type: work-package
declared_status: completed
identity: PROV-20260817-phase3-scenario-canonical-verifier-compatibility-amendment-work-package
date: 2026-08-17
owner: Global Validation Governance Integration Owner
domain: Global / Verification Baseline / Phase 3 Scenario Lineage
source_gap: PROV-20260817-phase3-scenario-canonical-verifier-compatibility-gap
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance completed with PHASE3_SCENARIO_LINEAGE_METADATA_READY; no DB authorization
approval_required: 核准此 exact Phase 3 Scenario Canonical Verifier Compatibility Amendment Work Package
base_head: 8615225481c8f72a9629289285516189b270cb36
dirty_baseline: integration-owner-must-capture-before-writer
---

# Phase 3 Scenario Canonical Verifier Compatibility Amendment 工作包

## Activation record

使用者已於2026-08-17明確回覆：

> 核准此 exact Phase 3 Scenario Canonical Verifier Compatibility Amendment Work Package

本包已進入`in-progress`；仍嚴格維持0 DB、0 browser、0 provider與0 production mutation。

## Objective

讓 canonical verification gate 能在同一 repository 安全辨識並驗證兩種既有資產：

1. dual-track baseline 的 root scenario／fixture／expected contract；
2. Phase 3 scenario lineage metadata、`validation/fixtures/phase3/` 與
   `validation/expected/phase3/` 的 metadata contract。

Loader 必須可遞迴發現應納入的資產，但不得將不同 contract family 強制解碼成另一 family，也不得
靜默忽略 malformed、duplicate、dangling 或 unsupported shape。canonical gate 必須輸出可診斷的
errors，而不是 `KeyError` 或未宣告的成功。

## Exact write set

唯一 Integration Owner 可修改 shared/index 類檔案；本工作包的候選 write set 如下，未經核准不得修改：

- `scripts/verify_verification_fixtures.py`
  - 以 contract-aware recursive discovery 載入 root 與 nested fixture assets；
  - duplicate scenario identity、duplicate path、dangling expected manifest 與 unsupported
    contract/shape 必須回報可讀錯誤並 fail closed；
  - 不把 Phase 3 metadata fixture 當作 baseline root fixture。
- `scripts/verify_verification_scenarios.py`
  - 若 live contract 需要，加入 schema-family partition、shape guard 與 deterministic errors，
    避免 root Phase 3 lineage artifact 造成 `KeyError`；
  - recursive discovery 不得以「發現數量」自動產生 expected set。
- `scripts/verification_gate_report.py`
  - 將 baseline validation 與 Phase 3 metadata validation 分開呈現；
  - canonical command 必須可完成報告輸出，無未捕捉例外；任何錯誤仍使對應 gate 不通過。
- `tests/test_verify_verification_baseline.py` 或新增同一 bounded validator 的 focused test file
  - 保留既有 baseline assertions，補足 nested discovery、duplicate identity、dangling path、
    unsupported shape、contract-family mixing 與 malformed required-field negative tests。
- `tests/test_phase3_scenario_lineage.py`
  - 只在需要共用 loader/validator contract 時補 deterministic compatibility assertions；
  - 不把 metadata-ready 升格為 runtime、DB 或 browser PASS。
- `validation/scenarios/` 中被 canonical discovery 掃描到的 Phase 3 exact scenario files，僅在
  live verifier 選擇「統一 recursive canonical loader」且證據證明需要時修改；不得刪除、改 ID、
  改 source lineage 或改成假 runtime receipt。
- `validation/fixtures/phase3/` 與 `validation/expected/phase3/` 的 exact Phase 3 files，僅在
  shape contract 需要補最小 metadata 欄位且有對應規格證據時修改；不得填入 actual、observed、
  runtime receipt 或 PASS。
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-phase3-scenario-canonical-verifier-compatibility/`
  下的 verification receipt、candidate-change-inventory、open-findings（由 Integration Owner
  在實作後建立；不在本 docs-only proposal 中預填）。

Shared `README.md`、`02/README.md`、Part 00 canonical source、production code、DB schema/migration、
React、API routes、receipt registry 與任何已存在的使用者 dirty path 均不在本次 proposal 的寫入範圍。

## Contract rules

1. Discovery 可使用 `rglob("*.json")`，但必須先依明確 `contract`／path namespace partition；
   不得以單一 `list[dict]` 混合 baseline 與 Phase 3 lineage shape。
2. 每個 contract family 的 expected identity set 必須獨立且固定；發現多餘、重複、未引用或
   dangling asset 必須 fail closed。
3. 缺少 required field、wrong primitive、wrong contract、unexpected shape 必須產生 deterministic
   validation error；不得因 `.get()` 或例外吞掉而變成 valid。
4. Phase 3 fixture 的 `expected_manifest_path` 必須在其 namespace 內可解析；baseline fixture
   仍必須依 baseline contract 驗證。跨 namespace 引用必須明確拒絕或列為 error。
5. `verification_gate_report` 的輸出可同時含 `valid: false`、blocked reason 與各 family errors，
   但程序本身不得 crash；bootstrap gate 只能依 errors 阻擋，不能繞過。
6. 不得把 `metadata-ready`、validator通過或 preflight 可繼續轉寫成 runtime receipt；所有 runtime
   receipt 初始狀態仍限 `missing | not_run | blocked`。

## Acceptance gates

| Gate | Required evidence | Pass condition |
|---|---|---|
| G0 Scope | candidate-change-inventory | 僅 exact write set；0 production／0 DB；無 shared README 競寫 |
| G1 Canonical no-crash | `.\.venv\Scripts\python.exe -m scripts.verification_gate_report` | 程式正常結束並輸出JSON；現有stale receipt等合法gap以errors呈現，不是traceback |
| G2 Baseline compatibility | focused baseline tests | 既有 root baseline contract 維持原語意與 coverage；無 Phase 3 shape 污染 |
| G3 Recursive discovery | focused tests | nested `phase3` assets 被明確納入其 family；root 與 nested duplicate identity fail closed |
| G4 Negative contract tests | focused tests | dangling、missing required field、wrong primitive、wrong contract、unknown family、cross-namespace reference 均 fail closed |
| G5 Bootstrap preflight | 唯讀呼叫 `_require_validation_gate`／等價 preflight | 可判斷DB gate並輸出明確blocked reason；本包不建立或連線任何DB |
| G6 Anti-fake evidence | receipt/open-findings scan | 0 actual/observed/runtime PASS payload；receipt 只記錄真實命令與結果 |
| G7 Hygiene | strict UTF-8/BOM、secret/PII、`.skip/.todo/.only`、`git diff --check` | 全數通過；不觸碰既有 dirty paths |

## Required verification protocol

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --basetemp .pytest_tmp\phase3-verifier-compat -q tests\test_verify_verification_baseline.py tests\test_phase3_scenario_lineage.py
.\.venv\Scripts\python.exe -m scripts.verification_gate_report
```

若 canonical report 仍有合法的 baseline／Phase 3 gap，必須輸出 JSON errors；不可用 fixture、mock、
舊 receipt、既有 `union_db` 或手工刪檔使它看似通過。本工作包禁止建立或連線任何DB、啟動
provider/browser或執行production mutation。

## Completion boundary

最高輸出為 `PHASE3_CANONICAL_VERIFIER_COMPATIBILITY_READY`，意義是驗證器能安全載入、分區並回報
contracts；不代表 Phase 3 backend、React、DB、browser、provider 或 runtime receipt 完成。若缺少
disposable MySQL 環境，DB engine gate 仍須維持 `BLOCKED`，整體不可宣稱 `DB_CHANGE_READY`。

## Completion record（2026-08-17）

Luna MAX完成contract-aware nested discovery與report分區；Integration Owner fresh重跑baseline＋Phase3
focused suite為`51 passed`。canonical report可正常輸出JSON，baseline／scenario／fixture／phase3_lineage
errors皆為0；14筆既有stale receipt digests仍分開fail-closed，未重算或改寫。本包輸出為
`PHASE3_CANONICAL_VERIFIER_COMPATIBILITY_READY`。

## Approval and handoff

本工作包已取得exact核准並完成；source gap與evidence由Integration Owner同步。它不構成React query、
DB、browser或mutation的通用前置。
