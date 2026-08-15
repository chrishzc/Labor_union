# 匯入警示類型審核佇列

- status: `approved-by-WP88`
- updated: 2026-08-14
- owner: 各 owning import Domain；目前 HCM 由 Case Import 擁有
- authority: 2026-08-14 人工採用 Work Package 88；正式業務語意仍由 owning Domain 規格與 WP77、WP80、WP85、WP86、WP88 擁有，本表保存類型審核矩陣。

## 使用方式

每個匯入警示類型在實作 UI、操作按鈕或 LINE 通知時，必須符合本表已採用的顯示、後續處理與解除條件。
不得因目前 live code 共用 `IMPORT-004` 就把不同業務原因視為同一警示類型。

## HCM 初始登錄

| logical code | 觸發條件 | 正式案件效果 | 審核主題（已由下方矩陣裁決） |
|---|---|---|---|
| `HCM-CASE-001` | 案件編號缺失或不可用 | 不建案 | 如何辨識來源、誰可補案號、補到可用案號後如何建立正式案件 |
| `HCM-FIELD-001` | 有案號但必要欄位缺漏 | 建立／保留正式案件 | 去敏欄位名稱、可由哪個 typed field-completion command 補齊、何時解除 |
| `HCM-FIELD-002` | 有案號但欄位格式無效 | 建立／保留正式案件 | 顯示格式要求、補件入口、通過 validation 的解除 predicate |
| `HCM-LINK-001` | IP＋姓名精確命中既有 Client，不能自動綁定 | 建立正式案件但不自動綁定 Client | 顯示為疑似既有客戶或待確認關聯、人工確認後的 typed linking command、解除 predicate |
| `HCM-LINK-002` | 多個候選或其他身份關聯歧義 | 建立正式案件但保留未確認關聯 | 候選資訊最小揭露、可操作角色、不可自動選擇的邊界與解除 predicate |
| `HCM-CASE-002` | 既有案件的已填欄位與後續來源不同 | 保留既有欄位；不得以匯入任意覆寫 | 差異顯示、可否以受控 command 確認變更，以及何時關閉或替代舊警示 |
| `BECLASS-001` | HCM 已建立但尚無唯一 Client BeClass 對方 | HCM 正式案件不受阻擋 | 與 HCM 欄位警示分頁或合併顯示、唯一配對後的自動解除證據 |

## 已知 live-drift

現行 HCM 實作以 `IMPORT-004` 承接欄位驗證失敗，且多數情境仍零正式 root mutation；這與 2026-08-14
HCM 裁決不一致。此佇列不是 schema 或 production mutation 授權；實作前仍需另完成 owner、typed command、
schema、警示投影及 DB gate 的正式設計。

## Client BeClass 過渡綁定初始登錄

| logical code | 觸發條件 | 正式資料效果 | 審核主題（已由下方矩陣裁決） |
|---|---|---|---|
| `CLIENT-BECLASS-BIND-001` | 姓名＋手機號碼未命中 Client | 保留 BeClass 來源，不建立 Client／案件綁定 | 顯示可定位不足、補件或人工確認的合法入口、解除 predicate |
| `CLIENT-BECLASS-BIND-002` | 姓名＋手機號碼命中多位 Client | 保留 BeClass 來源，不自動選擇 Client | 候選資訊最小揭露、可操作角色與人工確認後的 typed binding |
| `CLIENT-BECLASS-BIND-003` | 唯一 Client 但案件候選為零或多筆 | 保留 BeClass 來源，不自動選擇案件 | 顯示案件關聯待確認、可採取動作與解除 predicate |
| `CLIENT-BECLASS-SOURCE-001` | 來源姓名或手機號碼缺失／格式不可用 | 保留來源追溯，不建立過渡綁定 | 缺漏欄位的去敏顯示、補件入口與解除 predicate |

`query_no`只作來源追溯，禁止用於上述任一綁定條件。LIFF 啟用後，這組過渡警示由登入身分直接綁定流程取代。

## Staff BeClass 歷史匯入初始登錄

