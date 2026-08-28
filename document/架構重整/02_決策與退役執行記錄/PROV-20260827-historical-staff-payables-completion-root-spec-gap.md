# Historical Staff Payables case completion readback 規格缺口

- `spec_gap_id`: `PROV-20260827-historical-staff-payables-completion-root`
- `declared_status`: `approved`
- `affected_package`: `WP-HOB-E`
- `owner`: `Staff Payables`
- `current_terminal`: `SP2-Q_APPROVED`

## 1. 問題與必要性邊界

HOB正式規格要求以單一case的current owner readback證明Staff Payables義務、payout與
allocation lineage已結清；它沒有要求新增持久化case settlement root或單一scalar version。
現有`HistoricalSettlementReadback.aggregate_version: int`是本輪source candidate的技術形狀，
不能反過來創造業務必要性。Live schema同時存在：

- `payroll_case_accounts.aggregate_version`：case-level Payroll version；
- `staff_payable_accounts.aggregate_version`：staff-level Payables version；一案可有多位staff；
- staff obligations、payout events／links與projections，但無canonical case settlement lineage identity。

因此adapter不得自行取`MAX(version)`、任一event id或reconciliation reference當case authority；
缺staff account也不得以version `0`當terminal。指紋可作derived integrity identity，但不可偽裝成
root fact或取代typed source vector。

## 2. 必要性稽核後的候選裁決

| 方案 | 設計 | 影響 |
|---|---|---|
| `SP2-Q` Query-only typed source vector（最低必要／建議） | 以單一Staff Payables statement snapshot讀取case Payroll version、排序的staff account versions、obligation current events／projections、完整payout／return／reversal links與適用的recovery roots；公開typed source vector與derived lineage fingerprints。 | 無schema／rebuild；需校正HOB-E source candidate／oracle／API的scalar contract，並對cross-case payout以完整event allocation coverage fail closed。 |
| `SP1-M` Materialized case settlement projection（可採用但目前無必要性證據） | Staff Payables新增rebuildable case-level derived projection，以ordered source vector更新current version，HOB-E只讀此projection。 | 需additive schema／projector／rebuild／descriptor與preserve-data gates；只在查詢成本／SLO或穩定case scalar的實測需求證明query-only不足後才有必要。 |
| `SP-C` 重用既有喪staff／Payroll scalar | 使用任一或`MAX(staff_payable_accounts.aggregate_version)`。 | `remove`；無法證明同案多staff、跨案payout、return／reversal與recovery lineage。 |

### 2.1 四項原提案的necessity verdict

1. 持久化SP1：`NOT_JUSTIFIED`；規格只要求case-scoped current readback。使用者表示可採用不等於已證明必要，目前不施工。
2. 新case version、任一source mutation即`+1`：`NOT_JUSTIFIED`；必要的是existing owner material mutation保持自身版本與immutable successor lineage。readback／alert／UI變動不得創造業務版本。
3. historical bounded rebuild：只對已核准baseline與existing owner projection為`MUST`；為新SP1進行全域backfill是`NOT_JUSTIFIED`。選`SP2-Q`時無新projection可backfill。
4. open／partially recovered overpayment：必須保留`staff_overpayment_recovery_open` anomaly至`recovered|adjusted`，但原obligation已歸零、全額payout已由allocation＋recovery root完整表達時，不得單因recovery尚open就泛化阻擋Step 11。只readback stale／unavailable或lineage integrity blocker才間接阻擋。

### 2.2 `SP2-Q` 最低必要contract

1. 以typed、排序、去重source vector取代本輪candidate的假scalar；不取`MAX(version)`。
2. vector至少包含`payroll_case_accounts`、本案所有`staff_payable_accounts`、當前obligation current event／projection、payout／return／reversal events與links。
3. 同一payout event若跨case，readback必須驗證該event的完整allocation coverage；只讀本案slice或無法唯一attribution時回unavailable。
4. `settlement_lineage_identity`與`allocation_lineage_identity`是對完typed source rows的derived fingerprint，不是root fact；source vector本身必須穿過Subsystem／API contract供驗證。
5. 缺staff account、projection、allocation、reversal target或source drift一律`readback_available=false`；不得用version `0`、單一event或receipt補值。
6. Query只讀、零寫入、不鎖定；`for_update=True`拒絕。如未來實測SLO不足，再另立`SP1-M`necessity evidence與DB Work Package。

