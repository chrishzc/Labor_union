# Task 96 HCAT／RPRE Spec Pipeline correction receipt

- `date`: 2026-08-28
- `scope`: H owner source-map／catalog cardinality；R concrete persistence contract
- `authority`: 既有 Task 96 H/R 採用裁決與正式 owner specs
- `side_effects`: 文件更新；0 DB mutation、0 provider、0 production、0 Graphify

## 結果

| Slice | Status | Result |
|---|---|---|
| R request／Matching successor／root descriptor／replay contract | `passed` | 已補入 R spec §9 與 task pack §7，維持 `SPEC_READY / PACKAGE_READY`；不需新 DDL 或人工裁決。 |
| H Steps 1～11 owner/source map | `passed` | 已比對正式規格、live schema 與 typed readbacks；確認 v1 catalog 有 owner/cardinality live-drift。 |
| H catalog-v2 amendment | `blocked` | proposed bundle 已寫入 H spec §9 與 task pack §8；因改變 persisted/public catalog contract，等待人工採用。 |
| Implementation | `not_run` | H 在採用前不得實作；R concrete persistence 由獨立 writer 執行。 |

## H 必要修正證據

- Step 3 candidate contact 的 root owner 是 Scheduling／Matching，LINE 只負責 delivery。
- Step 5 customer decision 的 root owner 是 Matching Coordination，Orders 只消費 projection。
- Step 9 confirmed service dates 的 root owner 是 Scheduling。
- Step 6／8／10／11 需要同一步多 descriptor／多 observation；壓成單一 scalar source version
  會遺失 owner vector，無法安全做 stale／successor／terminal readback。
- 1011 的 descriptor／observation schema 預期可容納同一步多 occurrence；採用後先以 static contract
  test 驗證，不預先新增 migration。

## R 已收斂契約

- scenario／reason／evidence 由 request context 提供；repository 用 current owner roots 驗證，
  不從 DB 猜 operator intent。
- Matching successor 在同一 outer UoW 建新 rematch package lineage 與
  `package_proposed` event；`rematch_required` 不能冒充完成。
- root descriptor、canonical ordinal、`sha256_newline_v1` digest/count 與 replay readback
  必須由 relation rows 機械核對。

## 驗證

- 前置 H/R domain／workflow／schema focused suite：`68 passed`。
- 四份 spec／task-pack 文件 strict UTF-8：`passed`。
- 文件 `git diff --check`：`passed`。

## 狀態限制

H catalog-v2 未採用前固定 `BLOCKED_AUTHORITY`；不得讓 adapter 自行更換 owner、壓縮 source
vector 或填 placeholder capability。R 只可在 task pack §7 write set 內施工。另一台實體電腦的
Developer acceptance 仍 `not_run`，整體 DB 結論維持 `DB_CHANGE_NOT_READY`。