| logical code | 觸發條件 | 正式資料效果 | 審核主題（已由下方矩陣裁決） |
|---|---|---|---|
| `STAFF-BECLASS-IDENTITY-001` | 身分證缺失或不可用 | 不建立 Staff | 去敏來源識別、補件入口與取得可用身分證後的建檔流程 |
| `STAFF-BECLASS-NAME-001` | 身分證可用但姓名缺失／無效 | 不建立 Staff，維持現行 DB 不可空約束 | 缺失欄位顯示、補件入口與解除 predicate |
| `STAFF-BECLASS-IDENTITY-002` | 相同身分證命中多筆 Staff | 不更新任何候選 Staff | 重複 root 的處理 owner、顯示與人工裁決入口 |
| `STAFF-BECLASS-NAME-002` | 唯一 Staff 的較新歷史列姓名不同 | 更新姓名並保存追溯警示 | 舊／新姓名的最小揭露、追溯保存期間及何時可關閉 |
| `STAFF-BECLASS-FIELD-001` | 有可用身分證與姓名，但其他欄位缺漏 | 建立／保留 Staff；缺漏欄位為 `NULL` 並建立警示 | 缺漏欄位顯示、補件入口與解除 predicate |
| `STAFF-BECLASS-FIELD-002` | 有可用身分證與姓名，但其他欄位格式無效 | 建立／保留 Staff；無法寫入欄位為 `NULL` 並建立警示 | 欄位格式、補件入口與解除 predicate |

較新歷史列的銀行帳戶及所有勾選關聯是完整快照，必須以原子替換建立最新集合；來源列與警示事件仍保留，
不得以刪除歷史追溯取代此行為。Staff 退役不由此匯入推定或變更，另見 WP87。

## Finance Import 初始登錄

| logical code | 觸發條件 | 正式資料效果 | 審核主題（已由下方矩陣裁決） |
|---|---|---|---|
| `FINANCE-SOURCE-001` | 金額、日期、帳號或必要格式無法正規化 | 不建立 canonical bank row；其餘可解析列不受阻擋 | 去敏來源列識別、來源修正或外部確認入口、何時關閉 |
| `FINANCE-ROW-001` | 可正規化銀行列但分類／歸屬不足以入帳 | 建立 canonical bank row，ledger 零新增 | 固定可用 recovery action、證據要求與 root-fact predicate |

跨檔 fingerprint 完全相同的銀行交易不是 warning：不新增 occurrence、review 或 reopen，只在本次 receipt／計數回報已存在。

## Historical Orders 過渡匯入初始登錄

案件編號缺失或不存在固定為靜默零寫入，不建立來源、receipt、warning、review 或 outbox；因此不登錄警示類型。

| logical code | 觸發條件 | 正式資料效果 |
|---|---|---|
| `ORDER-HIST-FIELD-001` | 已精確命中案件，但歷史狀態空白／未知或日期不可解析 | 可安全解析的歷史欄位照常寫入；不可解析欄位不寫入並建立警示 |
| `ORDER-HIST-STAFF-001` | 已精確命中案件，但歷史照服員未命中 Staff | 寫入安全的案件歷史值，不建立不確定的人員關聯 |
| `ORDER-HIST-STAFF-002` | 已精確命中案件，但歷史照服員命中多筆 Staff | 寫入安全的案件歷史值，不自動選擇人員 |
| `ORDER-HIST-ASSIGNMENT-001` | 人員可識別，但期間或既有關聯證據不足以建立歷史 assignment | 保留來源證據，不建立不確定 assignment |

歷史檔案沒有可信的來源更新時間。只要精確命中案件且欄位符合寫入規則，就直接寫入歷史值，不因目前 DB 值不同而建立
`current_conflict`；上述警示只涵蓋不能安全寫入的個別欄位或關聯。

## 共通顯示與操作契約（已採用）

所有警示卡片只顯示：人可讀標籤、owning lane、去敏案件／來源識別、問題欄位與 issue code、來源列時間、目前處理狀態、
最後事件時間及可用操作。禁止顯示完整身分證、手機、銀行帳號、原始工作簿路徑、任意修正 payload 或 LINE 對話全文。

警示中心只記錄追蹤事件，不直接修改 Domain root；但可將 `warning_id`、field path、expected warning version 與去敏來源
reference 轉介至該類型允許的 owning Domain typed command。目標 command 成功寫入並通過 predicate 後，系統才解除警示。
共通人工操作固定為：

1. `open → awaiting_external_confirmation`：記錄已開始透過合法管道聯絡來源主人。
2. `awaiting_external_confirmation → response_recorded`：只記錄已取得回覆及最小必要摘要，不把回覆內容當成正式資料。
3. `response_recorded → reimport_requested`：需要來源重新提交、補欄位或由 owning Domain 的 typed command 寫入。
4. 任一 active 狀態可進入 `closed`：代表這次外部追蹤結束，不代表資料已修正。
5. `auto_resolved` 只能由系統重新讀取正式 root，確認該類型的 predicate 已不成立後寫入；人工不得直接標記。

