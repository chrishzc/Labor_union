---
doc_type: work-package
declared_status: completed
date: 2026-08-13
owner: Case Import / Staff Historical Adoption
priority: P0
---

# 77 Staff Historical Adoption 與 HCM Review Work Package

## 1. 人工裁決與 business scenario

2026-08-14 最新人工裁決：Staff 歷史來源可包含同一月嫂的重複填寫；以身分證唯一定位。姓名缺失／
無效時維持既有不可建檔規則；既有 Staff 身分證唯一且姓名相同時，來源`報名時間`嚴格較新的列覆寫
可更新 scalar。姓名不同不再阻擋更新；較新來源可更新姓名，但必須留下姓名變更追溯警示。身分證、
LINE ID、status等受保護 root fields不覆寫。較新歷史列的銀行與所有勾選關聯視為完整快照，整組取代
舊集合；資料庫既有 identity不得再以 `skipped_existing` 無證據略過。非根欄位錯誤可依既有裁決以
`NULL` 建立或合併 Staff；任一欄位缺漏或格式無效，即使 Staff 可建立／更新，也必須同時建立該欄位的
durable warning 與 canonical anomaly。

2026-08-13 補充裁決：Staff歷史來源的`IP位址`本身允許空值；空值正規化為`NULL`，不視為欄位
錯誤、不建立review，且不得阻擋同列其他合法欄位建立或保守合併。

2026-08-14 HCM補充裁決：HCM 與 Client BeClass 必須可獨立匯入、獨立存在，後續才進行配對綁定。
案件編號是 HCM 最低寫入資格與唯一鍵；只要案件編號可用，即使其他欄位缺漏、格式錯誤或 IP／姓名
關聯歧義，仍建立或補齊正式案件，並對問題欄位或未確認關聯建立警示。只有案件編號缺失／不可用
才不建案、僅留警示。後續只需透過 typed field-completion command 補齊被警示欄位，即可依 predicate
解除該警示，不要求整案重送；不得由警示中心直接改值。HCM歷史過渡另以來源業務時間由舊至新直接
寫入所有可更新欄位，不建立「目前有效值」推導層。即使案件已具帳務、薪資、排程等下游根事實，仍可直接
覆寫 HCM 所有可更新來源欄位；來源「案件狀態」不屬 HCM 可更新集合，永不覆寫 Orders lifecycle status。
Client BeClass 或料理答案尚未存在時仍可建立
Client／Order，`requires_cooking` 保持 `NULL`；任一方缺少對方只建立可自動解除的 current-state
anomaly，不是 `review_required`、`skipped` 或匯入失敗。

## 2. Owner、SSOT 與 transaction boundary

- Case Import 擁有 source row identity、payload fingerprint、HCM review root、兩條來源間的
  accepted mapping／reconciliation，以及 Staff historical adoption decision 與 adoption receipt。
- `staff`、銀行及關聯表仍是 Staff root facts；HistoricalAdoption 只透過目的明確的 borrowed
  writer port 在同一 outer Unit of Work 寫入，不把 Staff root ownership移給 LINE 或 script。
- Staff future LIFF profile API 不在本包裁決；本包只授權 restricted historical source。
- 每一 source row 是一個 terminal transaction boundary。Staff root mutation、adoption receipt、
  BeClass Staff review root 與 review outbox必須同 transaction；HCM review root 與 anomaly outbox
  亦必須同 transaction。
- importer、repository 與 anomaly projector不得 hidden commit。已完成列可 replay；後續列失敗
  不得宣稱整批 rollback。

## 3. Staff HistoricalAdoption contract

1. identity card 經 trim／uppercase 後是唯一 root identity；缺失或格式錯誤時零 Staff mutation並 review。
2. 新 identity 建立 Staff；非根欄位錯誤先將對應欄位設 `NULL`，仍可建立並正交計入 review。
3. 既有唯一 identity 時結果為 `adopted_existing`：
   - 來源 `報名時間`嚴格晚於既有 `registered_at` 時，以新來源覆寫可更新 scalar，並更新
     `registered_at`；姓名不同亦更新，但留下 `historical_name_changed` 追溯警示；未較新時只補 DB 的
     `NULL`／空字串，非空差異保留 current fact並 review；
   - `identity_card`、`line_user_id`、`status`、created／updated timestamps 永不由歷史來源覆寫；
   - `has_massage_cert`、`care_babies` 的 DB default 無法表達 unknown，既有列不自動改值；
   - 非空不同值保留 current fact並建立 review。
4. 既有 identity 但姓名不同且來源並未嚴格較新時結果為 `identity_conflict`，零 Staff mutation並建立
   review；嚴格較新的姓名變更依第 3 點採納，不再誤判為 identity conflict。
5. 銀行：嚴格較新的歷史列是完整快照，在同一 outer Unit of Work 先通過跨 Staff collision gate後整組
   取代；完全相同為 no-op，空快照會清除舊集合。未較新的來源維持保守合併；不完整資訊仍 review，
   receipt／alert 不保存完整帳號。
