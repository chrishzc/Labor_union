# Case Import 與非市民 Redis 待審正式規格

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Case Import Domain（`domains/case_import/`、`subsystems/case_import/`）
- 單一負責範圍：多來源進件通道架構（HCM Web Upload、Client／Staff LIFF 與歷史匯入分軌）、非市民自費案件報名與 `A` 字頭配號（`NC-ENTRY-01～03`、`NC-FORM-01～02`、`NC-APPROVAL-01～02`、`NC-NUMBER-01～02`）、**核准前問卷不得進 MySQL 之專用 Redis 7 隔離持久化架構（`REG-BOUNDARY-01～06`、`REG-REDIS-01～09`、`REG-EXPIRY-01～04`、`REG-REFUND-01～03`）**、HCM 整批原子匯入與 7 項待補件欄位／四種服務方式規範、HCM 欄位警示重驗與逐欄略過（`HCM-REPAIR-01～03`）、客戶 BeClass 工作簿人工配對、`BECLASS-001／IMPORT-003` 配對決策矩陣，以及匯入完成統計／自動重查顯示邊界。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[訂單看板、事前日期與歷史採納](01A_訂單看板與事前日期及歷史採納規格.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[Anomalies Domain](06_Anomalies_Domain.md)、[Global Migration 與 Cutover](10_Global_保留資料Migration與Cutover_Subsystem.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[Contract Signing 正式規格](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md)、[LINE 服務說明與選單角色](29_LINE服務說明、客服互動與選單角色正式規格.md)、[案件與月嫂整合名冊](33_案件與月嫂整合名冊正式規格.md)、[營運報表與統計口徑](34_營運報表與統計口徑正式規格.md)。

## 2. 多來源進件、工作簿原子性與彙整顯示

### 2.1 SSOT 與入口分流（`IMPORT-ENTRY-02`）

- Case Import 擁有 BeClass／HCM 原始 row identity、檔案摘要、正規化候選、驗證結果、accepted source→internal mapping 與 bootstrap receipt（不直接持有正式客戶、訂單、排班或帳務根事實；建案一律透過單一 outer UoW 委派各 owner）。
- **BeClass 照護欄位局部處理**。選填照護答案缺少或空白時只讓該欄留空，不阻擋其他有效資料寫入或名冊讀取；單一照護答案無效時保留該欄問題，其他有效照護欄位仍可顯示。原始題名與非空答案保留於來源，未辨識題名不得以空值覆寫其他有效欄位。必要基本欄位、來源歧義及版本檢查仍沿原驗證。
- **入口規則**：
  - **HCM**：僅限經認證後台 Web Upload（`WHOLE_WORKBOOK + archive_required`）；archive 成功若 DB 交易回滾必執行補償刪除。以非空合法 `查詢序號(案件編號)` 為唯一建案鍵：新案建立建置 policy 綁定與訂單；已存在案號同內容 exact replay、異內容 `skipped_existing` 零覆寫（唯允許對空白 `clients.email` 執行 email-only 補填）；不同案號但 `IP + 姓名` 命中既有客戶時照常建案並發非阻擋 link review 警示。
  - **Client BeClass／Staff**：現行來源透過 LIFF → owning Domain API；`Client／Staff Historical Adoption` 採 `ROW_ATOMIC_RESUMABLE + archive_required`（支援斷點續跑；同身分證＋姓名＋嚴格較新報名時間始更新歷史 Staff 純量，空值不覆蓋、`IP位址` 允許 `NULL`）。

### 2.2 匯入統計、未匯入明細與自動重查顯示契約

- **互斥統計（三類合計等於來源筆數）**：HCM、Client BeClass、Staff Historical 統一顯示「`來源筆數／成功匯入／重複略過／未匯入`」（歷史訂單則為 `成功寫入／資料已一致／未匯入`＋另列 `檔外取消`；Staff 歷史匯入依成功採納之不重複身分證累計 `成功匯入`，同人其餘成功列計 `重複略過`，保留逐列欄位合併與中斷續跑原始分類）。
- **未匯入明細（`row_issues`／`row_outcomes`）**：僅列實際未匯入項之位置（HCM 用資料序號，其餘用 Excel 列號）、案號／查號、問題欄位與去敏白話原因（禁止於匯入頁顯示成功但帶警示列、問題導覽或內嵌修正表單；Staff 明細禁洩漏身分證）。
- **Apply 超時自動重查**：HCM、Client BeClass、Staff Historical 與 Historical Order 四者 Apply 每次等待上限為 `180` 秒（協調鎖 `30` 秒）；遇等待逾時／斷線／502／504／鎖等待時每 `5` 秒依同快照與同 `idempotency_key` 背景重查（最多 `6` 次、顯示中性「匯入處理中」而不報錯），允許操作者自由切換分頁或離頁（不阻止導覽且離頁不取消已送出的 Apply，達上限改呈現「等待時間較長，尚未取得最終結果」與手動重查鈕）。

### 2.3 客戶 BeClass 工作簿的人工配對與確認匯入

- **候選範圍**。資料匯入中心的客戶 BeClass 工作簿預覽比對姓名與正規化電話，查找客戶及其 HCM 案件。姓名及電話皆精確命中，且唯一命中一筆客戶及一個可綁定案件時直接匯入。只有姓名或只有電話命中時，即使候選唯一也須透過既有連線抽屜人工確認。一筆客戶有多個案件，或命中多筆客戶而無法唯一確定案件時，將該問卷與可綁定的 HCM 案件列入人工配對。姓名及電話均未命中時不得自動配對。已匯入且來源內容相同的問卷列為重複略過。不可補正的必要欄位格式錯誤、來源衝突或無可綁定案件的列保留原未匯入分類。BeClass 查詢序號識別來源問卷。報名時間、建檔時間、預計服務日期及縣市供人工核對，系統不得用日期接近程度或清單順序代為選案。
- **抽屜與左右核對**。匯入預覽顯示人工配對組數、待配對筆數及「開啟人工配對」。抽屜將直接或間接共用候選 HCM 案號的問卷歸為同組，一次顯示一組，可切換組別或前往下一組待配對。切換組別或關閉抽屜保留本次預覽已建立的連線。抽屜沿用帳務核銷的左側來源、右側目標版型。左欄展開當組待配對問卷，顯示 Excel 列號、BeClass 查詢序號、姓名、遮蔽後的手機、縣市與問卷報名時間。右欄展開當組候選案件，每個 HCM 案號只出現一次，並顯示姓名、遮蔽後的手機、縣市、HCM 建檔時間與預計服務日期。缺值明示「未提供」，日期時間以臺灣時間顯示。
- **連線與改配**。承辦人先點選左側問卷，再勾選右側同一位客戶的一個或多個案件。畫面為每個案件繪製連線，並在兩端顯示查詢序號與案號。已配給另一份問卷的案件顯示其配對對象且不可選。再次點選案件可解除該連線。預覽和連線操作皆為零寫入。
- **確認與套用**。每份待選問卷至少勾選一案或明確捨棄後，可點「檢查配對」核對 Excel 列號、查詢序號與各 HCM 案號。確認畫面分別顯示人工配對的問卷數與套用案件數。點「確認匯入」後，Apply 重驗工作簿、同一客戶及所有已選案件的綁定資格。每案各存一筆來源副本，以「查詢序號＋綁定案號」防止重複，後續補正按案件獨立。任一選案失效或已遭綁定時，該問卷列整批以型別化衝突回報並須重新預覽。匯入分類按 Excel 列計數，人工綁定明細按案件列出成功的對應。結果未明時依 §2.2 以同一組已確認選案重查。
- **捨棄重複問卷**。承辦人可逐列捨棄本次預覽中待人工配對的問卷，捨棄即解除該列連線，確認前可恢復為待配對。所有人工列均完成配對或捨棄後才可確認，其他已配對與可直接匯入的列照常套用。確認畫面列出全部組別的配對及捨棄明細。Apply 僅接受待人工配對列的捨棄，禁止同列同時配對與捨棄；捨棄列不建立來源、案件綁定或補正，不刪除既有資料，收據以未匯入列及 `client_beclass_row_discarded` 原因回報。捨棄名單屬同鍵冪等命令的一部分，結果未明時沿原名單重查。
- **捨棄驗收**。S：同一客戶重複填表，待配對問卷多於可用案件，且同批其他列已完成配對或可直接匯入。T：捨棄多餘問卷並完成本批匯入。A：配對保留列，捨棄重複列，檢查全部明細後確認匯入並重播查詢。R：保留列正常匯入，捨棄列零業務寫入且明示未匯入原因，重播不重複寫入；未處理列仍阻擋確認，同列配對與捨棄及捨棄非人工列均拒絕。
- **重匯與既有資料保護**。同鍵重播、換鍵重匯，以及相同來源另存工作簿後重匯，只回讀原收據或保存匯入分類，不重新套用 Client、Orders 或 BeClass 既有資料。所有欄位的人工改值與已匯入後的明確清空均保留，原始問卷、有效補正、owner 版本及補正事件不因重匯改寫。首次配對時，`NULL` 統一視為從未填寫，不區分是否曾被人工清空；可新增問卷來源副本，並由 Orders 既有命令補入尚未知的下廚需求，已有下廚值維持原值。此規則不使已接受來源的重匯重新套用舊問卷。Web 與歷史工作簿入口均重驗案件綁定資格，不得以另一個查詢序號再綁同一案件而使原補正來源歧義。來源內容衝突沿既有拒絕條件處理，不藉重匯覆蓋既有值。
- **資料保護驗收**。S：問卷已綁定案件，客戶資料與訂單欄位已修改，BeClass 已有文字補正及明確清空。T：重新匯入原問卷並保留目前資料。A：依序以同鍵重播、不同鍵重匯、相同來源另存工作簿，以及另一查詢序號選取已綁定案件。R：前三者保留原資料與收據；另一查詢序號回報案件綁定衝突。完整客戶、訂單、原始問卷、補正狀態、補正事件與原收據均與操作前一致。
- **可補欄位局部匯入（`CLIENT-FIELD-REPAIR-01`）**。Email、縣市、退款銀行代號加分行與銀行帳號格式錯誤時，該正式來源欄位存 `NULL`，其餘合法欄位及唯一案件綁定照常匯入。銀行兩欄各自驗證。銀行代號加分行先將全形數字轉半形，再只保留 `[0-9]` 數字 並保留前導零，例如「銀行００４／分行１-２３４」正規化為 `0041234`；結果須恰為 7 碼，未取得數字或碼數不符均列為欄位問題，不補碼或截斷。銀行帳號仍為不超過 50 碼的數字文字，保留前導零，沿用空白、空格、連字號及全形數字的正規化，不得剝掉中文等非法字元後假裝合法。兩欄皆空白或只填一欄不新增匯入必填條件，退款可用性沿有效帳戶完整性判定。正規化只處理本次輸入，不自動回填已存在的來源或補正資料。查詢序號、姓名與電話比對及人工確認、案件配對、出生日期、報名時間、來源衝突與既有綁定仍沿原拒絕條件。
- **煮食需求局部匯入**。首次綁定補寫尚未知的煮食需求時，Orders 因 `service_data_locked` 拒絕，只略過該欄補寫，保留 Orders 原值，其餘有效資料及問卷綁定照常寫入並計入成功匯入。名冊及案件詳情的煮食欄顯示紅底與原因，沿既有 Orders 鎖定與更正權限，不因欄位警示解除服務鎖。警示依當前 Orders `requires_cooking` 判定，值為 `true` 或 `false` 時解除。人工多案配對只對實際受鎖案件保存該警示；其他來源、版本、綁定及交易錯誤仍沿原失敗邊界。
- **成功列欄位警示證據**。同一列交易保存去敏欄位 issue code 與原查詢序號，不保存錯誤銀行原值。成功列 receipt 的 outcome 保持 `created`，以 `root_id` 與 `review_identity` 關聯來源及問題證據；計入成功匯入，不放進 `row_issues`。人工多案配對仍逐列原子，各案件成功 receipt 指向各自 accepted source 與適用的欄位警示。
- **單項命中與局部匯入驗收**。S：姓名或電話只有一項命中既有 HCM 案件，該案煮食需求未知且服務資料已鎖。T：承辦人確認案件並匯入其他問卷資料。A：預覽工作簿、在既有抽屜連線、確認匯入，再讀回名冊與案件詳情。R：預覽零寫入且不自動選案；確認後有效資料與綁定保存、煮食需求原值不變、僅該欄顯示紅底警示。姓名及電話皆命中且唯一時沿自動配對；兩者皆未命中時不得自動配對；來源或選案衝突不得降為單欄警示。
- **結果回讀**。匯入結果沿用 §2.2 四項統計，另提供可展開的「人工綁定明細」，只列本次實際綁定成功的 Excel 列號、BeClass 查詢序號與 HCM 案號。人工綁定成功屬「成功匯入」的一部分。未匯入明細與人工綁定明細各自依結果顯示，並可從結果頁選擇下一份檔案。
- **綁定失敗原因**。預覽及 Apply 能判定一個案件無法綁定時，未匯入明細區分既有問卷綁定（`client_beclass_case_already_bound`）、既有 BeClass 人工補登（`client_beclass_case_manually_registered`）與缺同案號 HCM 資料（`client_beclass_hcm_case_missing`）。其他選案失效仍使用 `case_import_candidate_stale`。原因不帶既有問卷或人工補登內容。

## 3. 非市民自費進件與專用 Redis 7 待審隔離架構

### 3.1 非市民進件與配號（`NC-ENTRY`、`NC-FORM`、`NC-APPROVAL`、`NC-NUMBER`、`NC-STAT`）

- **進件獨立性（`NC-ENTRY-01～03`）**：非市民可由 [服務閘道 §2](29_LINE服務說明、客服互動與選單角色正式規格.md#2-服務閘道gateway與登記入口規則) 的「非新竹市民 → 尚未申請」進入專屬 LINE LIFF 合併表單，經工會審核取得新 `A` 案號；亦可由承辦人依 §3.1.1 從既有案件帶入資料，透過後台手動非市民建案取得新 `A` 案號。原 HCM 報名及其審核結果保留，禁止沿用原 HCM 案號或假借補件覆活已作廢之補助案件。
- **必填與用語（`NC-FORM-01～02`）**：合併表單套用全部 HCM 必填欄位 ＋ BeClass 既有規則；統一稱「退款帳戶」供一般退款使用；送出僅存待審申請編號，經工會核准方建立正式 Client／BeClass／Order 與非市民費率綁定。一般需求調查（`/line-registration`）與非市民服務申請（`/line-non-citizen-registration`）皆於銀行帳號欄位固定備註「**請填入產婦本人銀行帳號**」，並皆須必填上傳「**存摺封面**」圖片（JPG / PNG / WebP），供工會人員於審核／建檔時核對銀行帳號與分行代碼並一併歸檔至 NAS `02_客戶存摺封面` 資料夾；皆強制要求填選閉鎖**胎數**（`survey_details["特殊計費:胎數"]`，僅接受 `單胞胎` 或 `雙胞胎`）；非市民 LIFF 不重複渲染舊「寶寶資訊」文字欄位，亦不再向客戶索取 `LINE ID`（由客戶主動加入官方帳號並以 LIFF Token 識別；系統保留 `clients.line_id` 欄位供選填／相容）；`baby_info` 由所選胎數（`單胞胎`／`雙胞胎`）同步填入，`ProvisionalRegistration`／非市民檢核於 Preview／Apply 邊界拒絕缺漏、非「單胞胎／雙胞胎」或不一致之 `baby_info` 與「第幾胎」等其他文字，並於核准建檔時寫入 `beclass_records.survey_details` 供雙胞胎費率與整合名冊消費。
- **後台手動新案必填**。客戶姓名、連絡電話、預計服務開始日、服務天數、服務時段、胎數、電子郵件、退款銀行代號（含分行共 7 碼）及退款銀行帳號均為必填。胎數只接受單胞胎或雙胞胎；同一建案交易寫入 BeClass「特殊計費:胎數」，並以此胎數初始化客戶帳務及月嫂薪資。後台表單與建案 API 均拒絕缺漏或只有空白的值。
- **需求調查時薪**。市民與非市民 LIFF 在單胞胎及雙胞胎選項旁顯示 [Client Finance 計價政策](04_Client_Finance_Domain.md#2-核心不變量與計價規則) 的服務時薪。市民以一般市民費率為參考，區分補助內及用盡後費率。非市民顯示自費費率。
- **三節假日雙薪意願**。市民與非市民 LIFF 的「費用與同意條款」及後台手動非市民新案均提供選填欄位，記錄遇端午、中秋、除夕、初一或初二服務時的雙薪意願。可選「是」、「否」或未填。答案保存於需求調查，供名冊維護，業務語意依 [CRX-REGISTRATION-01](33_案件與月嫂整合名冊正式規格.md#52-client-profile-與-beclass-欄位及照護修正crx-account-01)。
- **非市民表單服務時段**。LIFF 與後台手動新案提供相同的服務方式、生產方式及居住型態選項。每日服務時段提供 08:30–12:30（4 小時）、08:30–16:30（8 小時）、09:00–17:00（8 小時）、13:00–17:00（4 小時）。LIFF 表單及 Preview／Apply 僅接受這四個時段。後台手動新案及原案資料帶入可調整每日開始與結束時間，同日起訖時間差須大於或等於所選的 4 或 8 小時；多出的時間可供客戶與月嫂協調休息，不自動增加每日服務時數或扣除固定午休。服務時數與起訖時間分別保存，例如 08:00–17:00 選 8 小時時，每日服務時數仍為 8 小時。前端與手動建案 API 使用相同驗證。LIFF 依預計服務開始日、天數及休假規則推算結束日。退款帳號正規化後須有數字。
- **年度流水配號與後續對齊（`NC-NUMBER-01～02`、`NC-FLOW-01`、`NC-PAYMENT-01`）**：案號採 `A＋民國年度＋3碼流水號`，依正式建案日的臺灣時間年度自 `001` 起算。虛擬帳號依 [Client Finance 帳號規則](04_Client_Finance_Domain.md#23-非市民付款與案件類別篩選nc-fin-0106) 解析。LINE 申請在核准時正式配號。手動新案先唯讀顯示預估案號與帳號，送出時與 LINE 核准共用年度流水號，在同一建案交易內鎖定取號並跳過已使用的案號或帳號，成功後顯示實際配號。可表示的流水號用完時回報衝突。正式建案後的統計、推薦媒合、契約簽署、5 天訂金與分期計價及排班結算沿用既有 owner 流程（見 [營運報表與統計口徑 §5](34_營運報表與統計口徑正式規格.md#noncitizen-statistics-20261029)、[Client Finance §2.3](04_Client_Finance_Domain.md#23-非市民付款與案件類別篩選nc-fin-0106) 與 [Contract Signing](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md)）。

### 3.1.1 原案資料帶入與獨立操作（`NC-MANUAL-01～04`、`NC-SEPARATE-01`）

本節也包含下表既有的時段驗收 `NC-MANUAL-05`。

- 管理端提供「以此案資料建立非市民新案」。承辦人選定來源案，帶入該案可對應的客戶及問卷欄位至既有手動非市民新案表單，核對並補齊 §3.1 必填欄位後確認送出；缺值留待填寫，不猜補其他客戶或案件資料，不要求客戶重新填 LIFF。
- 新案沿既有手動非市民機制新增客戶、配發 A 案號、建立 BeClass 問卷及必要初始化。不改寫來源案號、身分、訂單及歷史，不搬移帳務、銷帳明細、排班或契約；不複製 `line_user_id`、binding 或其版本。退款資料沿既有受權限控制的表單處理，不進入日誌或收據。
- 正常作業由人員先取消洽談中的市民案，再建立非市民新案；歷史訂單重啟後發現身分不符時，由人員使用相同入口處理。系統不依來源案狀態、取消是否完成、歷史／重啟身分或銷帳狀態新增資格檢查，也不要求補救專用模式或原因。
- [取消訂單](01_Orders_Domain.md)、本節建案與 [LINE 綁定轉移](23_LINE身分管理與解除正式規格.md#81-權限與操作介面) 是獨立操作，由人員判斷及選擇。各入口既有權限、必填、版本及交易驗證保留；不自動串接，不新增防止漏取消、重複建案或選錯對象的流程規則，不擴充重送機制。
- 每個操作各自提交，失敗依其既有交易處理，先前成功的操作保留，由人員回讀後決定後續處理；不建立跨步驟回滾。沒有 LINE 綁定不影響建案。

| ID | S 情境與前提 | T 使用者任務 | A 可重現操作 | R 可判定結果 |
| --- | --- | --- | --- | --- |
| NC-MANUAL-01 | 洽談中的市民案 | 正常轉非市民新案 | 取消原案，帶入並補齊資料後確認 | 原案取消及歷史保留；新增客戶與 A 案，問卷及初始化符合 §3.1。 |
| NC-MANUAL-02 | 歷史案重啟後發現非市民，未銷帳且未綁定 LINE | 人工補救 | 依正式流程取消原案，再帶入建立新案 | 建立 A 案並保持未綁定，不要求客戶重填問卷。 |
| NC-MANUAL-03 | 有權限人員選到尚未取消的來源案 | 自行判斷建案 | 帶入、填妥並送出 | 不因原案未取消而拒絕，建案不改動原案狀態。 |
| NC-MANUAL-04 | 來源缺少既有必填欄位 | 補齊後建案 | 缺欄送出，再補齊送出 | 首次拒絕且零建案；補齊後成功。 |
| NC-MANUAL-05 | 後台手動新案或原案資料帶入，選定每日 8 小時且其餘必填完整 | 設定含休息空間的時段 | 依次填 08:00–17:00、08:00–16:00、08:00–15:59；另以手動 API 提交相同內容 | 前兩者可建案，起訖分別保存且每日服務時數仍為 8；第三者前後端均拒絕且零建案。同日起訖、合法時間及 4／8 小時選項限制保持。 |
| NC-SEPARATE-01 | 原案已取消 | 確認建案失敗結果 | 觸發既有建案失敗並回讀 | 原案仍取消；新案依既有交易回滾，不自動重開原案。 |

<a id="registration-storage-refund-projection"></a>

### 3.2 核准前問卷不得進 MySQL 與獨立 Redis 7 架構（`REG-BOUNDARY`、`REG-REDIS`、`REG-EXPIRY`）

- **`REG-BOUNDARY-01～06`（儲存與邊界隔離）**：
  - 查到待審申請只表示收件，不表示已建正式案件。核准前待審問卷內容與完整申請候選**嚴禁寫入 MySQL 任何資料表、outbox、通知或稽核**。
  - 對外收件容器 `registration-intake` 僅持 LIFF token 驗證與專用 `registration-redis` 受限 ACL（僅可讀寫待審內容與計數器命名空間，完全不配置 MySQL 憑證、網路路徑或審核決策權限）；瀏覽器僅呼叫 bounded API。
  - 管理員審核核准於 MySQL 唯一 outer UoW 透過各 owning Domain writer 原子建立正式 Client／BeClass（含同步保存 `beclass_records.refund_bank_code` 與 `refund_account_no`，依 `REG-REFUND-01～03`）／Orders（含非市民建檔）與 LINE binding，並透過 Controlled File Storage boundary 將暫存的存摺封面歸檔至 NAS `02_客戶存摺封面` 資料夾，確認完成後方清除 Redis 問卷原文與暫存圖檔。
- **`REG-REDIS-01～04`（持久化設定與編號）**：專用 `registration-redis`（Redis 7 獨立實例＋持久化卷，禁與 cache 共用；關閉 host port；設定 `appendonly yes`、`appendfsync always`、`noeviction`、`maxmemory 256mb`、`auto-aof-rewrite-percentage 100`、`auto-aof-rewrite-min-size 64mb`）。容量滿或 AOF 錯誤一律拒收而不退回 MySQL。專用 Redis 持久化計數器須於還原後與 MySQL 核對最大已用編號（禁擅自以空庫或已核准值重設）。
  - **無正式資料的部署測試**。使用 `REGISTRATION_USE_SHARED_REDIS_FOR_TEST=1` 時，收件與管理端共用一般 Redis 的同一個實例和資料庫，可在正式登入模式下以測試資料驗證流程。收件端使用 `docker-compose.registration-test.yml`，保留 LINE 驗證服務與無 MySQL 的收件容器。測試暫存沿用既有命名空間。正式資料環境使用專用 Redis。
  - S：部署測試環境只有一般 Redis，管理端使用正式登入。T：讓測試申請寫入與待審清單使用同一暫存來源。A：收件與管理端啟用共用 Redis 測試設定，送出一筆測試申請並開啟待審清單。R：兩端使用相同 Redis 資料庫，管理端可看到該筆申請。停用設定後，正式模式恢復要求各自的專用 Redis 憑證。
- **`REG-REDIS-05` & `REG-EXPIRY-01～04`（14 天自動清除與拒絕終態）**：
  - 待審申請自伺服器提交時起算固定 **14 × 24 小時（14 天）**，設定不可延長之絕對 `expires_at` 與 Redis TTL（重開／查詢不延長；到期立即清除問卷並釋放主體占用，保留最小「已到期」狀態供查「申請已到期，請重新申請」；轉入核准處理中立即解除 TTL 改受恢復索引保護以防 MySQL 交易中途遺失）。
  - 明確拒絕立終態並立即清除問卷原文（僅留申請號、拒絕時間與操作人供授權回讀）；拒絕或到期後可重新提出新申請（原號重送僅回原終態）。
- **`REG-REDIS-06～08`（兩儲存故障恢復、維護與 AOF 實體整理）**：
  - 核准中斷後先分清 MySQL 是否已提交。若未提交，恢復作業讀取處理中索引，以原操作識別續走冪等 MySQL writer；若已提交但 Redis 未清除，核對已 commit 回執後只補做 Redis 終態與刪除，絕不重建案號或 Client。
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

### 4.3 目前進件欄位問題 Query（`IMPORT-FIELD-QUERY-01`）

- `GET /api/v1/case-import/field-issues` 是經管理員認證的唯讀 Query。`case_no` 可選，`page` 為大於等於 1 的整數，`page_size` 為 1 至 100。回傳 `items[{case_no, issues}]`、`next_page` 與可為 `null` 的 `total`。每一 issue 提供 `source`、`owner`、正式欄位 `field`、中文來源 `source_field`、`code` 與去敏 `message`。
- 每案合併 current HCM 尚未解決且未人工略過的欄位，以及成功匯入 Client BeClass 的欄位警示。HCM 沿既有 current review、owner root 重驗與 skip 規則。BeClass 只透過 `created` receipt 的 `root_id`、`review_identity` 與 accepted `bound_case_no` 連結，不能把失敗重匯的同查詢序號 review 投射到舊案件。
- 查詢每次讀取正式 owner 值。BeClass 來源的 Email／縣市以 Client Profile 的 current value 及原驗證規則判定，`owner=client_profile`；銀行兩欄以 BeClass 有效修正獨立判定，`owner=client_beclass`。合法 owner 值解除該欄警示；銀行明確補正為合法選填空白也可解除，不改寫原來源與 review evidence。通知工作台與名冊共用此 Query，不另存問題狀態。
- 候選案件先去重且有界分頁，再依 current facts 過濾已解決欄位。即使本頁過濾後為空，仍保留候選的 `next_page`。Query／owner 讀取失敗必須回報錯誤，不得轉成空清單或零問題。

## 5. 驗收標準

1. **Redis 隔離與非市民進件**：實機 Redis 7 ＋ MySQL 驗證核准前零問卷入 MySQL、`registration-intake` 無 DB 憑證、AOF `always/noeviction` 容量拒絕與斷電重啟、14 天到期解除占用、`REG-REDIS-07` 全部故障點恢復、小時 `BGREWRITEAOF` 整理、`A` 案號跨年並發配號、`501+` 虛擬帳號與 `beclass_records` 退款帳戶同步。
2. **HCM 與雙軌配對**：驗證 7 項待補件／`縣市` 零警示／`服務方式` 原文保留與 4 種 weekday 隔離、`clients.email` 空白補齊、`BECLASS-001／IMPORT-003` 自動解除與不同來源解除 lineage、逐欄略過 CAS 409／同鍵重播，及 180 秒匯入超時跨分頁自動輪詢。
3. **客戶 BeClass 人工配對**。驗證共用候選案件的問卷逐組呈現，同案只顯示一次，切組與關閉保留連線。以同一客戶的兩案驗證一份問卷可勾選兩案、每案各存一筆、重播不增筆、兩案補正獨立，且任一選案失效時該列零寫入。另驗證跨客戶選案、同案重複配對、解除連線及確認前零寫入。無歧義的工作簿直接匯入。

4. `CLIENT-FIELD-REPAIR-01`／`IMPORT-FIELD-QUERY-01`。
   - S：唯一可綁定客戶的 BeClass 列含非法銀行代號或帳號，或 Email／縣市格式錯誤。T：匯入合法資料並補正該欄。A：Preview／Apply 後由共同 Query 與名冊查詢，再經正式 owner 修改單欄並重新查詢。R：列計成功、非法來源欄為 NULL、合法欄保留；各欄警示獨立顯示及解除，主檔合法自由文字縣市可解除，原 review 不變且不含錯誤銀行原值。
   - S：缺識別／唯一配對、既有來源衝突、失敗重匯或 owner Query 故障。T：避免錯綁、誤清警示及假成功。A：提交同查詢序號異內容、非法識別與多案失效案例，並讀取分頁。R：原拒絕與整列原子性保留，失敗 review 不掛入已成功案件，讀取錯誤不變成空結果；已解決候選空頁仍可沿 next_page 繼續。
