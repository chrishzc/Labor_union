# CLIENTREFUND-001 客戶退款退匯異常人工修正規格

- 狀態：`approved`
- convergence：`SPEC_READY`
- Authority：使用者要求所有異常具人工修正，且自動解除必須依真實業務規則書；本規格只收斂既有正式退款退匯流程。
- 範圍：`CLIENTREFUND-001`；不涵蓋一般退款少退、補助退還、receipt reversal 或 generic Finance correction。

## 1. 真實業務情境與 owner

銀行已把一筆先前客戶退款退回，Finance Import 取得 canonical incoming bank fact；人員需確認它精確對應仍有效的原 `refund` ledger entry，再由 Client Finance append `refund_reversal`，重開原退款義務。Finance Import 只擁有 intake／classification／correction orchestration；Client Finance 是 refund ledger、reversal target、金額、case、progress 與 transaction 的唯一 owner。

異常頁不能直接 UPDATE ledger/projection，也不能用 tracking resolve 代替 reversal。若 incoming bank row、原 refund entry 或對應 case 不唯一，異常保持 active，交由人員選定合法 root facts後走正式 Preview／Apply。

## 2. 規則書 predicate

### 2.1 Active

`CLIENTREFUND-001` identity 固定由 canonical Finance Import row與原 refund ledger entry組成。當 review已確認這是一筆退款退匯候選，但尚無下列 exact formal reversal 時保持 active：

- reversal `entry_type='refund_reversal'`；
- `reversal_of_entry_id` 指向該仍有效的原 `refund` entry；
- reversal `finance_import_row_id` 指向該 canonical incoming bank row；
- reversal與原 refund為同一 case、金額精確相等；
- Client Finance formal workflow已提交並可fresh readback。

review receipt、Finance correction receipt、job/outbox成功、row被分類、tracking close或任一其他 reversal都不等於解除。

### 2.2 Detail

日常 detail 至少顯示：Finance Import row identity、batch identity、原 refund ledger identity、受影響case／obligation identities、current blockers、reason codes、root condition及source version。技術alert fingerprint可留稽核但不作人工輸入。不得只顯示「退款退匯待處理」。

### 2.3 Terminal completion

只有 fresh query證明 §2.1 exact formal reversal成立，並由同一 `CLIENTREFUND-001` projector重算 `active=false`，active anomaly list已無原 fingerprint，UI才可顯示「異常已解除」。formal job receipt只能顯示「帳務更正已提交，正在重新核對來源」。

stale target/version必須重新Query／Preview；timeout或結果未知以原idempotency key查job/receipt及owner root，不得產生第二命令。readback unavailable或alert仍active時提供重新核對入口，不得卡死。

## 3. Exact action contract

| 欄位 | 值 |
|---|---|
| code | `CLIENTREFUND-001` |
| intake owner | `finance_import` |
| ledger owner | `client_finance` |
| action key | `classify_client_refund_return` |
| form schema | `finance_import.correction.v1` |
| source bindings | `finance_import_row_identity`, `source_version` |
| operator inputs | `evidence`, `reason`, `refund_ledger_entry_identity`, `target_obligation_identities` |
| preview | `PreviewCorrectAndPostClientRefundReturn` |
| apply | `CorrectAndPostClientRefundReturn` |
| capability | `finance_import.correct_and_post` |
| completion | `client_refund_return_cleared` |
| contract version | `1` |

`finance_import_row_identity` 必須是實際 `finance-import-row:<positive id>`，不得誤用 synthetic alert source identity `finance-import-refund-return:<row>:<ledger>`。原 refund ledger與obligations來自current root snapshot並由人員核對，Preview再由owner驗證；缺任一 binding/detail即不提供action。

## 4. Q/P/A 與負向 oracle

正式流程 reuse既有 Finance Import correction：

1. Query anomaly current detail/root；
2. Preview固定classification=`client_refund_return`，選 exact incoming row、原 refund ledger、target obligations、reason/evidence；Preview零寫入；
3. 人工確認後Apply；Finance Import outer job在正式composition中呼叫 Client Finance refund-return Preview/Apply；
4. terminal receipt後重查owner reversal與原alert predicate；只有alert absent才完成。

必須保持active的反例：wrong/used/outgoing bank row、原entry非refund或已reversed、wrong case、amount mismatch、partial／over reversal、wrong target、stale、same-key different payload、queued/running、receipt-only、outbox delivered、readback failure。

## 5. Acceptance

- `CRR-A1`：detail具體顯示row/batch/original refund/case-obligation/blockers，不再空白。
- `CRR-A2`：recovery action綁定actual row identity，而非synthetic alert identity；缺失、型別、owner或source drift fail closed。
- `CRR-A3`：Preview固定purpose且零寫入；Apply只透過既有formal Finance Import→Client Finance composition。
- `CRR-A4`：fresh exact reversal後alert才inactive/absent；receipt-only與alert仍active時UI不顯示解除。
- `CRR-A5`：stale、queued/running、timeout/unknown、wrong result/readback failure都有可恢復入口且不重複mutation。
- `CRR-A6`：existing unit/API/React/disposable-MySQL positive與negative regression PASS；真服務未啟動時runtime標`NOT_RUN`。

## 6. Effect ceiling與DB inventory

- 允許：registry/display allowlist、root action binding、fresh reversal guard、React reconciliation copy/tests/docs；受控 `lu_test_*` runtime。
- 禁止：schema/migration/seed/backfill、直接ledger UPDATE、generic resolve、bank/provider side effect、`union_db`、production、replacement/`--switch`。
- DB inventory：schema-only/system-seed/business-row-backfill/destructive均`none`；若diff出現DB變更即停止重走DB gate。

## 7. Traceability

| Requirement | Formal source | Live reuse |
|---|---|---|
| refund return/reversal root | `16` §§3.2、3.4–3.6 | Client Refund Reversal Domain/workflow/repository |
| canonical bank fact/no provider command | `16` §§1、3.6 | Finance Import correction |
| anomaly owner recovery/fresh recheck | `06` Human-assisted Recovery | root fact projector/consumer |
| strict Q/P/A/idempotency | Global Q/P/A、`16` §3.4 | correction job/client/UI |

Convergence result：`SPEC_READY`，unresolved material decision：`none`。
