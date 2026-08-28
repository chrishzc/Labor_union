# Task 96 HCAT Matching owner adapter receipt

- 日期：2026-08-28
- Package：`PKG-HCAT-ADAPTER-matching`
- 結果：`PASS`（source／focused）；六 owner 同 connection 真 MySQL integration 為 `NOT_RUN`。

## 1. 已完成契約

- Step 2～5、Step 8 只接受 catalog-v2 Matching descriptors；earliest `candidates_added`、latest
  contact／willingness、current accepted selection、matching plan與caregiver binding使用正式 persisted lineage。
- plan segment 透過 parent `plan_id` 取得 case，不查不存在的 segment `case_no`；package 讀取並驗證
  `source_version_tuple`，criteria numeric FK 對 criteria row identity。
- customer decision 使用正式 `cross_domain_request.candidate_id`；較新的 rejected／disagree decision
  會使舊 accepted decision stale，不會錯誤維持 terminal。
- Step 4 遵守 descriptor max=1；多候選且無唯一 current selection 時 fail closed。`candidates_added`
  payload IDs 必須與 pool exact 相等；source tuple typed fields、versions與fingerprints均嚴格驗證。
- adapter 使用 borrowed connection，locked mode 傳遞 `FOR UPDATE`，不 begin／commit／rollback／close。

## 2. Fail-before-fix 與驗證

- 第一輪 fresh verifier：P0=0、P1=5、P2=2；揭露 schema欄位、package tuple、criteria FK／payload、
  cardinality、stale decision、candidate exactness與typed tuple缺口。
- 最小修正後主代理 cross regression：`107 passed`。
- 第二輪 fresh Luna/high：focused `11 passed`、cross-check `64 passed`、real-shaped probes `7/7 PASS`，
  P0=0、P1=0、P2=0，`changed_files=[]`。
- `py_compile`、strict UTF-8、`git diff --check`：`PASS`。

## 3. Remaining gate

本 receipt 只完成 Matching concrete source slice。六 owner adapters 的 dependency composition、同一
borrowed connection／lock integration、真 `lu_test_*` readback、projector、API、React 與 no-auth Browser
仍須另行驗收；不得由本結果外推 HCAT umbrella 完成。

本輪未修改 schema／migration、未操作 DB／port／Browser、未使用 Graphify，也未 stage／commit。
