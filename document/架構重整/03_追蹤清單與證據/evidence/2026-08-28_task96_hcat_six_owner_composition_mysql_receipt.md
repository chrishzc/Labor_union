# Task 96 HCAT six-owner composition and MySQL receipt

- 日期：2026-08-28
- Package：`PKG-HCAT-SIX-OWNER-COMPOSITION`
- 結果：`PASS`（source／focused／真 MySQL negative）；adopted-positive與projector/runtime為`NOT_RUN`。

## 1. 已完成契約

- Orders、Matching、Contract Signing、Client Finance、Scheduling、Staff Payables六adapter以同一
  caller-borrowed connection組成`HistoricalBaselineOwnerVectorV2Query`。
- exact六owner set、catalog-v2 21 descriptors、deterministic read order、locked/unlocked propagation、
  Scheduling-only BusinessClock injection與typed vector error propagation均固定。
- composition不begin／commit／rollback／close，不攔截owner/vector錯誤，不產生partial projection。

## 2. Fail-before-fix

第一次真MySQL mixed readback揭露Staff Payables obligation v2與projection v1共用raw
`source_event_identity`，觸發`historical_baseline_v2_source_version_drift`。Adapter修正為
`kind + raw identity` typed event identity；同typed source不同version仍由vector拒絕。

## 3. Static／fresh verification

- 主代理六owner final suite：`174 passed`；Staff event fix regression：`100 passed`。
- composition fresh Luna/high：focused `8 passed`、cross `121 passed`、adversarial
  `20 passed, 26 deselected`，P0=0、P1=0、P2=0。
- final MySQL verifier static/focused：`155 passed`；`py_compile`、strict UTF-8、diff／whitespace：`PASS`。

## 4. 真 MySQL readback

| Target | Gate | Result |
|---|---|---|
| `lu_test_task96_scenarios_20260827` | existing owner-data mixed readback | 21 collections／36 observations；25 available、11 typed unavailable；current／earliest=1；fingerprint 64；無unknown table/column/read_failed。此DB缺1010 baseline prerequisite，不能稱canonical-current。 |
| `lu_test_task96_ldu_candidate_1012_r1` | canonical-current schema negative | 21 collections／21 observations；全部typed unavailable；current／earliest=1；fingerprint 64；無unknown table/column/read_failed/source drift。fresh verifier P0/P1/P2=0。 |

兩個target均在連線前後回讀`APP_ENV=development`、exact database與`lu_test_*` allowlist；只使用
diagnostic-only provenance，不宣稱adopted，caller完成close，零DB mutation。`.env`原target為
`union_db`，全程未連線或操作。

## 5. Remaining gates

adopted-positive H-01～H-06 scenario、projector repository/worker、API、React、no-auth Browser與legacy
recovery仍未完成。本receipt不授權直接植入derived roots，不把全部unavailable或mixed readback冒充人工修復閉環。

未使用Graphify，也未stage／commit。