第一階段只記錄人工透過 LINE、電話或法定聯絡管道處理，不由系統自動發 LINE、不猜收件人、不保存聊天全文。
未來若增加 LINE 發送，必須另有唯一收件人綁定、核准模板、outbox、送達／失敗事件與 opt-out 契約。

## 類型別顯示、後續與解除條件（已採用）

### HCM

| logical code | 警示中心顯示 | 允許的後續處理 | `auto_resolved` predicate |
|---|---|---|---|
| `HCM-CASE-001` | 來源批次／列、案號「缺失或不可用」及其他 issue codes；不顯示不存在的案件連結 | 聯絡來源主人並要求提供可用案號；新來源必須顯式關聯本警示，不得直接改警示內容建案 | 關聯的新來源已以可用案號建立正式 HCM 案件 |
| `HCM-FIELD-001` | 案件連結、缺漏欄位名稱、來源列時間 | 聯絡來源主人；由 HCM typed field-completion command 只補指定欄位，不要求整案重送 | 正式案件該欄位已存在且通過 validation |
| `HCM-FIELD-002` | 案件連結、無效欄位名稱與格式要求，不顯示原始敏感值 | 同上；回覆只作證據，正式值仍由 HCM typed command 寫入 | 正式案件該欄位已通過 validation |
| `HCM-LINK-001` | 案件連結與「疑似既有 Client、待確認」；候選僅顯示最小去敏資料 | 外部確認後由 owning HCM／Client linking command 綁定；警示中心不可直接選取或寫入 Client | 案件已存在唯一、有效且可追溯的 Client 關聯 |
| `HCM-LINK-002` | 案件連結、候選數與最小去敏辨識資訊 | 先外部確認，再走 typed linking；禁止依排列順序或人工猜測自動挑選 | 同上 |
| `HCM-CASE-002` | 案件、衝突欄位及「保留目前 DB 值」；敏感值只顯示是否相同，不並列全文 | 來源確認後使用 HCM typed field-change command，或結束追蹤並保留現值 | 正式案件已符合經確認的欄位值；若決定保留現值，只能 `closed` |
| `BECLASS-001` | 案件連結與「等待客戶完成／綁定 BeClass」 | 無資料修正按鈕；LIFF 上線後由客戶本人流程完成 | 案件已有唯一有效的 Client BeClass 關聯 |

`HCM-CASE-002` 只適用一般新建／補件 lane。明確選擇「HCM 歷史過渡」模式時，只要符合最低寫入資格，來源欄位直接寫入，
不推定目前 DB 值較有效，也不建立此 conflict warning；個別缺漏、格式錯誤仍依 `HCM-FIELD-*` 追蹤。

### Client BeClass 過渡綁定

| logical code | 警示中心顯示 | 允許的後續處理 | `auto_resolved` predicate |
|---|---|---|---|
| `CLIENT-BECLASS-BIND-001` | 去敏姓名／手機、來源列及「未命中 Client」 | 要求來源主人更正姓名或手機；不得人工指定不符合精確條件的 Client | 來源姓名＋手機精確且唯一命中 Client，且案件候選唯一 |
| `CLIENT-BECLASS-BIND-002` | 去敏姓名／手機及候選數，不展開完整候選個資 | 外部確認或修正來源；仍不得以人工挑選繞過唯一匹配規則 | 同上 |
| `CLIENT-BECLASS-BIND-003` | 唯一 Client 的去敏識別、案件候選數 | 修正案件根事實或等待可唯一判定的新來源；不得把 `query_no` 當案件編號 | 唯一 Client 對應唯一可綁定案件 |
| `CLIENT-BECLASS-SOURCE-001` | 缺漏／無效的姓名或手機欄位名稱 | 要求補齊來源；不直接改 alert payload | 更正來源已符合姓名＋手機精確唯一綁定條件 |

LIFF 啟用後的新資料不再產生這組過渡綁定警示；登入身分直接建立來源主人與案件關聯。

### Staff BeClass 歷史過渡