6. 關聯集合：嚴格較新的歷史列整組取代 legacy relation集合；未較新的來源維持空集合補入、完全相同
   no-op、非空不同保留 current並 review。正式 Matching preference facts 不由 legacy relation tables
   反推更新。
7. exclusive outcomes：`created | adopted_existing | exact_replay | blocked_identity |
   identity_conflict | failed_retryable`。每列都必須重新完成DB identity resolution、merge decision、
   review與receipt；不得只因舊程式判定「既有」就略過。`exact_replay`只適用於已有同一source
   identity＋相同payload fingerprint的成功receipt，且 replay 時 fresh-lock 的唯一 Staff root、
   receipt `staff_id` 與 identity仍一致。姓名可被後續較新歷史列合法更新，因此舊來源 replay不得要求
   姓名仍等於舊列；root 遺失或錯配必須 fail closed，不得偽裝 replay。
   `review_required`是正交計數，可與
   created／adopted重疊。

## 4. HCM／Client BeClass 獨立匯入與 reconciliation contract

1. source identity 由 workbook digest、不可逆 sheet identity 與 row ordinal組成；歷史 Staff operator
   僅可用 bounded、非個資 `source_revision` 宣告同內容的新確認版本，revision 與 digest 派生新 identity；
   相同 identity＋相同 payload fingerprint 是 replay，相同 identity＋不同 fingerprint 是 source conflict。
   Staff歷史採身分證唯一定位；姓名缺失維持現有寫入阻擋，姓名不同只在來源時間嚴格較新時更新並建立
   追溯warning。
2. review root 只保存 masked case identity、issue codes、欄位存在性／型別等 privacy-safe evidence；
   不保存 raw row、姓名、電話、地址或原始 sheet name。
3. HCM案件編號是唯一鍵與最低寫入資格；案件編號缺失／不可用時零正式案件 mutation並建立警示。
   其他欄位缺漏、格式錯誤或關聯歧義不可阻擋有案號的正式案件建立；問題欄位建立HCM warning，
   IP位址與姓名同時精確命中既有Client時也只禁止自動綁定，不得阻擋建案或用模糊姓名／電話自動合併。
   同source fingerprint成功receipt才是exact replay；既有案件的補件只能經fresh-lock typed
   field-completion command寫入被警示欄位。
4. 有效HCM可在Client BeClass不存在時建立Client／Order；有HCM無Client BeClass時投影
   `BECLASS-001`，但該列exclusive outcome仍是`created`，並正交標示`pending_counterpart`。
5. Client BeClass 的`query_no`只是來源流水號，不得作為客戶識別或案件編號。LIFF 啟用前，只有
   姓名與手機號碼均完全一致且唯一命中正式 Client，且該 Client 的案件候選唯一時，才可建立過渡綁定；
   0／多筆 Client 或案件候選都必須留警示，不得猜測。LIFF 啟用後由登入身分直接綁定，不再使用此
   過渡比對。Client BeClass 可在HCM不存在時獨立落地；有Client BeClass無HCM時投影
   `IMPORT-003 / beclass_hcm_mismatch`，不得將其計為Client BeClass匯入失敗。
6. 對方日後出現時，reconciliation重新讀取fresh facts；案件編號及accepted mapping唯一且一致才
   建立accepted mapping並解除缺件警示。多筆候選或衝突保留兩方來源並進review。
7. HCM歷史過渡來源以明示的來源業務時間由舊至新處理，符合最低寫入資格的列直接寫入所有可更新
   欄位；不讀取或推導DB目前有效值。既有帳務、薪資、排程等下游根事實不是覆寫 gate；但來源「案件狀態」
   一律排除，維持 Orders lifecycle SSOT。cooking只在唯一綁定後解析Client BeClass controlled answer，並透過typed Orders command補入
   `requires_cooking`。missing／malformed／ambiguous／unsupported答案不得回滾或刪除HCM roots；
   HCM warning涵蓋來源欄位缺漏／格式錯誤與關聯未確認；每種類型的顯示、允許後續處理、解除predicate
   與未來LINE行為必須登錄後另行審核。
8. HCM review anomaly由committed outbox非同步投影；script不另開連線同步寫alert。
9. 本包只建立必要intake review／outbox與既有current-state anomaly reconciliation；人工
   Correct／Reject、typed command轉介及管理UI由WP86／警示中心後續工作承接，本包不施工。

## 5. Change inventory

| 類型 | 變更 | 資料效果 | replay／rollback |
|---|---|---|---|
| schema-only | immutable Staff adoption receipt | 新增操作證據，不改既有 Staff | key＋fingerprint replay；code rollback保留 receipt |
| schema-only | HCM review root＋outbox | HCM root identity／來源欄位無效時建立review及anomaly intent | source identity replay；code rollback保留review |
| system-seed | 無 | 無 | 不適用 |
| business-row-backfill | 無 | 不自動處理既有資料 | 真實來源由 operator明確執行 |
| destructive | 無 | 不刪表、不改既有 column | 不適用 |

