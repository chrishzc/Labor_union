# WP77 Staff Historical Adoption 與 HCM Review 完成收據

- 初始日期：2026-08-13
- 完成裁決與重驗日期：2026-08-14
- Work Package：`../../04_已完成與上線封存/work_packages/77_Staff_Historical_Adoption_and_HCM_Review_Work_Package.md`
- immutable release id：`labor-union-wp77-2026-08-13-v1`
- isolated rehearsal assembly：`labor-union-wp77-pre189-assembly-2026-08-14-v1`
- 狀態：completed

## 完成裁決

先前以特定目標機 `49` 列與 Staff 保守 non-empty merge 作為完成條件的敘述，已被2026-08-14人工
裁決取代：目前去敏 workbook就是受控資料證據，source row數由該檔實際內容決定。Staff以身分證唯一
定位；嚴格較新的歷史列覆寫 mutable scalars，姓名變更留下追溯警示，銀行與 legacy relations視為
完整快照整組取代。警示中心 Correct／Reject／typed command轉介不屬本包。

## 程式與 dirty-data evidence

1. fail-before證明 workbook Preview原先仍把「較新來源＋姓名不同」錯判為`identity_conflict`；修正後
   Preview與Apply一致判定為`adopted_existing + review_required`。
2. focused Staff contracts、typed API client／route、parser與 disposable MySQL：`45 passed`。
3. disposable MySQL較新快照驗證：姓名、銀行與關聯集合整組更新並建立`historical_name_changed`；隨後
   重播舊來源只回 exact replay，不把姓名或集合倒退。
4. HCM dirty-data與 partial formal case證據由WP73完成收據承接：可解析整列落正式Client／Order，異常
   欄位為`NULL`、案件維持`待補件`且不建立帳務義務。

## 去敏 workbook evidence

- 來源：`document/資料庫、資料處理/2.staff.xlsx`
- workbook結構：單一`Worksheet`，使用範圍`A1:BG2`，1筆source row。
- project parser：1筆invalid row；問題欄位為報名時間、行動電話、身分證字號。
- typed Preview：`source_rows=1`、`blocked_identity=1`、`review_required=1`。
- typed Apply：同上，正式Staff新增0；invalid row沒有靜默消失。
- 相同全檔command replay：`replayed_workbook=true`，沒有新增review／receipt待辦。
- workbook只作受控去敏驗收來源；收據不保存原始個資值。

## Schema engine evidence

- fresh：既有 `lu_test_wp77_20260813_r3` 已建立至part 189，WP77 MySQL E2E PASS。
- previous baseline：`lu_test_wp77_pre189_20260814` 由base schema加part 20～188建立。
- candidate：`lu_test_wp77_candidate_assembly_20260814`。
- rehearsal artifacts：`scratch/wp77-preserve/assembly-v1/`（ignored operator evidence）。
- dry-run明示part 189由`absent`待套用；dump／restore／apply／verify均PASS。
- part 189 candidate classification=`exact`；source與candidate既有table的row count／checksum／PK fingerprint
  相同；沒有seed、backfill、destructive change或same-name switch。
- 第二次Apply／Verify仍PASS，證明release replay安全。

## DB gate

| Gate | 狀態 | 證據 |
|---|---|---|
| Scope gate | PASS | 已核准WP77與2026-08-14 Staff歷史快照裁決 |
| Change inventory | PASS | part 189只有schema-only；無seed、backfill、destructive change |
| Static release gate | PASS | immutable manifest／descriptor／catalog及pre-189 rehearsal assembly；plan contract `21 passed` |
| Descriptor gate | PASS | Staff receipt、HCM review／outbox與immutable triggers分類為exact |
| Read-only plan gate | PASS | pre-189 source顯示part 189 absent且plan ready |
| Engine verification gate | PASS | fresh＋pre-189 dump→candidate→apply→verify＋replay均PASS |
| Developer acceptance gate | PASS | 去敏 Staff workbook typed Preview／Apply／replay及HCM dirty-data evidence完成 |

總狀態：`DB_CHANGE_READY`；WP77已完成。這不代表警示中心 Correct／Reject／轉介功能完成。