### 2.3 人工裁決

2026-08-27人工在必要性稽核後正式採用`SP2-Q` typed source vector，並接受：

- open／partially recovered overpayment anomaly持續存在至`recovered|adjusted`；
- 但原obligation已歸零且payout／allocation lineage完整時，不單獨阻擋Step 11；
- `SP1-M`只保留為未來有SLO／查詢成本證據時的可選優化，不在本次實作範圍。

## 3. `SP2-Q` minimum acceptance after decision

1. 多staff settled case只有一個case-scoped typed readback，source vector保留每位staff與Payroll source identity/version。
2. 任一open obligation、missing projection、unallocated／reversed payout、owner unavailable都不得terminal。
3. payout event跨case時驗證完整event allocation coverage；無法唯一對應回unavailable。
4. return／reversal使原obligation重開；underpayment remaining大於零不terminal。
5. overpayment在原obligation歸零且全額payout完整表達時可完成Staff payout readback，但recovery anomaly持續至`recovered|adjusted`。
6. Query單案、零寫入、零鎖；`for_update=True`拒絕。

## 4. DB change gates

| Gate | 結果 | 證據／原因 |
|---|---|---|
| Scope gate | `PASS` | 2026-08-27人工已確認`SP2-Q` typed source vector public contract；`SP1-M`不施工。 |
| Change inventory | `PASS` | `SP2-Q`為schema-only=`NOT_APPLICABLE`、seed/backfill/destructive=`NOT_APPLICABLE`；只改Subsystem／API typed contract與adapter/tests。 |
| Static release gate | `PASS` | `SP2-Q`不新增schema／release，not applicable。 |
| Descriptor gate | `PASS` | `SP2-Q`不新增owned DB object，not applicable。 |
| Read-only plan gate | `PASS` | `SP2-Q`無migration artifact，not applicable。 |
| Engine verification gate | `PASS` | DB change gate不適用；功能本身仍須真MySQL readback驗收。 |
| Developer acceptance gate | `PASS` | 無本機DB upgrade，not applicable。 |

總結：`SP2-Q_APPROVED / NO_DB_CHANGE`；授權在WP-HOB-E既有write set內修改Subsystem typed contract、
Staff Payables read adapter、API／React contract與tests；不授權DDL／migration、row backfill、reset／replacement、
`union_db`或production操作。只有未來重新選擇`SP1-M`時才觸發完整DB change gates。

## 5. 2026-08-27 implementation snapshot

- `status`: `CROSS_LAYER_CANDIDATE`；不是WP-HOB-E整包完成。
- 已完成：typed sorted source vector、Orders／settlement material fingerprint、單statement Staff Payables
  read adapter、bank evidence、完整event allocation、target-bounded return／reversal、recovery root／event
  lineage、open recovery非單獨blocker與typed unavailable分類。
- 跨層：已完成fresh projector、typed authenticated API與strict React client／Step 11 panel；API將
  signed BIGINT version序列化為decimal string，避免JavaScript number失真。known Scheduling blocker
  保留`scheduling` owner與`scheduling.official_service_facts` referral，不壓成generic unavailable。
- 驗證：focused Python `137 passed`、React `23 passed`、build PASS、Python compile、scoped
  `git diff --check`、真`lu_test_*` MySQL對Orders／Staff單statement SQL解析PASS；零DB寫入。
- DDH：exact patch producer blocked後降E2；兩輪Luna High read-only verification各自找到反例，再由E2
  修正。所有子代理均為`gpt-5.6-luna`／`high`且零寫入。
- DDH：r16 fresh Luna High跨層verifier找到Scheduling分類與BIGINT transport兩項缺陷；修正後r17
  fresh Luna High verifier PASS。所有子代理均唯讀且零寫入。
- Browser：依人工指示使用no-auth development local bypass；`AP-DURABLE-1`負向／unavailable顯示PASS、
  Step 11未假完成、精確owner referral可見、console零error／warning。這不是enabled persisted-human auth證據。
- 尚未完成：現有`lu_test_*`沒有可由正式command鏈重播建立的同案F-04正向根事實；不得用直接植入
  derived roots的E2E fixture替代。因此正式command正向runtime與Browser維持`blocked`。