## 6. Write set

- `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md`
- 本 Work Package、同目錄 `README.md`、WP73 capability decision與 evidence index
- `domains/case_import/` 下 Staff adoption及 HCM review typed rules
- `subsystems/case_import/` 下 Staff HistoricalAdoption與 HCM review intake
- `infrastructure/mysql/` 下 purpose-specific repositories／writers
- `subsystems/anomalies/` 下 HCM review outbox consumer與 worker wiring
- `ui/pages/06_finance_alerts.py` 的疑似重複申請警示文字（不新增人工處理入口）
- `scripts/imports/import_staff_beclass.py`、`scripts/imports/import_client_hcm.py`
- 一個新的 additive `db/schema_parts/` artifact、`db/schema.sql`、validation release assembly／manifest、
  canonical migration release manifest／descriptor及 migration catalog
- focused tests、disposable MySQL tests、preserve-data plan／engine tests、operator文件與去敏 evidence

不包含 Staff future LIFF profile UI/API、Client HistoricalAdoption、HCM Web upload UI、generic import
registry、production DB操作、seed、business backfill或 destructive migration。

## 7. Acceptance

1. 去敏 Staff workbook 的全部 source rows守恆；DB existing intersection不得再計為skipped，也不得預設
   `created／adopted_existing／review_required`固定筆數。exclusive outcomes總和必須等於實際source rows。
2. 每個source row都完成fresh DB identity resolution並留下receipt；只有實際查得唯一既有identity且
   唯一 identity可為`adopted_existing`。不存在者建立Staff，零duplicate；嚴格較新的來源時間覆寫可更新
   scalar及完整銀行／關聯快照，姓名變更留追溯警示；未較新非空衝突review。
3. existing dirty row仍建立 review；review root、outbox、Staff mutation與 receipt atomic。
   已發布 outbox 後若 current anomaly projection 遺失，背景 bounded root rescan 必須從 durable
   review root／resolution event 補建，不重置 outbox、不改寫 review root。
4. bank／relations empty、exact、較新快照replacement、舊來源replay與跨 Staff collision均有 focused evidence；
   只有同一 Staff 的較新完整快照可在 outer Unit of Work內取代舊集合。
5. HCM與Client BeClass可依任意順序獨立匯入；缺對方不阻擋來源root，分別投影`BECLASS-001`或
   `IMPORT-003 / beclass_hcm_mismatch`，對方出現且唯一綁定後自動解除。
6. 有可用案件編號的 HCM 列一律建立或定位正式案件；IP＋姓名同時命中既有Client時不得自動綁定，
   而是保留正式案件、建立關聯警示與`IMPORT-004` anomaly。案件編號缺失／不可用才零正式案件 mutation；
   欄位缺漏、格式錯誤或關聯歧義皆須留下可追蹤 warning，供後續 typed field-completion command解除。
7. cooking缺失／歧義不得阻擋或回滾HCM roots；唯一綁定後只有controlled answer可透過typed Orders
   command補入`requires_cooking`，否則維持`NULL`並進對應review。
8. HCM 不再於匯入前讀取BeClass cooking、不再呼叫 BeClass review，不再 helper commit或另連線同步 anomaly；infrastructure failure回
   retryable failure，不偽裝 review。
9. exact replay零增量；same identity＋different payload conflict；注入 writer／receipt／outbox failure
   時單列 full rollback。
10. stdout、receipt、review與 anomaly snapshot不含完整證號、電話、地址、銀行帳號或 raw workbook path。
    stdout至少顯示source rows、各exclusive outcome、review_required及alerts_created；警示中心只顯示
    需要人工處理或等待對方的current state，不以警示筆數取代匯入守恆。
11. schema part、fresh assembly、canonical release／descriptor互相一致；read-only migration plan列出
   WP77 artifact；fresh disposable DB與上一支援版 preserve-data candidate均 PASS。
12. 原則上不操作既有 `union_db`；2026-08-13 人工另行確認目前本機 `union_db` 為可直接操作的測試
    資料庫，因此本輪可精準套用 WP77 part 189 並執行去敏 import 驗證，但不得延伸到其他 DB。

## 8. Completion gate

2026-08-14 已依人工裁決以目前去敏 workbook作受控來源證據；實際資料列數由該 workbook決定，不再以
舊環境的49列作固定完成門檻。code、schema release、focused、fresh／pre-189 preserve candidate、去敏
Staff Preview／Apply／replay及HCM dirty-data evidence均完成，無 duplicate／fabricated root，因此WP77
完成。警示中心 Correct／Reject／轉介仍屬WP86後續範圍。
