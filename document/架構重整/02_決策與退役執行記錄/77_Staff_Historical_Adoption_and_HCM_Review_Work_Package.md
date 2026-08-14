---
doc_type: work-package
declared_status: in-progress
date: 2026-08-13
owner: Case Import / Staff Historical Adoption
priority: P0
---

# 77 Staff Historical Adoption 與 HCM Review Work Package

## 1. 人工裁決與 business scenario

2026-08-13 最新人工裁決：Staff 歷史來源可包含同一月嫂的重複填寫；identity與姓名相同且來源
`報名時間`嚴格較新時，最新來源覆寫可更新 scalar，作為同一月嫂更新資料。來源空值與受保護 root
fields不覆寫；銀行與關聯集仍採保守合併。資料庫既有 identity不得再以 `skipped_existing` 無證據略過。
非根欄位錯誤可依既有裁決以
`NULL` 建立或合併 Staff，但必須同時建立 durable review 與 canonical anomaly。

2026-08-13 補充裁決：Staff歷史來源的`IP位址`本身允許空值；空值正規化為`NULL`，不視為欄位
錯誤、不建立review，且不得阻擋同列其他合法欄位建立或保守合併。

2026-08-13 修正裁決：HCM 與 Client BeClass 必須可獨立匯入、獨立存在，後續才進行配對綁定。
HCM案件編號不得重複；新案件若IP位址與姓名同時命中既有Client，視為疑似重複申請，不載入並
建立review與警示請公會確認。只有IP相同但姓名不同不阻擋；Client
BeClass 或料理答案尚未存在時仍可建立 Client／Order，`requires_cooking` 保持 `NULL`。Client
BeClass 也不得因 HCM 尚未匯入而失敗。任一方缺少對方只建立可自動解除的 current-state anomaly，
不是 `review_required`、`skipped` 或匯入失敗。

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
3. 既有 identity 且姓名一致時結果為 `adopted_existing`：
   - 來源 `報名時間`嚴格晚於既有 `registered_at` 時，以新來源覆寫可更新的非空 scalar，並更新
     `registered_at`；未較新時只補 DB 的 `NULL`／空字串，非空差異保留 current fact並 review；
   - `identity_card`、`line_user_id`、`status`、created／updated timestamps 永不由歷史來源覆寫；
   - `has_massage_cert`、`care_babies` 的 DB default 無法表達 unknown，既有列不自動改值；
   - 非空不同值保留 current fact並建立 review。
4. 既有 identity 但姓名不同時結果為 `identity_conflict`，零 Staff mutation並建立 review。
5. 銀行：完全相同為 no-op；Staff 沒有帳戶時才新增通過驗證的帳戶；不同帳戶、跨 Staff
   collision 或不完整銀行資訊都 review，receipt／alert 不保存完整帳號。
6. 關聯集合：空集合才補入、完全相同為 no-op、非空不同時保留 current 並 review；禁止
   delete-and-reinsert 或 union。正式 Matching preference facts 不由 legacy relation tables 反推更新。
7. exclusive outcomes：`created | adopted_existing | exact_replay | blocked_identity |
   identity_conflict | failed_retryable`。每列都必須重新完成DB identity resolution、merge decision、
   review與receipt；不得只因舊程式判定「既有」就略過。`exact_replay`只適用於已有同一source
   identity＋相同payload fingerprint的成功receipt，且 replay 時 fresh-lock 的唯一 Staff root、
   receipt `staff_id` 與姓名仍一致。root 遺失或錯配必須 fail closed，不得偽裝 replay。
   `review_required`是正交計數，可與
   created／adopted重疊。

## 4. HCM／Client BeClass 獨立匯入與 reconciliation contract

1. source identity 由 workbook digest、不可逆 sheet identity 與 row ordinal組成；歷史 Staff operator
   僅可用 bounded、非個資 `source_revision` 宣告同內容的新確認版本，revision 與 digest 派生新 identity；
   相同 identity＋相同 payload fingerprint 是 replay，相同 identity＋不同 fingerprint 是 source conflict。
2. review root 只保存 masked case identity、issue codes、欄位存在性／型別等 privacy-safe evidence；
   不保存 raw row、姓名、電話、地址或原始 sheet name。
3. HCM案件編號必須唯一；既有案件只有同source fingerprint成功receipt可exact replay。新案件若
   IP位址與姓名同時精確命中既有Client，零root mutation並建立HCM review＋outbox，警示中心顯示
   「疑似重複申請，請公會人員確認」。只有IP相同但姓名不同不阻擋；不得用模糊姓名或電話自動合併。
4. 有效HCM可在Client BeClass不存在時建立Client／Order；有HCM無Client BeClass時投影
   `BECLASS-001`，但該列exclusive outcome仍是`created`，並正交標示`pending_counterpart`。
5. Client BeClass可在HCM不存在時獨立落地；有Client BeClass無HCM時投影
   `IMPORT-003 / beclass_hcm_mismatch`，不得將其計為Client BeClass匯入失敗。
6. 對方日後出現時，reconciliation重新讀取fresh facts；案件編號及accepted mapping唯一且一致才
   建立accepted mapping並解除缺件警示。多筆候選或衝突保留兩方來源並進review。
7. cooking只在唯一綁定後解析Client BeClass controlled answer，並透過typed Orders command補入
   `requires_cooking`。missing／malformed／ambiguous／unsupported答案不得回滾或刪除HCM roots；
   `IMPORT-004`只處理HCM來源列本身的validation failure。
8. HCM review anomaly由committed outbox非同步投影；script不另開連線同步寫alert。
9. 本包只建立必要intake review／outbox與既有current-state anomaly reconciliation；人工
   Correct／Reject Preview／Apply及管理UI由WP73後續phase承接，不預建generic workbook manifest。

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

1. 49-row Staff scenario守恆；DB existing intersection不得再計為skipped，也不得預設
   `created／adopted_existing／review_required`固定筆數。exclusive outcomes總和必須等於source rows。
2. 每個source row都完成fresh DB identity resolution並留下receipt；只有實際查得唯一既有identity且
   姓名一致者可為`adopted_existing`。不存在者建立Staff，零duplicate；嚴格較新的來源時間覆寫可更新
   nonblank scalar，未較新非空衝突review。
3. existing dirty row仍建立 review；review root、outbox、Staff mutation與 receipt atomic。
   已發布 outbox 後若 current anomaly projection 遺失，背景 bounded root rescan 必須從 durable
   review root／resolution event 補建，不重置 outbox、不改寫 review root。
4. bank／relations empty、exact、conflict與跨 Staff collision均有 focused evidence，且既有集合未 DELETE。
5. HCM與Client BeClass可依任意順序獨立匯入；缺對方不阻擋來源root，分別投影`BECLASS-001`或
   `IMPORT-003 / beclass_hcm_mismatch`，對方出現且唯一綁定後自動解除。
6. HCM新案件若IP＋姓名未同時命中既有Client可建立roots；案件重複或IP＋姓名同時命中時零Client／
   Order，durable HCM review與`IMPORT-004` anomaly可查，警示中心明示請公會確認疑似重複申請。
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
    資料庫，因此本輪可精準套用 WP77 successor part 192 並執行去敏 import 驗證，但不得延伸到其他 DB。

## 8. Completion gate

只有 code、schema release、focused與 engine evidence全部完成，且實際 49-row Staff與HCM dirty-data
驗收 receipt確認無 duplicate／fabricated root後，WP77才可 completed。WP77完成不等於WP73 Web UI完成，
也不授權封存ADR-001。