| logical code | 警示中心顯示 | 允許的後續處理 | `auto_resolved` predicate |
|---|---|---|---|
| `STAFF-BECLASS-IDENTITY-001` | 來源列及身分證「缺失／無效」，不顯示原始值 | 要求來源主人補件；未取得有效身分證前不能建 Staff | 新來源提供有效身分證並建立／更新唯一 Staff |
| `STAFF-BECLASS-NAME-001` | 去敏身分識別與姓名「缺失／無效」 | 要求補姓名；維持 DB 姓名不可空 | 新來源具有效姓名並建立／更新唯一 Staff |
| `STAFF-BECLASS-IDENTITY-002` | 去敏身分識別、重複 root 數量及內部資料完整性標記 | 轉交 Staff 資料 owner 的受控 recovery；不得在警示中心 merge 或選一筆 | 正式 Staff root 對該身分證已唯一 |
| `STAFF-BECLASS-NAME-002` | 舊／新姓名皆去敏，標示歷史快照已覆蓋及事件時間 | 只供追溯，不成為公會人員待辦；建立後直接進入 `auto_resolved` 歷史區 | 較新快照已成功寫入且姓名變更事件已保存 |
| `STAFF-BECLASS-FIELD-001` | Staff 連結與缺漏欄位名稱 | 聯絡來源主人；以 Staff typed field-completion command 補指定欄位 | 正式 Staff 該欄位已存在且有效 |
| `STAFF-BECLASS-FIELD-002` | Staff 連結、無效欄位名稱與格式要求 | 同上，不要求整筆歷史資料重送 | 正式 Staff 該欄位已通過 validation |

Staff 退役不是匯入警示操作，也不得由歷史資料推定；另由 WP87 設計。

### Historical Orders

| logical code | 警示中心顯示 | 允許的後續處理 | `auto_resolved` predicate |
|---|---|---|---|
| `ORDER-HIST-FIELD-001` | 案件連結、無法寫入的狀態／日期欄位及格式要求 | 要求修正歷史來源，或由 Orders typed historical-field command 補入；安全欄位不回滾 | 正式歷史欄位已有符合規則的值 |
| `ORDER-HIST-STAFF-001` | 案件連結、去敏人員來源值及「未命中 Staff」 | 修正人員資料或來源；禁止建立不確定 assignment | 該歷史人員可唯一命中 Staff，且關聯已受控寫入 |
| `ORDER-HIST-STAFF-002` | 案件連結、候選數與最小去敏資訊 | 由 Staff 資料 owner 先解除重複，或修正來源；警示中心不可選人 | 同上 |
| `ORDER-HIST-ASSIGNMENT-001` | 案件、人員及不足的期間／關聯證據類型 | 補足歷史證據後重試 typed assignment command | 正式歷史 assignment 已具唯一人員及合法期間 |

### Finance Import

| logical code | 警示中心顯示 | 允許的後續處理 | `auto_resolved` predicate |
|---|---|---|---|
| `FINANCE-SOURCE-001` | 批次／工作表／列、無法正規化的欄位名稱與格式要求；帳號只顯示遮罩 | 要求提供修正版銀行檔或合法外部確認；不可在警示中心直接建立 bank row | 顯式關聯的新來源列已成功正規化為 canonical bank row |
| `FINANCE-ROW-001` | canonical row、日期、金額、方向、遮罩帳號、分類／歸屬 issue codes | 只能呼叫 Finance recovery registry 允許的 typed action，並附必要證據 | canonical row 已完成合法分類、ledger dispatch 或正式 disposition |

跨檔完全相同交易只顯示在匯入 receipt 的「已存在」計數，不進警示中心，也不改變任何既有警示狀態。

## 實作前 live-drift 清單

1. live `domains/anomalies/registry.py` 與 `subsystems/anomalies/alert_workflow.py` 仍只有 `open／claimed／resolved`，不符合已採用的六狀態及 `closed ≠ data fixed` 語意。
2. live `ui/pages/anomalies/beclass_import_review_panel.py` 可直接編輯 `corrected_fields` 與 issue codes；新契約要求警示中心只能追蹤，資料修正必須交給 owning Domain typed command，因此該操作需退役或替換。
3. live `ui/pages/06_finance_alerts.py` 把多種原因收斂為 `IMPORT-004`、`HISTORICAL-ORDER-001` 等 umbrella code；實作前須建立 logical subtype 與顯示 projection，不得只改標籤。
4. `HCM-CASE-001`、`FINANCE-SOURCE-001` 沒有正式 root，必須先設計「後續來源與舊警示的顯式關聯」，否則不可宣稱可自動消除。

本文件是已採用的審核矩陣，但追蹤清單不取代正式規格；schema、production mutation、LINE 自動發送及資料修正入口
仍須依 WP88、DB change gates 與 owning Domain typed command 實作及驗收。
