# Client Finance Domain

> 2026-11-05 全額補助免自備最新裁決：依 [`22` §17.4.1](22_銀行流水匯入與帳務異常處理正式規格.md#full-subsidy-no-advance-20261105)，補助市民／原住民且H≤本案有效補助上限L，自動S＝T、B＝0、方案一、轉交月嫂，不需客戶實付或人工免自備確認；H>L回一般三方案，缺值不當0。這是下文「不由身分／時數判方案」的一項明定例外，不恢復固定120／80路由。本輪只更新規格及方案，不修改程式或資料。

> 2026-11-03 案件帳務最新裁決：依 [§0.3](#client-case-accounting-schemes-20261103) 與 [`22` §17](22_銀行流水匯入與帳務異常處理正式規格.md#case-accounting-schemes-20261103)，案件總額、客戶負擔、客戶應繳工會及補助流向分開；除§0.3 CF-SCHEME-FULL及規格22 §17.4.1明定的全額免自備例外外，不再由客戶身分直接決定先墊／免墊、退款對象或三種方案。本次僅更新規格，程式及歷史資料未依本次改動。舊 PRICE-01／03／04、QUAL-FIN-04 及下文身分固定推導退款的敘述，在此範圍由新契約取代；身分／資格、既有政策快照與非本次重訂的費率、日期來源不自動改寫。

> 2026-11-02 差額認列、人工金額更正與政府整期差額的最新實作／驗證見 [規格22 §16.9.1](22_銀行流水匯入與帳務異常處理正式規格.md#accounting-differences-implementation-20261102)。本檔 2026-11-01 的「尚未實作／本次僅規格」為當時記錄，以該續作結果為目前狀態；bank／ledger／allocation 的不可變性與各 owner 歸屬不變。


## 0. 帳務參數與個案分段計價（2026-10-29 最新人工裁決）

2026-11-03 實作授權補充：使用者要求先核對規格書，再依序修正後端、前端，最後以實際瀏覽器檢查身分相關頁面、抽屜及分頁。本次施工範圍為一般市民／補助市民的身分語意與流程對齊；原住民條件分界、HCM 作廢新流程及資料回填仍保留原先未收斂／未授權邊界，不由本次名稱修正補定。

**IDENTITY-FIX-01**：一般市民與補助市民維持不同正式身分及可追溯的 `citizen`／`social` 歷史政策標記；原補助上限分別為 40／120，實際上限依本案政策。除規格22 §17.4.1明定的全額免自備例外外，身分與政策標記不單獨決定本案先墊、退款或補助轉交對象，帳務方案依 §0.3 及 `22` §17。HCM 保存兩者為不同身分，不再將一般市民併為補助市民；社福／低收入戶／中低收入戶僅作可追溯的補助市民來源別名。上限與四段費率仍可由本案有效政策／人工設定決定，不依名稱修正覆寫金額。

**IDENTITY-FIX-02**：新政策使用一般市民／補助市民／非市民的正式名稱及既有 typed rule；歷史政策、已綁定案件與人工事件按原快照的名稱與 rule 讀取，不改寫不可變版本。帳務參數畫面可從舊版本建立正確命名的新稿，保留時數、四費率、原住民等自訂身分及其已保存規則，歷史頁維持可辨識原版。若目前生效政策仍使用舊的「補助市民 citizen／社福 social」命名，新一般／補助市民進件不得錯綁舊命名項目，須以 typed 業務原因要求先建立正確命名的新政策；既有案件不因此換版。實際政策發布、source DB 變更與舊案修復另依既有執行門，不在程式修改時自動執行。

**IDENTITY-FIX-03**：身分保真、來源別名、資格分類、政策版本與不可變歷史仍須驗證；一般／補助市民的名稱不能混併。舊依身分驗退款、訂金及月嫂付款路徑的驗收內容已取代，僅供歷史追溯；新三方案驗收依 `22` §17／18，不從舊測試結果推導新流程。原住民補助內費率防護與既有可讀資料不因本次放寬或回填。

**IDENTITY-FIX-04（2026-11-05）**：使用者明確要求修正舊身分轉換，涵蓋未來匯入及保留資料升級，不只調整合成資料。HCM 原始一般市民不得轉成補助市民；原住民、補助市民原值保持。現行升級依規格10的v5 successor保留來源身分、政策綁定、人工更正及已成立帳務，不再執行`subsidy-period-policy-v1`的舊更名／退款重算。即使沒有舊marker或已有更名日誌，亦不得重套舊對照；未知舊值保持待確認。此修正不新增身分編輯入口，不依40／120等數字反推舊案，也不授權production遷移。

**歷史驗證紀錄標示**：以下身分驅動帳務路由的驗收已取代，僅供歷史追溯；保留當時實測內容及數量，不代表 `22` §17／18 已實作。

2026-11-03 repository-local 驗證：身分／計價／HCM／薪資／補助 focused tests 232 項通過；最後補正退款清單與政府報表依綁定 rule 分類後，對應 34 項及週報／XLSX 契約 54 項通過。實際 disposable MySQL 10 項通過，含舊命名 citizen 40 小時仍列應退 12,000、新 social 案不列客戶退款。前端 focused 62 項、客戶名冊 42 項、型別檢查與建置通過。Chromium 使用合成資料操作實際 React 頁面：帳務參數兩分頁／舊新版本、客戶名冊兩類案件抽屜及個案儲存回讀、補助明細兩類抽屜、週報三分頁、季／年報、待辦統計及手機版；無 page error。手機帳務身分欄保留最小寬度並以表內水平捲動呈現。架構與測試歸屬檢查通過。既有 source DB、實際政策發布、歷史資料辨識／回填與原住民分界流程均 NOT_RUN，不以本機合成資料驗證外推已上線。

### 2026-11-03 補助資格與原住民身分補充（一般／補助身分修正依 IDENTITY-FIX；其餘僅規格）

Authority：使用者明確裁決非市民屬補助資格不符合、仍可另走非市民自費報名與專用案號；社福資格不符但符合一般市民資格者歸一般市民符合；新增原住民身分、補助時數由帳務參數設定，目前預設 80 小時；案件不得重複計數。本補充原為僅規格；一般／補助市民程式修正已由上方 IDENTITY-FIX 授權。原住民流程、HCM 作廢、實際政策發布、資料回填與既有帳務重算仍不在本次執行範圍。

- **QUAL-FIN-01**：市民／社福／原住民的補助資格與自費服務受理資格分開。非市民補助為零，不代表不能接受服務；其正式自費案件須依 `17` §5.1.1 另行報名、核准及取得 `A＋民國年度＋3 碼流水號`，原 HCM 報名作廢，不以修改原 HCM 案件身分或沿用原案號代替。非市民既有定金、分期、自費及薪資規則維持。
- **QUAL-FIN-02**：依使用者同日最新更正，正式補助身分類別就是「一般市民」「補助市民」，本次再加入「原住民」，不是只供週報顯示的稱呼。「一般市民符合」對應一般市民資格，原規則最高 40 小時；「補助市民符合」對應補助市民的社福資格，原規則最高 120 小時；原住民目前預設 80 小時，由帳務參數設定。社福資格不符合但一般市民符合時，最終補助分類歸一般市民，不直接判為整案補助審核不符合。「社福」可描述補助市民資格或既有內部規則，不取代此正式身分名稱；先前將一般市民改稱補助市民、補助市民改稱社福的規格敘述由本裁決取代。既有資料辨識及實作落差見 `14` §1，不以文件改名直接重解讀或回填舊資料。
- **QUAL-FIN-03**：新增「原住民」身分，其補助時數上限由本節既有帳務參數設定管理，目前預設為 80 小時。80 是本次確認的可設定政策預設，不是固定於報表、政府補助公式或所有既有案件的常數；案件仍依 PRICE-02 綁定適用政策，人工調整及不可變保護沿 PRICE-03／07／08。政策發布、既有案件換版、回填及已核銷金額重算均不在本輪授權內。
- **QUAL-FIN-04**：補助資格與工會經手方案分開。原住民及其他身分的補助上限仍由本案有效政策／人工設定管理；客戶應繳工會、是否先墊、補助轉交對象及月嫂實付依 §0.3／`22` §17，除規格22 §17.4.1明定的補助市民／原住民H≤有效L自動免自備外，不以身分或固定小於／大於80小時切換帳務路徑。

| 正式身分類別 | 補助上限來源 | 工會收退款方案 |
|---|---|---|
| 一般市民 | 原規則 40 小時；實際依本案政策／人工設定 | 一般三方案依本案繳款、安排及真實收付款，不由身分單獨決定；全額免自備例外限下列兩身分 |
| 補助市民 | 原規則 120 小時；實際依本案政策／人工設定 | H≤本案有效L時依22 §17.4.1自動免自備、方案一、轉交月嫂；其餘依一般三方案 |
| 原住民 | 帳務參數管理，目前預設 80 小時；實際依本案設定 | H≤本案有效L時依22 §17.4.1自動免自備、方案一、轉交月嫂；不把80寫死為分界 |

身分資格、補助上限與重疊資格去重仍沿原 owner；本表不改既有政策、已簽文件、核銷金額或已形成日期。政府實際款、退客戶款及付月嫂款仍各由原 owner 保存。

**已取代，僅供歷史追溯**：先前「原住民小於 80 同補助市民、超過 80 同一般市民」及一般／補助市民固定先墊／免墊的比較表，不再是現行帳務規則；原需釐清比較時數、等於 80 及分界隨上限變動的問題不再作為帳務方案阻塞。歷史金流與已形成到期日保留。

仍待資格 owner 收斂的是同時符合原住民及社福等重疊資格時的適用身分／補助政策選用；不得把此資格問題混成三方案金流判斷，或擅依時數大小選身分。案件去重與資格統計依 `15` §15.1.1。

### 既有帳務參數與計價契約

名稱適用：以下規則按 QUAL-FIN-02 的最新身分裁決解讀。早前「補助市民 40／社福 120」的命名不再是本規格的正式分類；正確為一般市民 40／補助市民 120，原住民補助上限由參數設定、目前預設 80。內部 `citizen`／`social` 的新案及新政策對齊依 IDENTITY-FIX；既有資料辨識／回填另案處理，歷史綁定快照與不可變交易不改。

Authority：本次對話已核准獨立主頁、客戶名冊 Drawer 人工調整、四種時薪及開始實作；付款月份以最後裁決為準，兩類皆由服務結束月份起算。本段既有實作授權不擴張到上方 2026-11-03 僅規格補充。

- **PRICE-01**：帳務作業左側新增獨立「帳務參數設定」，與帳務中心同層。不得併入既有收款帳戶／帳務工作區。保存版本、生效日、身分補助上限、客戶及月嫂各自的補助內／用盡後時薪、胎數費率與選填變更說明（省略或留白保存空字串）。新增身分的資格及政策適用仍須明確；原住民依 QUAL-FIN-03／04 保留資格與上限。帳務參數不以身分直接指定三方案、給付對象或客戶應退；本案已形成分期條款及到期日不因此任意改動。
- **PRICE-02**：以案件在系統首次建立時間（臺灣時間）選取當日 00:00 已生效的最新政策，立即綁定版本；待補件案件亦須綁定。之後補件、改期、重播及新政策發布不換版。既有案件保持既有參數及已形成日期；無新政策綁定時保持原規則，不推定最新版。
- **PRICE-03**：客戶名冊右側抽屜新增「個案計價調整」區塊。可人工設定本案補助上限、客戶補助內／用盡後時薪、月嫂補助內／用盡後時薪。依 2026-10-29 最新人工修正，調整原因選填，留白保存空字串；直接儲存，不顯示影響預覽或另行確認，也不執行隱藏預覽。與任何政策日期、服務開始日期無關；本案已形成的訂金／分期條款及到期日保留；補助與付款流向依 §0.3 的案件方案及真實交易。人工設定優先於預設身分／胎數費率，並保留原政策及不可變調整事件。未儲存離開須可繼續編輯、捨棄或儲存後離開；儲存結果未確認時保留修改並阻止離開。
- **PRICE-04**：補助時數在整案服務日期序列上累計，跨月嫂、分期或改期不重置。補助內時數=min(有效服務時數,本案上限)，超額為剩餘時數。客戶扣補助後負擔、應繳工會及補助轉交對象依 §0.3 分開記錄，不從身分推先墊／免墊。非市民補助仍為 0，服務金額不因此清零。樓層費、原雙倍薪倍率及實際服務 ownership 維持原契約。350→300 為可設定情境，不代表預先發布新價格。
- **PRICE-05**：新分段計價不再使用「全補助」特殊分類或客戶零應付的分類 gate。月嫂客戶負擔部分在服務結束月份次月 15 日給付；直接補助部分在服務結束月份次次月 15 日給付；均不以客戶／政府實際入帳月份起算。客戶先墊的部分按客戶負擔期程。整案可按來源分期，總額、實付及未付守恆，禁止重複建立或付款。
- **PRICE-06**：Client Finance 擁有客戶費率、補助涵蓋與客戶應退；Payroll 擁有月嫂分段薪資及給付月份；設定 application 組合各 owner typed facts，單一 outer UoW 保存。個案直接 Apply fresh-lock Orders／Finance／Payroll／pricing facts，以本案 pricing revision 驗 concurrent 個案計價修改，並按當次最新 owner facts 同步；stale 或 same-key mismatch 為 typed 409，重播不追加事件。既有 Preview entry 保持零寫入；既有 Apply 若明確攜帶 preview fingerprint，仍驗其有效性，但直接儲存不要求該欄位。
- **PRICE-07**：個案 Apply 由既有 writer 同交易同步未結清義務，已收付款只以原 owner 差額／退款／追償承接，既有流水及已簽文件不改寫。已核銷補助期間的金額快照不得覆寫；涉及其補助金額改動且沒有正式更正入口時 typed blocker、零寫入。
- **PRICE-08**：政府補助按補助內有效時數及本案月嫂補助內單價計算，不使用超額單價或混合平均。是否存在客戶應退及其正式金額由 Client Finance 依 §0.3、案件已確認方案及既有證據決定，不由身分或單一費率直接建立退款；不得任意改給付資格或自造實際收付。
- **PRICE-09**：additive migration 保存原資料，新增政策／案件綁定／人工事件與必要給付分期資料。fresh 與 preserve 都可使用，不回填或重算既有帳務。無 production、外部付款／通知、deployment、entry switch 或 Git 提交授權。

2026-10-29 最新人工補助防護（適用 PRICE-01／03／04／08）：補助範圍內客戶與月嫂時薪必須相等，供政府報帳使用；新模型不以客戶／月嫂費率差形成工會抽成、手續費或利潤，案件總額與月嫂應收關係依 §0.3。**已取代，僅供歷史追溯**：舊用盡後費率差可作工會利潤的設計不再適用；歷史費率、快照及原實付保留，具體計價接線未收斂前不暗改資料。政策（含新身分／雙胞胎）及個案 Preview／直接 Apply 均由 Domain 驗此規則，違反時 typed 422、零寫入；前端即時提示並阻止儲存。既有不等費率資料維持可讀，由人員修正後經原 Apply 保存，不暗中修復、回填或重算。非市民補助時數、補助內客戶／月嫂時薪、補助實際時數、政府補助與應退補助均為 0；過去非市民資料中未使用的補助內費率按 0 解讀，不修改其不可變原始紀錄。自費及月嫂薪資仍按用盡後費率計算，不能因補助為 0 將服務費／定金／薪資清零。零補助案件的基本自費費率使用用盡後費率；有補助時數時補助內費率必須為正整數。

**Reporting 案件總額唯讀投影**（2026-11-04，`15` §15.4）：`case_total_amount` 由完整有效 `CasePricingFacts` 組合服務費及一次樓層費；Domain `calculate_case_total_amount` 保留補助內服務費、超額及雙倍日，補助僅改變資金來源。報表不以扣補助後應繳、月嫂薪資或現金實收代替整案金額，不修改計價 writer、政策或歷史資料。

Acceptance：A1 新政策保存／查閱／版本衝突／冪等；A2 生效日前後、待補件後完成及既有案不換版；A3 四費率、身分繼承、雙胞胎與整案補助用盡邊界；A4 名冊人工直接 Apply／原因選填／回讀及金流守恆、未儲存離開保護及同命令重試；A5 服務結束月+1／+2（含跨年）及已付部分防重；A6 政府核銷保護、已簽文件不改寫；A7 fresh／preserve additive、API 權限與桌面實際畫面。



<a id="noncitizen-finance-20261029"></a>

### 0.1 非市民付款與帳務統計（2026-10-29 人工確認）

狀態：`implemented / repository-local-verified`。使用者已於 2026-10-29 核准七階段實作與逐階段驗收；執行範圍及實際證據見 [非市民案件實作工作包](../非市民案件實作工作包.md)。此狀態不代表已部署、使用正式資料或完成外部 provider 驗收。

- **NC-FIN-01**：正式核准建案時依現有非市民身分規則及 §0 PRICE-02 綁定適用費率政策，服務費全數自付；不另訂一組固定費率或給付政策。後續修改及月嫂報酬沿各 owner 的既有規則。
- **NC-FIN-02**：定金按 5 天服務費收取，繳款、入帳、核銷及後續結算沿用現行非市民規則。剩餘服務費的分期金額與繳款期限沿用本 Domain 既有公式，包括第一期、第二期及其零金額／日期處理，不因 LIFF 來源另算一套。
- **NC-FIN-03**：客戶及月嫂契約套用現行非市民政策與適用的自費條文；契約、繳費資訊及核銷共用本案付款投影與 §8 虛擬帳號結果。退款帳戶保留原 BeClass 的銀行、分行及銀行帳號及既有必填規則，用於一般退款，不因非市民無補助而移除。
- **NC-FIN-04**：帳務統計新增「案件類別」篩選，選項為「補助案件」（預設）、「非市民案件」、「全部案件」。補助案件維持原有非市民以外的案件範圍；全部案件為兩類的聯集，不重複計入同一案件。
- **NC-FIN-05**：上述篩選同步作用於相關案件明細、件數與金額合計；查詢及合計須使用相同案件集合。分類依正式案件身分／既有身分規則，不只用 A 前綴判斷，以免既有非市民漏入原統計；不以身分類別重算 ledger、核銷或應付。
- **NC-FIN-06**：帳務分類篩選不取代 Reporting 的獨立案件統計。補助申請統計保留原 HCM 審核不符合結果、排除另行核准的非市民自費服務案件；非市民獨立統計依核准建案日計數，詳 `15` §15.1.1／§15.3。此區分不改本節 ledger／帳務案件集合與金額。

後續驗收：現行非市民政策／5 天定金及剩餘分期與期限一致；退款沿既有 owner；帳務預設排除非市民、單獨非市民及全部案件三種集合互斥／聯集正確，明細、件數及金額合計一致；Query 不修改帳務。此輪未執行程式驗收。

<a id="client-differences-20261101"></a>

### 0.2 差額處理與人工金額更正（2026-11-01 核准；尚未實作）

跨帳務流程及驗收見 [`22` §16](22_銀行流水匯入與帳務異常處理正式規格.md#finance-differences-20261101)；本 Domain 仍擁有客戶金額、義務與分配。

- **CF-DIFF-01**：核查確認系統應收或客戶應退款計算結果／數值有誤後，可手動更正系統金額；不只等同調費率。保留原計算、更正前後及操作紀錄，沿正式 owner writer 表達，再重新核對；銀行事實、不可變義務／ledger／allocation、已簽文件及已核銷政府快照不得覆寫。
- **CF-DIFF-02**：原應收正確但少收，目標是先記實收、原款保留待收，再補款接續。人員可追收差額或協調後期合繳；後續同筆入款按已確認歸屬分配至各期，不重複計款。這是下述 exact-only／same-stage 限制在明示差額處理時的核准例外；現有程式尚未具備，不宣稱已支援部分收款或跨期。
- **CF-DIFF-03**：多收另列退款，超退另列追償；直接核銷並認列差額依適用處分類型，不猜工會損益。金額更正、差額認列、實際收付及通知各自保留狀態；通知不結清欠款。
- **CF-DIFF-04**：已確認歷史原因無法查明後，僅記案件帳務人工核銷，保留原差額及操作紀錄；該類案件排除實際金額統計，不補造付款、不直接計工會損益、不改 Orders lifecycle。原有 historical `paid／settled` 不等同此案件標記。
- **CF-DIFF-05**（2026-11-01 已確認；尚未實作）：人員可選「同意減收服務費」，只減少客戶應收，差額由工會承擔，月嫂原應付薪資保持不變，不連動修改 Payroll／Staff Payables 的薪資、實付或待付。保留原應收、減收金額、有效應收、實收、剩餘待收、協議依據及操作紀錄。原款剩餘待收為 0 且正式處理成立才顯示「已減收結清」；銀行原始金額不變。此為原計算正確後的協議減收，與人工更正計算錯誤分開；完整例子及驗收見 [`22` §16.3.2](22_銀行流水匯入與帳務異常處理正式規格.md#difference-client-reduction-20261101)。
- **CF-DIFF-06**（2026-11-01 已確認；尚未實作）：客戶入款差額確為手續費時，需由人員確認金額及工會負擔依據後，才能使用「由工會負擔手續費」處理。原應收保持原額，費用另列，銀行實收不改，月嫂薪資、實付及待付不變。無其他待收且正式處理成立才顯示「已結清，工會負擔手續費」；另筆銀行扣費沿原支出處理一次，不重複列費用或扣應收。完整淨額入帳／另筆扣費例子及驗收見 [`22` §16.3.3](22_銀行流水匯入與帳務異常處理正式規格.md#difference-union-bank-fee-20261101)。
- **CF-DIFF-07**（2026-11-01 已確認；尚未實作）：客戶退款多退所形成的追償，可使用「工會承擔超付款，不再追回」。由人員確認承擔金額與依據後，針對指定追償款處理；原退款應付與全額實付不改，承擔額另列。追償剩餘款全部處理且正式結果成立才顯示「已由工會承擔，不再追回」；未處理款仍待追回，不新增假入款或第二筆出款。保留原退款、追償、已收回／承擔／剩餘金額與依據及操作紀錄。月嫂多付的同類處理由 Staff Payables 擁有，不跨 owner 推定結清；完整例子見 [`22` §16.3.4](22_銀行流水匯入與帳務異常處理正式規格.md#difference-union-assume-overpayment-20261101)。
- **CF-DIFF-08**（2026-11-01 已確認；尚未實作）：僅客戶退款少退及客戶多付款不用退回，可由人員主動選「確認不用再補付／退款」，結束指定剩餘待退並顯示「已結清」。此為系統提供的選項，沒有預設選項，不因金額或其他條件自動選取／結清；未選時原待退款保留。原銀行實收／實付不改，不另存同意證明、免付／免退金額明細或本次操作紀錄；其他選項已確認的紀錄範圍不變。不適用月嫂薪資少付或政府款；完整範圍及驗收見 [`22` §16.3.5](22_銀行流水匯入與帳務異常處理正式規格.md#difference-close-payable-20261101)，人工差額選擇依 `DIFF-CHOICE-01`。
- **CF-DIFF-09**（2026-11-01 已確認；尚未實作）：依該筆目前「自動計算／人工更正」模式判斷，不依歷史上是否曾修改。自動模式在來源變動後沿正常計算直接更新；人工模式保留人工值，另顯示新計算。選「採用新計算結果」時更新金額並恢復自動，之後資料再變直接更新；再次手動更正才切回人工模式，未採用前不因重新整理／計算覆蓋人工值。恢復自動不刪既有更正紀錄；銀行收付、核銷證據與受保護快照不改，已收付款的影響沿原差額／退款／追償承接，Query 不寫帳。完整例子與模式往返驗收見 [`22` §16.4.1](22_銀行流水匯入與帳務異常處理正式規格.md#difference-manual-recalculation-20261101)。
- **CF-DIFF-10**（2026-11-01 已確認；尚未實作）：已辨識同案的多筆入款按案件展示各筆銀行明細與本次合計；合計符合本次應收時，人員可直接一起核銷，不因單筆金額不同、同案多筆或有多期待收而報錯／強制再確認期款。例：應收 10,000，先匯 9,000 並在匯入前自行補 1,000，合計正確即可核銷；不要求先部分核銷或逐筆更正。合計尚有差額才走差額處理。各銀行來源及防重保持原義，不新增期款猜測／提醒規則；完整原則及驗收見 [`22` §16.5.2](22_銀行流水匯入與帳務異常處理正式規格.md#client-case-receipts-total-20261101)。
- 本次不設退匯功能或獨立更正／操作異常章節；既有 return／reversal 歷史證據仍可追溯，沒有 API／writer 退役施工授權。原 PRICE、非市民計價與分類不因此重算或回填；認列、受保護款項更正及政府資金銜接等未定細則見 `22` §16.7。

<a id="client-case-accounting-schemes-20261103"></a>

### 0.3 案件金額、各期繳款與三種方案（產品契約已核准；實作範圍分列）

Authority：使用者於2026-11-03採用第三版「帳務方案、對帳來源與核銷規格草案」；後續精簡案件／期款通知／人工方案的正式施工授權及限定結果見22 §18.1、§18.10。**已取代，僅供歷史追溯**：當時「先修正規格書、不修改程式」只描述原文件階段，不是現行全面未實作的結論。跨域公式、方案判斷表、銀行來源及驗收唯一以 [`22` §17](22_銀行流水匯入與帳務異常處理正式規格.md#case-accounting-schemes-20261103) 為準；本節維護 Client Finance 的直接責任，不新增第二套規則。

- **CF-SCHEME-FULL**：全額補助例外唯一沿規格22 §17.4.1 FULL-01～05：正式身分為補助市民／原住民且H≤有效L，自動S＝T、B＝0及方案一，不再要求人工免自備、客戶實付或先有零額期款；不新建客戶補助退款，H>L及未知來源回一般規則／待確認。零期款判定使用明確免繳來源，不能把一般缺件當0；計價／既有收款與規則不一致沿原owner查核，不由Query重寫。

- **CF-SCHEME-01**：案件總額 T＝服務費＋樓層費／其他費用，月嫂應收合計＝T，客戶應付（補助扣抵後的負擔）＝T－政府補助 S。客戶應繳工會 B 與上述負擔分開，分別入款時 B＝T－S，先墊後退或政府直接付客戶時 B＝T；這是既有繳款安排／歷史金額關係，不是依進行中人工選擇重算B的命令。補助與客戶款是資金來源，不得在 T 之外再加付月嫂補助。
- **CF-SCHEME-02**：一般需繳案件的訂金應繳額＝訂金服務費＋樓層費／其他費用；B＝訂金應繳額＋第一期應繳額＋第二期應繳額，其他費用只計一次。一般案件各期沿本案獨立保存的繳款安排與歷史證據，不先用待分類方案生成金額，再用該金額證明方案；CF-SCHEME-FULL則由明定身分與H≤L直接成立B＝0，不以先有期款為分類前置。歷史訂單的訂金、第一期、第二期均已正式繳齊，才啟動既有自動方案辨識；進行中人工方案可提前保存、不據此改前三期金額，依22 REVIEW-01／02；零金額期款不阻擋。分次付款、明示跨期分配及沖正保留原證據；未明確分配的超收不能直接視為另一未繳期款已繳。
- **CF-SCHEME-03**：永豐客戶入款為 C，永豐正常退客戶為 R永，台新退客戶先墊補助為 R台；兩種退款性質分開。台新補助轉交月嫂屬 Staff Payables 的 P台，不建立客戶退款或第二筆薪資。身分、補助上限、查無政府入款或新報表格式，都不能單獨決定本案退款對象。
- **CF-SCHEME-04**：歷史自動辨識先檢查CF-SCHEME-FULL免自備例外，其餘款未齊不自動分類、齊款且證據唯一才辨識，否則待確認。進行中案件由人員設定補助歸屬，可提前選擇，不套此自動分類門檻，也不改既有金額／款項。分類不等於退款完成；工會退客戶須有正確對象、案件及金額的真實有效付款紀錄才核銷，部分退款保留待退。先前身分驅動的自動 `subsidy_return`／預估不得被當成本次新方案已確認的證據。
- **CF-SCHEME-05**：政府直接付客戶時，工會只確認方案安排、產生政府補助清單，不追蹤客戶是否實收補助、不要求政府撥款或客戶收款證明，也不建立工會待退款。歷史義務、退款、沖正與人工處理證據保留；本次無回填、重算、清除或搬移授權。
- **CF-SCHEME-UI-01**（2026-11-05已核准並限定接線）：現行操作沿[22 §18](22_銀行流水匯入與帳務異常處理正式規格.md#finance-six-surfaces-ui-20261104)。所有抽屜沿客戶名冊同寬，案件精簡摘要保留月嫂、實際起訖、T；下方只有客戶繳款／補助退款方案兩區塊，不是分頁。期款列含日期、應繳、已收／待收、已核銷入帳資訊、最近成功通知時間及按鈕；已繳齊／免繳灰色鎖定，來源不足不假造尚未通知或已關聯銀行資料。通知與人工方案在同案子畫面返回原區塊、捲動及焦點；核銷／問題帳務集中銀行對帳。人工方案可提前保存，客戶款齊且已保存才移出；不改應收、實收、已形成日期或既有免繳計算，不提前生成補助退款與應付。移除收付／歷史區塊不刪既有證據，月報兩口徑及原合法查閱工具保留；人工安排與應付承接已核准依16 §2.5.5，保存及移出不代表下游款項已成立或已付款；正式抽屜、通知來源與人工保存的既有接線／驗收及本機schema-only升級見22 §18.10，不擴張成新模型、下游應付或真實通知已全面完成。本輪僅清理文件，不重驗或修改程式與資料。**已取代，僅供歷史追溯**：較早「正式程式／schema／DB不修改」為當輪文件範圍。**已取代，僅供歷史追溯**：三分頁、全期金流卡及案件內核對的顯示契約，舊PASS只證明當輪版本。

新模型的工會職責為經手轉交及確認自身收付，沒有抽成或手續費收入；舊文允許客戶／月嫂超額費率差形成工會利潤的說法不再作為新模型需求。已存在的不等費率及非現金差額處理仍是歷史／現行實作證據，不得據此降低月嫂應收、補造實收或把非現金結清視為真實退款。本次不自行重訂服務費計價參數、分期天數或付款日期；其與新模型的實作銜接須後續另行收斂與授權。

## 1. Domain 責任

擁有客戶付款條款、訂金／各期款／adjustment／退款／補助退還義務、不可變正式交易與 allocation、核銷 Preview／Apply、超收與退款義務，以及 current balance／settled projection。

不擁有 Orders lifecycle、assignment、正式服務日、客戶身分根值、銀行原始流水或 Alert workflow。

## 2. SSOT

| 資料 | 唯一權威 |
|---|---|
| 付款條款與到期日 | `PaymentTerms` root facts |
| 本案專屬虛擬帳號 | Client Finance 依 §8，從既有 canonical 9 碼案件編號或非市民 A 開頭案件編號確定性產生；Finance Import 消費同一 typed 結果；舊流程案件可保存實際虛擬帳號對照 |
| 應收／退款／補助退還義務 | append-only obligation events |
| 收款／退款／adjustment／reversal | immutable client ledger |
| transaction allocation | append-only M:N allocations |
| current balance／settled at | obligation 與 ledger reducer |
| 客戶代墊／補助退還／資金回收 | 一般服務費 receivable 與 receipt、依已確認方案／對象及正式來源成立的 `subsidy_return` 應退與 immutable payout；資料齊全即由身分自動建退款的舊路由已取代，僅供歷史追溯，以及 Government Subsidy receipt-allocation fact 的 M:N settlement link |
| `client_payments` | current／compatibility projection |
| review status | root-derived projection，不可人工直接修改 |

每次正式核銷必須完整分配所選銀行流水，且每個所選義務在同一次 Apply 後精確為 `0`。少收、超收、錯案或 ownership 不明不得建立部分正式交易。

## 3. Subsystems

### Payment Terms／Obligation Planning

簽約與應收用詞依第 `21` 份正式規格 §1.1：使用「所有月嫂簽約完成」與「客戶簽約完成」；案件計算資料齊全即由系統同步客戶應付；缺值顯示待確認，不以簽約或另行建立付款義務作為計算／核銷門檻。

依 Orders Terms、服務日根事實及費率政策建立訂金、第一期、第二期及調整義務。樓層費只計入一次。條款變更只重算未核銷義務；已核銷差額建立 adjustment 或 refund obligation。

第一期款到期日依 Orders 已正式確定的 `actual_start_date`；尚未確定實際開始日時才採預計開始日。規格 02 SSTART-03／05 的月嫂接受或工會代班日期保存，在同一正式處理中委派 Client Finance 同步 `first_payment_due_date`、未結清期款到期日與付款條款事件，不增加「建立付款義務」操作或狀態。只改日期不新增本金、收款、退款或 allocation；既有已核銷交易與已簽文件保持不可變。服務中局部代班沒有改變全案實際開始日，不得以代班首日重設第一期到期日。第二期有金額時仍依下述既有加 15 日公式同步，正常查詢零寫入。

2026-10-13 第二期繳款日人工裁決：第二期有應付金額時，Client Finance stage plan 的預計繳款日
固定為第一期款預計入帳日（`first_payment_due_date`）加 15 個曆日；第二期金額為零時不產生日期。
計算不等待第一期實際入帳，也不使用實際核銷日期。訂單資訊、候選／推薦寄送前預覽及契約共用此
owner 計算結果；既有保存的第二期日期不取代本公式。預覽零寫入；未結清義務日期的正式異動仍經
既有 Preview／Apply，已核銷交易與已簽文件不由預覽改寫。

2026-10-13 第二期日期保存裁決：案件初始化正式 Apply 將上述 owner 計算結果保存至
`client_payment_terms.second_payment_due_date` 與初始付款條款事件；期款應收建立或重算時，
同一 outer Unit of Work 同步此欄位與新的 immutable payment-terms event，並使用同一 stage plan
寫入義務日期。第二期金額為零時保存 NULL；查詢與預覽保持零寫入，既有日期補正須走正式 writer。

完整進件與服務條件保存後，在原 outer Unit of Work 依目前付款條款、服務天數、每日時數、單價與樓層費，自動同步訂金、第一期與第二期客戶應付。CF-SCHEME-FULL成立時客戶應繳為0；本次僅記錄應有行為，不授權改寫既有期款、人工控制或實收。未簽約或未建立執行指派，不阻擋金額計算與核銷；不要求人員另行建立付款義務。

2026-10-29 訂金提醒與逾期待辦人工裁決：預先計算、保存各期金額及合法核銷維持上述規則；訂金繳費提醒與訂金／第一期／第二期逾期待辦，另須客戶及所有月嫂均已簽約完成。資格沿用同案 `order_contract_flow_events.event_type=contract_completed`，且事件的 `contract_identity` 必須等於 Orders 目前契約識別；沒有正式完成事件、只有單方簽署或契約識別不符，均不得列入。這是通知資格，不是新增帳務狀態或計算／核銷門檻。原到期日不因簽約重設；雙方簽約完成後若原期限已過，依各期既有逾期規則列入。

2026-10-30 入帳通知人工裁決：第一期正式核銷在既有 `projection_refresh` payload 同交易保存 `line_first_payment_notification=true`、期別、settlement identity、選定義務及正式分配金額；LINE 透過 Finance-owned 第一期款 Query 驗證結清、精確 allocation 與未沖正收款後，只衍生內部通知／帳務待辦，人員確認才可私訊客戶。沒有核銷標記的歷史入帳不回填，不新增財務狀態、writer 或外層 commit；其餘付款與核銷規則不變。


付款相關條件變動沿用既有 Terms Preview／Apply、Finance aggregate version 與正式 writer。日期優先使用本次正式替代／目前確認日期；尚未確認時只供計價使用約定服務量，不建立 Scheduling 服務事實。既有未結清期款沿原 identity 更新；已核銷交易、allocation 與簽署文件不得覆寫，差額沿既有 adjustment／refund 規則承接。非計價修改、歷史實際服務補正及 nonstage 完整性保護維持各 owner 契約。

所有 Query／Preview 零寫入；自動同步只發生在有授權的資料保存交易。初始化回條仍記錄政策 roots 的初始版本，後續帳務同步使用 Client Finance 自己的版本與事件，與父命令同交易提交及回滾。重播不重複計算或建立款項；缺少必要資料不填零、也不偽造服務或付款。

使用者介面一律稱為「客戶應付」，意思是客戶應付給工會的金額；內部既有 accounting
`receivable` 型別可保留。服務本金公式固定為 `有效正式服務時數 × 有效服務單價`，雙胞胎為
每小時 450。服務前的合法胎數更正必須在同一交易同步付款條款與所有 open 義務；已核銷金額
不得覆寫，差額形成 adjustment 或 refund。正式服務開始後不得再變更胎數，完工確認當下即凍結本金。

一般市民遇工會突發狀況時，system admin 可經專用 Preview／Apply 人工允許案件在訂金尚未付清時繼續後續流程。此入口不得自動執行，且不適用低收入戶、中低收入戶或非市民；Apply 必須保存 actor、明確原因、idempotency receipt 與 immutable payment-terms event。放行不修改訂金服務天數、金額、義務或 `deposit_settled`，而是以獨立 typed override 經 durable outbox 交由 Orders 正式 writer 將仍在 `洽談中` 的案件推進為 `訂單成立`；Scheduling 只讀此 override，不得自行改寫 Orders。Operational Stage 必須將訂金關卡標為完成並顯示「定金未付，已人工放行」，不得誤標為已核銷。後續付款仍走既有核銷流程，payment terms 的下一次正式變更會使既有放行失效並要求重新確認。

LINE 案件群組不接受上述未付款放行取代核銷；只有
`client_deposit_settlement_projection.settlement_state = settled` 才能綁定群組或發送邀請。

第 `27` 份正式規格的歷史 lifecycle branch 可用每位月嫂已確認 `actual_service_days` 的總和取代逐日
服務日期作為歷史服務量來源；Client Finance 仍自行擁有費率、補助、自費、樓層費、obligation direction
與核銷。歷史服務量可少於或大於原合約天數，既有已核銷金額差異只能追加 adjustment／refund，不得
覆寫 immutable ledger。

簽約只記錄文件與簽回進度，不再觸發訂金或其餘期款的建立。客戶簽約前已合法核銷的款項保持原 identity、金額、ledger 與 allocation；簽約時不重建或撤銷。先收款仍依 Finance Import 保存銀行事實與人工核對／確認核銷；資料未齊時保留待處理，不推定已核銷。資料齊全後即可使用既有核銷入口，不另建立付款義務。

### 取消帳務 impact 的公開 direction（2026-08-27 人工裁決）

取消 Preview／Apply 對外公開的每一筆 Client Finance impact 必須帶 server-owned、required
`direction`；UI 不得由 `action_kind`、金額正負、before／after 差值或排序推定。固定 enum 與顯示
語意如下：

| `direction` | 公開意義 | `direction_amount_ntd` invariant |
|---|---|---|
| `refund_due` | 應退款：客戶有待收回的款項 | 非負整數且 `> 0` |
| `additional_charge_due` | 應補收：客戶仍有待繳的款項 | 非負整數且 `> 0` |
| `no_finance_change` | 無帳務變動 | 必須為 `0` |

`action_kind` 仍可說明 adjustment／refund／collection 等操作類型，但不具 direction 權威。
若同一取消同時存在多個獨立 impact，結果必須逐筆帶 direction，不得先由 UI 合併成一個淨額
方向。`before_amount_ntd`／`after_amount_ntd` 是 obligation target；既有
`obligation_amount_ntd` 是該 action 新建／變更的 obligation delta（或新建 obligation 金額），
不是客戶實際應退款／補收的金額。另公開 required `direction_amount_ntd`，代表 direction 對
客戶的現金／待收付影響，為非負整數；只有它能和 direction 配對。Direction 是 derived public
view 的必要欄位，實際 obligation、ledger、allocation 與 settlement 仍由本 Domain 根事實重建；
不存在新的帳務根事實或 UI writer。

取消結果對現有 action kind 的 canonical mapping 固定如下；server 必須在建 candidate 時寫入，
caller 不得重算：

表中的 `current_settled_amount_ntd` 是 Client Finance 由 immutable ledger／allocation reducer
重建的目前已結算金額；不是 `before_amount_ntd`（後者是既有 obligation target）。

| `action_kind` | 條件 | `direction` | `direction_amount_ntd` | `obligation_amount_ntd` |
|---|---|---|---:|---:|
| `create_stage` | `after_amount_ntd > 0` | `additional_charge_due` | `after_amount_ntd` | `after_amount_ntd` |
| `replace_open` | after > before | `additional_charge_due` | `after - before` | `abs(after - before)` |
| `replace_open` | after < before（尚無正式收款歷史） | `no_finance_change` | `0` | `before - after` |
| `cancel_open` | open obligation、無正式收款歷史 | `no_finance_change` | `0` | `before_amount_ntd` |
| `create_adjustment` | `after_amount_ntd - current_settled_amount_ntd > 0` | `additional_charge_due` | `after - current_settled` | `after - current_settled` |
| `create_refund` | `after_amount_ntd - current_settled_amount_ntd < 0` | `refund_due` | `current_settled - after` | `current_settled - after` |
| `unchanged` | before = after 且沒有新 obligation | `no_finance_change` | `0` | `0` |

因此 `replace_open` 減額與 `cancel_open` 都不是退款：它們只減少／取消尚未收取的 open
obligation；真正已有正式收款而新義務下降時，固定使用 `create_refund` 與 `refund_due`。
同一 cancellation response 可含多筆 action，各筆均依本表產生自己的 direction 與
direction amount。

取消不加收取消費。服務中取消以已確認實際服務時數重算服務本金；訂金、第一期及其他已正式
核銷款項均依 allocation reducer 計入 `current_settled_amount_ntd`，不得只扣其中一期或重複收取。
已收總額大於實際應付時建立退款，小於時才形成補收。

缺少 direction、direction_amount 與 direction 不一致、或 current owner readback 不能唯一確認
方向時，Query／Preview／Apply 回 typed schema／domain error 或 `outcome_unknown`，不建立或
變更正式交易；不得 fallback 成 action kind 或以正負號猜測。舊 caller 若無法驗證該欄位，只能
顯示 schema-drift／unavailable。相同 idempotency identity 的結果重查後，receipt／readback 必須
保留同一 direction。

現行補助與客戶負擔依 §0.3／`22` §17 的案件金額及三方案記錄：

- 案件總額 T＝服務費＋樓層費／其他費用＝月嫂應收合計；客戶扣補助後負擔為 T－S，應繳工會 B 另依原各期安排保存。
- CF-SCHEME-FULL免自備案件直接成立方案一，零期款不阻擋；其餘各期款未齊不自動判方案，齊款且證據唯一才分類。此門檻不阻止保存及核銷此前已確認的真實交易。
- P永 與 P台 可分次清償同筆月嫂應收，不能以一次 payout 限制拒絕真實付款，也不另加一份補助薪資。R永 與 R台 分開，不能將正常退款視為補助返還。
- 樓層費／其他非補助項目只計一次，補助範圍由原 owner 保存，不因方案分類改寫日期、服務事實或既有核銷。

**已取代，僅供歷史追溯**：舊「社福不超過 120 小時且客戶應付為 0 才全補助」及一般市民固定先墊後退的兩路徑，不再決定現行金流方案；原已形成義務、費率、到期日及實付仍按歷史來源保存。

Modules：

- `PaymentStageSplitter`
- `DailyClientChargeCalculator`
- `PaymentDueDatePolicy`
- `ObligationDiffCalculator`
- `FinancePreviewFingerprint`

### Reconciliation Preview／Apply

客戶各期逾期查詢供 LINE 規格 20 §6.10 工會待辦使用：先依上述雙方簽約完成資格篩選，再按每筆訂金／第一期／第二期獨立讀取正式 due date、current event、projection version 及未核銷餘額，台灣到期日隔天起、同筆餘額為正才逾期，不以訂金到期日觸發後續期款或合計全案應付。不需／零金額第二期不列；提醒不建立新義務、收款或異常。清單、總數、送出提醒前與 provider 前均重讀同一資格；未完成雙方簽約的舊待寄提醒須取消。核銷與條款日期變更沿既有 writer 更新，待辦重新查詢即反映，已排入寄送的舊快照由 LINE 在 provider 前取消。

鎖定銀行 facts、account version 與 obligations；驗證方向、案件、external reference、ownership 與完整 allocation。Preview 零寫入；Apply 建立正式 ledger、allocation、projection、audit 與 outbox。

正式訂金核銷在原 outer Unit of Work 保存 `orders_deposit_reconciled` outbox intent，
新事件的 payload 同時帶 `line_deposit_notification=true`，供 LINE 建立核銷成功通知。
LINE 只讀此已提交事件及 current settled projection，不消費或變更 Orders outbox 的處理狀態。
交易 rollback 不留下通知；沒有上述標記的歷史核銷不補送，不新增資料表或 outbox enum。
同一 settlement identity 重試不重複建立寄送工作；Orders consumer 仍處理其原有 lifecycle intent。
訂金通知／客戶繳費查詢共用 typed `DepositPayment` 唯讀投影：既有 deposit obligation 的金額、
期限、版本及專屬虛擬帳號，入帳狀態以正式 settled projection 為準，日期讀對應 receipt ledger 的
`occurred_on`。客戶留言、付款截圖、提醒與客服需求均不得建立或修改入帳事實。

第二期款群組通知依規格 20 §6.9。正式第二期核銷沿原 `projection_refresh` outbox 保存 `line_second_payment_notification=true`、`payment_stage=second`、settlement identity、所選 obligation identities 及本次分配金額。與 ledger／allocation／receipt 同交易，零新資料表或 enum；LINE 只讀已提交事件及 current Finance facts，不消費該 outbox status。未需第二期、金額為零或第二期資料不足不通知；已付只省略催繳，合法新核銷仍可通知。正常精確核銷不因階段不是訂金而產生異常事件；真正超收處理依既有 discrepancy 契約保留。

Modules：

- `BankFactEligibilityValidator`
- `ExactAllocationSolver`
- `StageBalanceCalculator`
- `ReconciliationInvariantValidator`
- `ExternalReferenceDeduplicator`

### Historical Payment Evidence／Settlement（2026-08-28 人工裁決）

對使用系統前且已正式採納的 historical case，付款與本 Domain 結清仍須依方向分開：客戶付款給
工會只清償 `receivable_from_client`；工會一般退款給客戶只清償 `payable_to_client/refund|adjustment`；
工會退還客戶補助款只清償 `payable_to_client/subsidy_return`。客戶補助退款的收款人是客戶，屬本
Domain；不得投影成 Government Subsidy 或 Staff Payables 已完成。

首要證據是 Finance Import 匯入的 canonical bank facts，能正常核銷時固定走既有 reconciliation。
舊銀行／帳務證據缺失、歸屬不明或無法可靠還原時，才允許歷史人工 `paid | settled` Q/P/A；它必須
綁定 historical adoption、payer/payee/direction 與 exact obligation identities，並保存 actor、reason、
evidence、版本、fingerprint、idempotency、receipt及outbox。未知付款日期保存 null／unknown，不得用
匯入日或操作日補值。這是替代 evidence source，不是 generic balance editor，也不得偽造 Finance Import
row、bank allocation或另一帳務方向。

`paid` 是特定付款方向與義務的 payment fact；`settled` 是本 Domain 選定 obligations 的合法歷史處分。
兩者都不能推定 Staff Payables 或 Orders Step 11完成。後續退款、退匯、reversal、服務／金額更正或新
obligation依strictly-newer owner event更新current projection，未被舊event exact綁定的義務保持open。
完整跨Domain契約見
`../02_決策與退役執行記錄/PROV-20260828-historical-payment-and-owner-settlement-spec.md`。

### Immutable Ledger／Reversal

收款工作區的「已收款」依 canonical ledger 中 `entry_type=receipt` 的實際收款紀錄篩選。既有案件摘要增加唯讀 `receipt_entry_count`，只計同案件的 receipt；退款、adjustment、reversal、補助退款及代墊紀錄不得單獨使案件符合此篩選。部分收款且仍有待收餘額的案件仍納入，不以餘額為零或一般帳務紀錄筆數推定已收款；此篩選不代表已全額收清，也不改寫歷史或原帳務規則。

原交易永不 UPDATE。reversal 指向同 case、同 obligation kind、同 ledger 的原交易；不得超過仍可沖銷餘額。

已確認禁止 reversal-of-reversal。若 reversal 疑似錯誤，系統先產生異常警報並停止自動修復，顯示原交易、reversal、有效淨額、受影響義務及合法 recovery actions。只有人員確認實際情況後，才可透過 Client Finance Preview／Apply 新增反方向 adjustment；不得由 projector、scanner 或 ledger reducer 自動補 adjustment。

### Over-receipt／Customer Refund

義務合法下降造成有效實收大於新義務時，差額形成 `over_receipt` 與退款義務。退款後淨應收與淨實收同減；銀行撤銷原收款而義務未降低則是 reversal，重新形成應收。退款不取消已完成訂單，也不解除服務資料鎖。

取消自動產生的一般退款與月嫂薪資、補助退款共用每月應付帳款清冊；退款依本身 due date 納入所選月份月底以前仍未退完的款項，包含以前月份餘額。原期款取消歸零時若不再產生新期款到期日，其已收款退款保留來源義務既有到期日，不清空為未知日期；來源本來缺日期時仍列待確認。人工核對提供足額或「退款不足，先核銷實退」，沿既有 `allow_partial_refund_recovery` 保存實付並保留剩餘款；補退不重建退款，退匯／沖正重開對應餘額。銀行核對可依原流水選取客戶退款，不限逾期；一般逾期查詢仍保留原預設。取消與退款成功不發送 LINE 通知。

### Client Subsidy Return

客戶補助返還是已確認由工會退給客戶的正式應付 R台，與政府付工會 G、轉交月嫂 P台 分開；不能只因有補助資格、時數或 S 就建立客戶退款。三方案與對象依 §0.3／`22` §17：先墊後退依客戶應退及真實R台核銷；分別入款的月嫂補助走Staff Payables；政府直付客戶不新建該補助的工會待退款、不追蹤客戶實收證明。新流程交接依[16 §2.5.5](16_Staff_Payables與Client_Refund正式規格.md#manual-subsidy-plan-payables-handoff-20261105)：正式服務結束後讀取最後正式保存的人工方案，原Client Finance負責客戶退款的合法成立／更正及核銷；選方案不直接建立退款，歷史分類未知本身不否定人工安排或撤銷既成款項。

CF-SCHEME-FULL成立時不等待客戶付款；其餘客戶款未齊時不對歷史訂單啟動自動辨識；此為歷史分類門檻，不是新人工方案及應付交接的付款前置。人工方案交接依16 §2.5.5，未設定或與既成款項衝突只保留受影響補助待確認，不預設方案三、不整案擋住其他合法到期款。對已有正式義務、已確認對象及來源的真實交易，仍可沿原 owner 記錄與核銷，不把分類門檻變成所有退款／入帳的新前置。未唯一或必要資料不足保留待確認，Query 零寫入；不得以 `client_payments.subsidy_refund_*` 作根事實。

既有客戶應退、`subsidy_return`／`subsidy_advance` ledger、allocation、追償及沖正證據不可覆寫或刪除。已形成的服務結束月加兩月 15 日等 due date 保留，條款後續合法變更仍沿原 owner，不因本次分類重算／改期；未形成日期或新模型接線不明時保留待確認。歷史 actual-service owner、有效實際服務量及已核銷政府快照亦不改寫。

**已取代，僅供歷史追溯**：原系統曾依一般市民／社福身分、有效服務量與凍結客戶單價自動同步應退，資料足夠即建立，且不等待客戶齊款或政府款。這是原實作與舊流程證據，不是新三方案的退款建立規則；本次不修改程式、回填既有帳或強制重建。

對已正式成立的客戶退款，實際出款及部分退款仍沿原 owner、帳戶 snapshot、concurrency 與既有 due date 規則；政府後入不得造成第二筆同款 payout。原代墊及整期回收僅針對既有真實出款／沖正 lineage，依規格 14 查閱，不補造現金或逐案政府分配。已付 ledger／allocation 不改寫，超退仍沿既有差額追償；新模式的義務接線待後續實作收斂。

`GET /api/v1/finance-reports/client-subsidy-returns` 保留 bounded cursor、exact case、搜尋及退款月份條件。日期及金額來自 current owner projection；缺值不是零，缺收款帳戶不使案件消失。

一般退款與客戶補助退還不得共用 ledger transaction type 或 reversal type：

| 業務線 | payout entry type | return／reversal entry type | obligation projection |
|---|---|---|---|
| 一般客戶退款 | `refund` | `refund_reversal` | `refund` 的 `pending → partially_refunded → refunded` |
| 客戶補助退還 | `subsidy_return` | `subsidy_return_reversal` | `subsidy_return` 的獨立 payable progress；不與一般退款互抵 |
| 客戶收款沖正 | 不適用 | `reversal` | 只重開原 receivable，不得重開任何 payable |

同一 Client Finance outer UoW 可以共用技術性 receipt／outbox 實作，但不得以共用
`refund` entry type、共同餘額或共同狀態 reducer 混淆兩條業務線。

### Adjustment Accounting

adjustment 是獨立義務，不修改歷史服務費。一筆銀行交易可明確 allocation 到多筆 adjustment，但每筆所選義務都必須完整核銷。

adjustment 的原因、方向或歸屬若不能從已確認根事實唯一決定，必須先進異常中心，由人員查看完整事件鏈並啟動 typed Adjustment Preview／Apply；不得為了讓差額歸零而自動建立。

Adjustment 必須明確宣告 scope：

- `client_only` 只建立客戶 adjustment obligation／ledger event，不要求 staff
  allocation、不檢查或遞增 Payroll version，也不發出 Payroll outbox。
- `client_and_staff` 必須讓 client delta 與所有 staff allocation 的整數 NTD
  加總完全相等，並在同一交易檢查及遞增 Client Finance／Payroll 兩端版本。
- 兩種 scope 都必須經 Preview／Apply、Client Finance version compare-and-swap、
  idempotency receipt、不可變事件及 Client Finance outbox。reversal 必須沿用原
  adjustment scope，不得用 `client_only` 局部沖回雙端 adjustment。

### Projection／Query

從 obligation 與 ledger events 重建各 stage receivable、received、due date、settled at。總額只供顯示，不得掩蓋單期差異。對 Orders 只輸出 typed `ClientSettlementFacts`；取消 impact 的每一筆公開結果必須包含上述 `direction`，不得讓 caller 由 action kind 或 amount 推定。

2026-10-14 人工裁決：已保留等待訂金檔期、但尚未建立訂金應收的案件，Client Finance
可提供 typed `UnreceivedDepositConfirmation`，確認沒有客戶帳務義務、義務事件或 ledger 歷史後，
允許 Scheduling 沿原 Release Preview／Apply 釋放檔期並換人。不存在的 settlement projection
本身不是未收款證據，不得補造零金額義務、結算、收款或退款；既有結算 projection 仍沿用原淨額門禁。
任何正式財務歷史存在而結算資料缺漏時，回 `deposit_receipt_unconfirmed` 並交財務核對，
不得把取消過的義務、退款或 reversal 歷史忽略成「未收款」。

此確認 Query 借用 Scheduling 外層交易，先鎖 Finance account，再完整讀取同案的義務、
義務事件與 ledger；不建立 account、不寫帳務、不自行 commit。account 不存在保留明示的
`None` 來源版本，與現存 version 0 區別；空根事實須由完整查詢確認，不能由缺列推定。
來源版本與確認事實納入既有 Release fingerprint；Apply 在同一交易重新查核，發現新收款、
義務或版本異動時拒絕釋放。成功的確認來源保存於 Scheduling 原檔期釋放事件，原 key 的
replay 回原操作，不重複釋放或新建財務事實。

## 4. Ports

輸入：

- `OrdersTermsFactsPort`
- `OfficialServiceDaysPort`
- `ClientEligibilityPolicyPort`
- `FinanceImportCanonicalIncomingFactsPort`
- `FinanceImportClientReceiptDispatchPort`
- `FinancialAdjustmentFactsPort`
- `GovernmentSubsidyReceiptAllocationFactsPort`

輸出：

- `ClientFinanceImpactPreviewPort`
- `ClientSettlementFactsPort`
- `ClientFinanceRootFactsOutboxPort`
- `ClientFinanceQueryPort`

基礎設施：

- `ClientObligationRepository`
- `ClientLedgerRepository`
- `TransactionAllocationRepository`
- `ClientFinanceProjectionRepository`
- `IdempotencyReceiptRepository`
- `UnitOfWork`

不得提供同步 Alert writer；只在交易內寫 outbox facts。

## 5. 驗收

- 三階段義務及多流水完整核銷。
- 一筆流水跨多義務時，每筆義務皆完整歸零。
- 少收／超收初次對帳零正式交易並形成異常 fact。
- obligation 後降建立 over-receipt／refund obligation。
- 合法退款與 reversal 的淨額結果不同且正確。
- 補助退還建立、到期、精確退款、退匯重開。
- 第一個季度月結案案件在兩曆月內未獲政府入帳時，建立可追溯的墊付待辦；墊付後的
  政府 receipt 只核銷墊付款，絕不重複退還客戶。
- 補助退款日為結案月份加兩曆月的 15 日；未清償的客戶補助退還必須出現在
  Accounts Payable Query／Export，並以 `client_subsidy_return` 類型與月嫂應付款區分。
- 政府撥款、核准或墊付額不一致時，零自動 settlement 並建立 anomaly。
- 取消帳務每筆 impact 都公開 `refund_due`／`additional_charge_due`／`no_finance_change` direction；
  UI 顯示 server enum，不從 action kind 或金額正負推定，且 direction／direction_amount 不一致時零寫入。
- Domain blocker 不因 Alert resolve 被繞過。
- 任一 ledger／allocation／projection／outbox 失敗整筆 rollback。

## 6. Typed Commands／Results／Errors

Commands：

- `QueryClientFinance`
- `PreviewClientReceiptReconciliation`
- `ApplyClientReceiptReconciliation`
- `PreviewClientRefund`
- `ApplyClientRefund`
- `PreviewClientAdjustment`
- `ApplyClientAdjustment`
- `PreviewClientReversal`
- `ApplyClientReversal`
- `PreviewClientSubsidyReturn`
- `ApplyClientSubsidyReturn`
- `QueryClientSubsidyAdvanceQueue`
- `PreviewClientSubsidyAdvance`
- `ApplyClientSubsidyAdvance`
- `RebuildClientObligationsForCase`
- `QueryHistoricalClientPaymentRepair`
- `PreviewHistoricalClientPaymentRepair`
- `ApplyHistoricalClientPaymentRepair`

Stable errors：

- `client_finance_case_not_found`
- `invalid_client_finance_intent`
- `bank_fact_not_eligible`
- `client_obligation_not_found`
- `allocation_not_exact`
- `client_receipt_underpaid`
- `client_receipt_overpaid`
- `client_finance_identity_ambiguous`
- `reversal_target_invalid`
- `reversal_amount_exceeded`
- `adjustment_evidence_required`
- `client_finance_candidate_stale`
- `idempotency_conflict`
- `transaction_failed`
- `subsidy_advance_not_due`
- `subsidy_advance_already_recovered`
- `subsidy_advance_settlement_ambiguous`
- `client_finance_direction_missing`
- `client_finance_direction_amount_mismatch`
- `historical_client_payment_not_eligible`
- `historical_client_payment_direction_ambiguous`
- `historical_client_payment_obligation_binding_invalid`

## 7. Live writer 退出

- `services/client_payment_writer.py`、`services/client_payment_transactions.py`、
  `services/client_receipt_reconciliation.py`、`services/client_subsidy_return_obligations.py`
  與 `services/client_subsidy_return_transactions.py` 的合法規則可吸收至本 Domain。
- `services/client_payment_snapshots.py` 與 `services/db_service.py` 只能建立／更新
  compatibility projection，不得成為 obligation 或 ledger SSOT。
- Finance Import、API、Streamlit 與 scripts 不得直接 UPDATE `client_payments`、
  `client_payment_transactions` 或 reconciliation projection。
- final writer scan 必須證明 obligation event、client ledger、allocation、refund、
  adjustment、reversal 與 settled projection 都只有 Client Finance adapters 可寫。

## 8. 客戶收款帳號（2026-09-15 人工裁決）

- 每個案件的服務款項使用 Client Finance 擁有的專屬虛擬帳號，不得讀取 `staff_bank_accounts`，
  也不得以全域工會／代收付帳戶填入客戶契約。
- 虛擬帳號與 Finance Import 共用同一 owner 規則，固定前綴為 `99781699`：
  - 既有 canonical 9 碼案件編號：沿用案件編號前三碼民國年度及後六碼轉成三碼序號的公式；後六碼數值須可由三碼表示。
  - 非市民 `A＋民國年度＋3 碼流水號`：使用案件民國年度及「案件流水號＋500」三碼。例如 `A115001` 對應 `99781699115501`，`A115002` 對應 `99781699115502`，跨年 `A116001` 對應 `99781699116501`。
  - 收款、退款／月嫂付款案件定位、契約與名冊讀取同一 typed 帳號／對照結果，不得把 A 開頭案件去字母後直接套舊公式。既有不可表示值維持 fail closed；非市民編號容量及超量政策依人工裁決暫不在本次範圍。
- Contract Signing 只消費 `client_virtual_account` typed projection；銀行核銷以相同規則解析帳號，
  並且只有在案件唯一且同案同金額的未清償應收義務唯一時才可自動配對，否則保留 pending。 同案多筆入款另依 §0.2 CF-DIFF-10／`22` §16.5.2 彙整明細及合計供人員直接核銷；本句描述單筆自動配對條件，不表示每筆入款都必須個別等於整筆應收。
- 舊流程虛擬帳號由管理員以含「虛擬帳號」與「市府訂單號碼」欄位的 XLSX 經 Preview／Apply 匯入；
  空白案件編號、格式不符與查無既有訂單的列直接略過，不建立 anomaly 或預覽錯誤。匯入對照是較公式
  推導更高順位的來源事實：收到的虛擬帳號只要存在匯入對照，核銷候選只取匯入對照，不得再合併公式
  候選；匯入對照唯一時直接解析該案件，對應多個案件時保留 pending。只有完全沒有匯入對照時，才可
  使用現行公式候選。案件對外顯示帳號亦採相同順位：唯一匯入帳號優先；同案存在多個不同匯入帳號時
  必須明確回傳不唯一，不得任選其一或退回公式。
- 2026-11-02 使用者明確退役舊全域工會／代收付帳戶：移除維護畫面、typed client、Query／Preview／Apply API、Domain/application/repository 與三張專屬設定／event／receipt 表，不再提供讀寫或契約來源。此裁決取代舊的保留維護要求。單案虛擬帳號、退款與月嫂個人帳戶、登入帳號管理不受影響。新庫依 retirement register 排除；既有本機庫依規格 10 的獨立備份、計畫、engine 與精確移除程序執行。已發布的歷史 migration／release 僅作重現證據，不改寫。

### 8.1 客戶名冊單案虛擬帳號修改（2026-10-15 人工裁決）

狀態：SPEC_READY；convergence：READY，無 blocking gap。Authority：使用者要求在客戶名冊新增修改功能，
並明確選擇「以新帳號取代本案原有匯入帳號，後續契約與收款辨識使用新帳號」。
同日最新人工裁決：「不用原因跟預覽功能」；單案修改直接儲存，不填原因、不執行人工或隱藏預覽。

- VA-01：有名冊寫入權限的管理人員可在案件詳細資料新增或修改「匯入虛擬帳號」。
  新值沿用既有 `99781699` 加六位數字的格式；內建帳號仍依案件編號產生，不可人工改寫。
- VA-02：Client Finance 提供 `GET /api/v1/admin/client-finance/cases/{case_no}/virtual-account`
  與同路徑的 `POST /apply`。Query 零寫入，回傳本案全部舊對照與 `mapping_ids`；Apply 不接受原因或 preview fingerprint。
  Apply 原子取代本案全部匯入對照，其他案件不變；禁止將已匯入對應其他案件的帳號指派給本案。
  無對照時可新增，多筆舊對照時可整理為單一新帳號；不提供清空或刪除帳號操作。
- VA-03：沿用既有匯入對照與公式順位。儲存後契約的下一次資料投影及收款辨識讀取新對照；
  不改寫已簽契約、歷史流水、核銷分配或對外發送文件。移除舊匯入對照不建立帳號停用清單，
  完全沒有匯入對照的帳號仍依第 8 節公式解析。
  已產生但未簽的客戶契約可依規格 21 的既有未簽 PDF 命令重新產生新版本，帶入新帳號；由 Contract Signing 擁有文件版本，不由帳號 writer 改檔。
- VA-04：現有對照無獨立 owner version；Query 回傳不可變 mapping row IDs 作為本案集合的版本依據。
  Apply 以 `expected_mapping_ids` 對照 fresh-lock 後的 current IDs，防止讀取後被另一個匯入／修改更換對照；
  不一致回 typed HTTP 409，不自動重試。空集合以空陣列表示，取代同值但 row IDs 改變仍視為 stale。
  不使用 Preview fingerprint／digest／snapshot token；使用既有匯入 writer 的同一互斥鎖，跨案占用亦在鎖內重查。
- VA-05：單一 outer UoW 同時保存對照與 `admin_command_receipts` 的 actor、reason、before／after。
  使用者不填原因；receipt 的 reason 固定記錄「後台客戶名冊虛擬帳號更新」。既有必填 `preview_fingerprint`
  儲存欄位填入同一 command digest，僅符合既有 schema，不代表預覽契約，也不作 concurrency 檢查。
  人工來源為 canonical 單列命令的 content digest，`source_row=2` 表示其標準表頭後第一列；
  receipt 的獨立 command family 區分人工修改與 XLSX 匯入，不假稱上傳過 workbook。
  同 key／command／actor 回原 receipt，異內容或異 actor 固定拒絕。
- VA-06：UI 只保留帳號輸入、取消與直接儲存；不提供修改原因、預覽或額外確認步驟。
  草稿、送出中、結果未明、已儲存但回讀失敗均沿用名冊關閉保護；stale 需重新讀取後再儲存。
  結果未明以同一 key 核對，成功後回讀帳號、名冊清單及詳情，才顯示完成。

驗收：VA-A1 無／單／多舊對照可改成單一新值且不影響他案；VA-A2 格式錯誤、查無案件、跨案占用、
stale 與異內容／異 actor replay 均拒絕且零 mutation；VA-A3 同命令 replay 不重做，receipt 保存失敗整筆 rollback；
VA-A4 契約及核銷沿用既有 resolver 消費新對照；VA-A5 UI 不填原因、不預覽即可直接儲存，回讀及結果未明關閉鎖可驗證。
來源：最新人工裁決＋第 8 節（格式／順位）＋Global 2.3（concurrency）＋既有 mapping／receipt schema（執行機制）。
本次僅授權本機程式、測試與規格變更；不含正式資料修改、schema migration、銀行／LINE 外部效果或部署。

2026-11-02 實作接線補充：金額控制及非現金處理歸 Client Finance。來源計畫的已處理額包含正式非現金結清證據，與實際銀行收款分開；人工更正造成已分配本金大於新計算時保留原 allocation，獨立退款承接，不回寫銀行或分配。Query／月統計仍只以正式銀行事實表達現金。
