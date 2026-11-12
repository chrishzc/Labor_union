# Case Import 與非市民 Redis 待審正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Case Import Domain（`domains/case_import/`、`subsystems/case_import/`）
- 單一負責範圍：多來源進件通道架構（HCM Web Upload、Client／Staff LIFF 與歷史匯入分軌）、非市民自費案件報名與 `A` 字頭配號（`NC-ENTRY-01～03`、`NC-FORM-01～02`、`NC-APPROVAL-01～02`、`NC-NUMBER-01～02`）、**核准前問卷不得進 MySQL 之專用 Redis 7 隔離持久化架構（`REG-BOUNDARY-01～06`、`REG-REDIS-01～09`、`REG-EXPIRY-01～04`、`REG-REFUND-01～03`）**、HCM 整批原子匯入與 7 項待補件欄位／四種服務方式規範、HCM 欄位警示重驗與逐欄略過（`HCM-REPAIR-01～03`）、客戶 BeClass 工作簿人工配對、`BECLASS-001／IMPORT-003` 配對決策矩陣，以及匯入完成統計／自動重查顯示邊界。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[訂單看板、事前日期與歷史採納](01A_訂單看板與事前日期及歷史採納規格.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[Anomalies Domain](06_Anomalies_Domain.md)、[Global Migration 與 Cutover](10_Global_保留資料Migration與Cutover_Subsystem.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[Contract Signing 正式規格](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md)、[LINE 服務說明與選單角色](29_LINE服務說明、客服互動與選單角色正式規格.md)、[案件與月嫂整合名冊](33_案件與月嫂整合名冊正式規格.md)、[營運報表與統計口徑](34_營運報表與統計口徑正式規格.md)。

## 2. 多來源進件、工作簿原子性與彙整顯示

### 2.1 SSOT 與入口分流（`IMPORT-ENTRY-02`）

- Case Import 擁有 BeClass／HCM 原始 row identity、檔案摘要、正規化候選、驗證結果、accepted source→internal mapping 與 bootstrap receipt（不直接持有正式客戶、訂單、排班或帳務根事實；建案一律透過單一 outer UoW 委派各 owner）。
- **入口規則**：
  - **HCM**：僅限經認證後台 Web Upload（`WHOLE_WORKBOOK + archive_required`）；archive 成功若 DB 交易回滾必執行補償刪除。以非空合法 `查詢序號(案件編號)` 為唯一建案鍵：新案建立建置 policy 綁定與訂單；已存在案號同內容 exact replay、異內容 `skipped_existing` 零覆寫（唯允許對空白 `clients.email` 執行 email-only 補填）；不同案號但 `IP + 姓名` 命中既有客戶時照常建案並發非阻擋 link review 警示。
  - **Client BeClass／Staff**：現行來源透過 LIFF → owning Domain API；`Client／Staff Historical Adoption` 採 `ROW_ATOMIC_RESUMABLE + archive_required`（支援斷點續跑；同身分證＋姓名＋嚴格較新報名時間始更新歷史 Staff 純量，空值不覆蓋、`IP位址` 允許 `NULL`）。

### 2.2 匯入統計、未匯入明細與自動重查顯示契約

- **互斥統計（三類合計等於來源筆數）**：HCM、Client BeClass、Staff Historical 統一顯示「`來源筆數／成功匯入／重複略過／未匯入`」（歷史訂單則為 `成功寫入／資料已一致／未匯入`＋另列 `檔外取消`；Staff 歷史匯入依成功採納之不重複身分證累計 `成功匯入`，同人其餘成功列計 `重複略過`，保留逐列欄位合併與中斷續跑原始分類）。
- **未匯入明細（`row_issues`／`row_outcomes`）**：僅列實際未匯入項之位置（HCM 用資料序號，其餘用 Excel 列號）、案號／查號、問題欄位與去敏白話原因（禁止於匯入頁顯示成功但帶警示列、問題導覽或內嵌修正表單；Staff 明細禁洩漏身分證）。
- **Apply 超時自動重查**：HCM、Client BeClass、Staff Historical 與 Historical Order 四者 Apply 每次等待上限為 `180` 秒（協調鎖 `30` 秒）；遇等待逾時／斷線／502／504／鎖等待時每 `5` 秒依同快照與同 `idempotency_key` 背景重查（最多 `6` 次、顯示中性「匯入處理中」而不報錯），允許操作者自由切換分頁或離頁（不阻止導覽且離頁不取消已送出的 Apply，達上限改呈現「等待時間較長，尚未取得最終結果」與手動重查鈕）。

### 2.3 客戶 BeClass 工作簿的人工配對與確認匯入

- **候選範圍**。資料匯入中心的客戶 BeClass 工作簿預覽先依姓名與正規化手機精確查找客戶及其 HCM 案件。唯一命中一筆客戶及一個可綁定案件時直接匯入。一筆客戶有多個案件，或命中多筆客戶而無法唯一確定案件時，將該問卷與可綁定的 HCM 案件列入人工配對。已匯入且來源內容相同的問卷列為重複略過。格式錯誤、來源衝突或無可綁定案件的列保留原未匯入分類。BeClass 查詢序號識別來源問卷。報名時間、建檔時間、預計服務日期及縣市供人工核對，系統不得用日期接近程度或清單順序代為選案。
- **抽屜與左右核對**。匯入預覽顯示人工配對組數、待配對筆數及「開啟人工配對」。抽屜將直接或間接共用候選 HCM 案號的問卷歸為同組，一次顯示一組，可切換組別或前往下一組待配對。切換組別或關閉抽屜保留本次預覽已建立的連線。抽屜沿用帳務核銷的左側來源、右側目標版型。左欄展開當組待配對問卷，顯示 Excel 列號、BeClass 查詢序號、姓名、遮蔽後的手機、縣市與問卷報名時間。右欄展開當組候選案件，每個 HCM 案號只出現一次，並顯示姓名、遮蔽後的手機、縣市、HCM 建檔時間與預計服務日期。缺值明示「未提供」，日期時間以臺灣時間顯示。
- **連線與改配**。承辦人先點選左側問卷，再勾選右側同一位客戶的一個或多個案件。畫面為每個案件繪製連線，並在兩端顯示查詢序號與案號。已配給另一份問卷的案件顯示其配對對象且不可選。再次點選案件可解除該連線。預覽和連線操作皆為零寫入。
- **確認與套用**。每份待選問卷至少勾選一案後，可點「檢查配對」核對 Excel 列號、查詢序號與各 HCM 案號。確認畫面分別顯示人工配對的問卷數與套用案件數。點「確認匯入」後，Apply 重驗工作簿、同一客戶及所有已選案件的綁定資格。每案各存一筆來源副本，以「查詢序號＋綁定案號」防止重複，後續補正按案件獨立。任一選案失效或已遭綁定時，該問卷列整批以型別化衝突回報並須重新預覽。匯入分類按 Excel 列計數，人工綁定明細按案件列出成功的對應。結果未明時依 §2.2 以同一組已確認選案重查。
- **結果回讀**。匯入結果沿用 §2.2 四項統計，另提供可展開的「人工綁定明細」，只列本次實際綁定成功的 Excel 列號、BeClass 查詢序號與 HCM 案號。人工綁定成功屬「成功匯入」的一部分。未匯入明細與人工綁定明細各自依結果顯示，並可從結果頁選擇下一份檔案。

## 3. 非市民自費進件與專用 Redis 7 待審隔離架構

### 3.1 非市民進件與配號（`NC-ENTRY`、`NC-FORM`、`NC-APPROVAL`、`NC-NUMBER`、`NC-STAT`）

- **進件獨立性（`NC-ENTRY-01～03`）**：非市民由 [服務閘道 §2](29_LINE服務說明、客服互動與選單角色正式規格.md#2-服務閘道gateway與登記入口規則) 的「非新竹市民 → 尚未申請」進入專屬 LINE LIFF 合併表單；因補助資格不符而作廢之原 HCM 報名保留原記錄與審核失敗統計，另申請自費者須走本專用 LIFF 與工會審核取得新 `A` 案號（禁止沿用原 HCM 案號或假借補件覆活已作廢之補助案件）。
- **必填與用語（`NC-FORM-01～02`）**：合併表單套用全部 HCM 必填欄位 ＋ BeClass 既有規則；統一稱「退款帳戶」供一般退款使用；送出僅存待審申請編號，經工會核准方建立正式 Client／BeClass／Order 與非市民費率綁定。一般需求調查（`/line-registration`）與非市民服務申請（`/line-non-citizen-registration`）皆強制要求填選閉鎖**胎數**（`survey_details["特殊計費:胎數"]`，僅接受 `單胞胎` 或 `雙胞胎`）；非市民 LIFF 不重複渲染舊「寶寶資訊」文字欄位，亦不再向客戶索取 `LINE ID`（由客戶主動加入官方帳號並以 LIFF Token 識別；系統保留 `clients.line_id` 欄位供選填／相容）；`baby_info` 由所選胎數（`單胞胎`／`雙胞胎`）同步填入，`ProvisionalRegistration`／非市民檢核於 Preview／Apply 邊界拒絕缺漏、非「單胞胎／雙胞胎」或不一致之 `baby_info` 與「第幾胎」等其他文字，並於核准建檔時寫入 `beclass_records.survey_details` 供雙胞胎費率與整合名冊消費。
- **後台手動新案必填**。客戶姓名、連絡電話、預計服務開始日、服務天數、服務時段、胎數、電子郵件、退款銀行代號（含分行共 7 碼）及退款銀行帳號均為必填。胎數只接受單胞胎或雙胞胎；同一建案交易寫入 BeClass「特殊計費:胎數」，並以此胎數初始化客戶帳務及月嫂薪資。後台表單與建案 API 均拒絕缺漏或只有空白的值。
- **需求調查時薪與假日意願**。市民與非市民 LIFF 在單胞胎及雙胞胎選項旁顯示 [Client Finance 計價政策](04_Client_Finance_Domain.md#2-核心不變量與計價規則) 的服務時薪。市民以一般市民費率為參考，區分不同的補助內及用盡後費率，非市民顯示自費費率。兩種 LIFF 的「費用與同意條款」及後台手動非市民新案皆選填遇端午、中秋、除夕、初一或初二是否願意支付雙倍薪水，答案為「是」或「否」。此答案只保存於需求調查。
- **非市民表單服務時段**。LIFF 與後台手動新案提供相同的服務方式、生產方式及居住型態選項。每日服務時段提供 08:30–12:30（4 小時）、08:30–16:30（8 小時）、09:00–17:00（8 小時）、13:00–17:00（4 小時）。LIFF 表單及 Preview／Apply 僅接受這四個時段。後台手動新案可調整每日開始與結束時間，同日起訖時間差須等於所選的 4 或 8 小時，不扣午休。LIFF 依預計服務開始日、天數及休假規則推算結束日。退款帳號正規化後須有數字。
- **年度流水配號與後續對齊（`NC-NUMBER-01～02`、`NC-FLOW-01`、`NC-PAYMENT-01`）**：案號採 `A＋民國年度＋3碼流水號`，依正式建案日的臺灣時間年度自 `001` 起算。虛擬帳號依 [Client Finance 帳號規則](04_Client_Finance_Domain.md#23-非市民付款與案件類別篩選nc-fin-0106) 解析。LINE 申請在核准時正式配號。手動新案先唯讀顯示預估案號與帳號，送出時與 LINE 核准共用年度流水號，在同一建案交易內鎖定取號並跳過已使用的案號或帳號，成功後顯示實際配號。可表示的流水號用完時回報衝突。正式建案後的統計、推薦媒合、契約簽署、5 天訂金與分期計價及排班結算沿用既有 owner 流程（見 [營運報表與統計口徑 §5](34_營運報表與統計口徑正式規格.md#noncitizen-statistics-20261029)、[Client Finance §2.3](04_Client_Finance_Domain.md#23-非市民付款與案件類別篩選nc-fin-0106) 與 [Contract Signing](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md)）。

<a id="registration-storage-refund-projection"></a>

### 3.2 核准前問卷不得進 MySQL 與獨立 Redis 7 架構（`REG-BOUNDARY`、`REG-REDIS`、`REG-EXPIRY`）

- **`REG-BOUNDARY-01～06`（儲存與邊界隔離）**：
  - 核准前待審問卷內容與完整申請候選**嚴禁寫入 MySQL 任何資料表、outbox、通知或稽核**。
  - 對外收件容器 `registration-intake` 僅持 LIFF token 驗證與專用 `registration-redis` 受限 ACL（僅可讀寫待審內容與計數器命名空間，完全不配置 MySQL 憑證、網路路徑或審核決策權限）；瀏覽器僅呼叫 bounded API。
  - 管理員審核核准於 MySQL 唯一 outer UoW 透過各 owning Domain writer 原子建立正式 Client／BeClass（含同步保存 `beclass_records.refund_bank_code` 與 `refund_account_no`，依 `REG-REFUND-01～03`）／Orders（含非市民建檔）與 LINE binding，確認完成後方清除 Redis 問卷原文。
- **`REG-REDIS-01～04`（持久化設定與編號）**：專用 `registration-redis`（Redis 7 獨立實例＋持久化卷，禁與 cache 共用；關閉 host port；設定 `appendonly yes`、`appendfsync always`、`noeviction`、`maxmemory 256mb`、`auto-aof-rewrite-percentage 100`、`auto-aof-rewrite-min-size 64mb`）。容量滿或 AOF 錯誤一律拒收而不退回 MySQL。專用 Redis 持久化計數器須於還原後與 MySQL 核對最大已用編號（禁擅自以空庫或已核准值重設）。
- **`REG-REDIS-05` & `REG-EXPIRY-01～04`（14 天自動清除與拒絕終態）**：
  - 待審申請自伺服器提交時起算固定 **14 × 24 小時（14 天）**，設定不可延長之絕對 `expires_at` 與 Redis TTL（重開／查詢不延長；到期立即清除問卷並釋放主體占用，保留最小「已到期」狀態供查「申請已到期，請重新申請」；轉入核准處理中立即解除 TTL 改受恢復索引保護以防 MySQL 交易中途遺失）。
  - 明確拒絕立終態並立即清除問卷原文（僅留申請號、拒絕時間與操作人供授權回讀）；拒絕或到期後可重新提出新申請（原號重送僅回原終態）。
- **`REG-REDIS-06～08`（兩儲存故障恢復、維護與 AOF 實體整理）**：
  - 核准中 MySQL 未提交：恢復作業讀取處理中索引以原操作識別續走冪等 MySQL writer；MySQL 已提交 Redis 未清除：核對已 commit 回執後僅補行 Redis 終態與刪除，絕不重建案號／Client。
  - 內部維運排程除設定原生 AOF rewrite 外，每小時偵測自上次整理後如有問卷清除則執行一次 `BGREWRITEAOF`，實體抹除舊 AOF 內容（禁止腳本手動刪 AOF）；獨立容器拓樸由 `docker-compose.registration.yml` 與 `REGISTRATION_REDIS_ADMIN_PASSWORD_FILE` 隔離（`registration-intake` 不掛 `.env` 或管理 secret），首次全新空實例以 `scripts.registration_maintenance --initialize-new-instance --once` 初始化並於一般啟動／還原核對既有 SQL 最大編號。

## 4. HCM 進件規範、欄位警示與 `BECLASS-001／IMPORT-003`

### 4.1 欄位規範與七項待補件觸發條件

- **7 項觸發 `partial intake / 待補件` 欄位**：僅 `姓名`、`身分資格`、`報名時間(建檔)`、`預計服務日期`、`希望服務天數`、`服務時間`、`服務方式`（`身分資格` 支援一般市民、補助市民／社福／低收入戶／中低收入戶、原住民〔含別名 `原民`、`原住民市民`，正規化為 `原住民`〕與非市民；其中 `服務方式` 僅缺欄／`NULL`／空白觸發待補件，**非空文字最多 100 字一律原文保留供排班參考而不觸發格式警示或清空**）。
- **零警示／容錯規則**：`縣市` 不產生任何警示或補件要求；`行動電話`（接受手機及含區碼市話）與位於「管理員註記」後一欄之空白表頭 `email` 格式異常時僅記 `NULL` ＋ 非阻擋欄位警示；只要具備合法 `案件編號`（且非已確認作廢之非市民 HCM 報名）即建案／補寫其餘合法 Orders 條款，不預設 `requires_cooking`（待 BeClass 唯一配對後方補寫）。
- **Canonical 服務方式與訂金期限**：`服務方式` 正規化為 `連續服務 | 休周六 | 休周日 | 週休2日`（嚴禁合併 `休周六` 與 `休周日`，全部下游排班／精算必須保留週六／週日差異）；訂金到期日固定 `min(報名時間日期 + 3 calendar days, 預計服務日期)`（急件照常建檔）。
- **Client 欄位投影**：客戶資料唯讀呈現 `identity_status`、`city`、`service_type`、`service_time`、`delivery_type`、`residence_type`（合法空值顯示「尚未登錄」）。

### 4.2 HCM 警示自動重驗、逐欄略過與 `BECLASS-001／IMPORT-003`

- **修正工作簿入口退役與自動重驗**：已退役 `/api/v1/case-import/hcm/resubmissions/{preview|apply}` 與獨立資料中心「目前待修正」清單（`current review.can_correct = false`、`unavailable_reason = hcm_workbook_correction_retired`）；操作者直接透過 [整合名冊](33_案件與月嫂整合名冊正式規格.md)（Client Profile ＋ `clients.due_month`／`clients.reject_reason` 與 Orders Terms）修改，Case Import review Query 即依據最新根事實自動逐欄重驗解除警示。
- **逐欄人工略過（`HCM-REPAIR-03`）**：管理員針對 current HCM review 尚未解決欄位，可經 `/api/v1/case-import/hcm/reviews/{review_identity}/skip-field/{preview|apply}`（及相容 `skip-missing-reject-reason`）逐欄確認略過，於 `case_import_hcm_correction_events` 寫入 `review.skip_field:<source_field>`（不改 Client／Order 業務值，顯示於名冊歷程，新 review 不繼承舊略過）；其他連結／未綁定／歷史警示仍可逐筆手動標記 `closed (manual_warning_skip)`。
- **異常決策矩陣（`BECLASS-001`／`IMPORT-003`）**：

| Code／subject | Active predicate | 唯一合法操作 | Completion predicate | Closed unresolved reasons |
|---|---|---|---|---|
| `BECLASS-001` / `case_no` | 有 HCM 來源但缺唯一 Client BeClass 配對 | 正確 counterpart 經 `IngestCaseImportSource → Preview/ApplyCaseImport`，客戶 BeClass 工作簿的歧義配對依 §2.3 | 形成唯一、一致 accepted mapping＋`recheck` 完成（含 `original_review → source_event → result` lineage） | `counterpart_missing`, `counterpart_ambiguous`, `mapping_conflict`, `owner_readback_incomplete` |
| `IMPORT-003` / `entity_kind + review_item_id` | 有 Client BeClass 但缺唯一 HCM 配對 | 同左（嚴禁於異常頁以姓名／電話手動湊配或強制標記結案） | 同左＋fresh readback 完整 | 同上 |

- **Validator Issue 代碼對齊**：已知驗證狀態不得誤為 unknown：`CLIENT-BECLASS-SOURCE-001`（`client_field_missing:<field_path>`／`client_field_invalid:<field_path>` 區分缺欄與格式錯誤，嚴禁保存錯誤原值）、`HCM-CASE-002/$source_row`（HCM 既有案指紋差異）、`IMPORT-004`（僅供 HCM 來源列驗證失敗，不得將缺少 Client BeClass 投影成 `IMPORT-004`）、`ORDER-HIST-FIELD-01/actual_start_date|actual_end_date`（歷史訂單起迄解析失敗）。
- **Unknown Issue 防護與 Typed Errors**：未登錄 issue code 必須交易回滾並進 3 次間隔 >= 1s 重試後進 dead-letter。Typed Errors：`case_import_source_conflict`、`case_import_row_invalid`、`case_import_identity_ambiguous`、`case_import_candidate_stale`、`case_import_already_applied`、`case_bootstrap_failed`、`import_warning_transition_not_allowed`、`import_warning_resubmission_association_invalid`、`import_warning_predicate_owner_unavailable`。

## 5. 驗收標準

1. **Redis 隔離與非市民進件**：實機 Redis 7 ＋ MySQL 驗證核准前零問卷入 MySQL、`registration-intake` 無 DB 憑證、AOF `always/noeviction` 容量拒絕與斷電重啟、14 天到期解除占用、`REG-REDIS-07` 全部故障點恢復、小時 `BGREWRITEAOF` 整理、`A` 案號跨年並發配號、`501+` 虛擬帳號與 `beclass_records` 退款帳戶同步。
2. **HCM 與雙軌配對**：驗證 7 項待補件／`縣市` 零警示／`服務方式` 原文保留與 4 種 weekday 隔離、`clients.email` 空白補齊、`BECLASS-001／IMPORT-003` 自動解除與不同來源解除 lineage、逐欄略過 CAS 409／同鍵重播，及 180 秒匯入超時跨分頁自動輪詢。
3. **客戶 BeClass 人工配對**。驗證共用候選案件的問卷逐組呈現，同案只顯示一次，切組與關閉保留連線。以同一客戶的兩案驗證一份問卷可勾選兩案、每案各存一筆、重播不增筆、兩案補正獨立，且任一選案失效時該列零寫入。另驗證跨客戶選案、同案重複配對、解除連線及確認前零寫入。無歧義的工作簿直接匯入。
