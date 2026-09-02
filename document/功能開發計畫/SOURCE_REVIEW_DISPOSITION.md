---
doc_type: source-review-disposition
declared_status: current
authority: false
reviewed_at: 2026-09-02
restored_from: b1679e737e50d0d3a064f380df8584e202dd8df4
formal_authority:
  - document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md
  - document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md
  - document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md
  - document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md
  - document/架構重整/01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md
  - document/架構重整/01_規格基線/29_LINE服務說明、客服互動與選單角色正式規格.md
---

# 功能開發計畫來源審閱與退役閘門

本文件只記錄恢復來源文件的逐條處置，不建立產品、資料庫、provider、deployment 或外部操作 Authority。來源文件標題、front matter、舊 `approved`、舊 route、舊畫面與舊流程文字均不得覆蓋上列 current 正式規格與 live owner contract。

## 1. 處置標記

| 標記 | 意義 |
|---|---|
| `已由正式規格承接` | 語意已由 current 正式規格擁有。來源文件只保留追溯，不再是 Authority。 |
| `仍有效待搬移` | 內容仍可能是 current requirement、驗收或操作證據，但尚未完整搬入 owning formal spec，或仍需以 current source／provider／UI 驗證。完成搬移與驗證前不得刪除。 |
| `已被後續裁決否定` | 該 exact route、owner、硬編值、外部效果或執行方式已被較新裁決取代或不再獲授權。不得由來源文件復活。 |

同一段可拆成不同處置；「否定」通常否定的是 exact mechanism／Authority，不代表相鄰的業務目的也被否定。

## 2. `LINE_Rich_Menu_多角色圖文選單與互動中心正式規範.md`

此檔恢復為 `source-review`。檔名中的「正式規範」是歷史名稱，不代表 current Authority。

| 原文範圍 | 處置 | Current 解讀／下一步 |
|---|---|---|
| §一：`default_menu`、`staff_menu`、`union_staff_menu` 三種 audience | `已由正式規格承接` | 由 `29` §7 與 `23` 的 role-scoped binding／current-role 契約擁有。 |
| §一：手機端不以 Alias Tab 模擬其他身分 | `已由正式規格承接` | 角色預覽只能改 preview context；不得建立或猜測 binding。 |
| §二：一般入口至少包含「服務登記」「服務說明」 | `已由正式規格承接` | 由 `29` §§3–4、§7 擁有。 |
| §二：修改登記資料、聯絡真人的業務目的 | `已由正式規格承接` | 修改資料走 Customer Service／owner correction workflow；真人需求走幂等 ticket。 |
| §二：staff 的訂單、排班、請假代班、薪資查詢，以及 union-staff 的審核、客服、異常、看板功能意圖 | `仍有效待搬移` | 必須逐項確認 owning Domain、可見欄位、authentication、typed entry 與 current React／LIFF route；本來源不授權直接查詢或 mutation。 |
| §二：固定 4 格位置、`2500 x 1686`、`chat_bar_text`、`set_as_default` | `仍有效待搬移` | 作 UI／provider 候選；以 current versioned LINE configuration、provider constraint 與 browser／sandbox readback 決定。 |
| §二：`?entry=registration`、各 `?target=...` deep link 作為不可變 contract | `已被後續裁決否定` | `29` 明定不硬編舊 deep link；publication 以 versioned configuration 與已核准 typed entry 為準。 |
| §二：「服務說明」直接回覆舊補助數字、AI 自由生成回答 | `已被後續裁決否定` | 只能回 approved、versioned catalog；LLM 只可選 closed 候選 ID，不能自由撰寫政策答案。 |
| §二：手機端一鍵跨 Domain 核准、直接異常處置或由 Rich Menu action 寫 root | `已被後續裁決否定` | Rich Menu 只導向 owning workflow；不得直接寫 Orders、Scheduling、Finance、Staff、Access 或 binding root。 |
| §三：Draft → Preview → durable publication task → provider terminal readback | `已由正式規格承接` | 由 `29` §8 與 `17` 的 delivery／provider 邊界擁有。 |
| §三：`CreateMenu → UploadImage → SetDefaultAlias → FanoutLink → CleanupOld` 固定為唯一 provider saga | `仍有效待搬移` | 只作候選順序；需對 current adapter、idempotency、unknown outcome、rollback／reconciliation 與 provider API 驗證後再正式化。 |
| §三：發布流程可直接清理所有舊 menu | `已被後續裁決否定` | 不得由來源文字取得 destructive cleanup Authority；需明確 retention、reference/readback 與 exact effect scope。 |

## 3. `LINE_Rich_Menu_本機視覺比對與互動模擬工作室正式規範.md`

此檔恢復為 `source-review`。本機工作室的 current 原則是 preview 零外送；任何畫面範例都不是 provider 成功證據。

| 原文範圍 | 處置 | Current 解讀／下一步 |
|---|---|---|
| §一：熱區 click preview、before/after visual diff、geometry guard、audience sandbox | `已由正式規格承接` | 由 `29` §8 擁有。 |
| §一：本機模擬 LIFF、文字訊息與 bot 回覆 | `仍有效待搬移` | 只可作 deterministic local simulation；需明定 fixture、typed preview result 與 browser acceptance。 |
| §一：preview 期間產生真實 LINE 推播、provider task 或成功 receipt | `已被後續裁決否定` | local visual studio 固定零 provider 外送、零 publication task、零 business receipt。 |
| §一：`Active DB Snapshot` 直接作 UI Authority | `仍有效待搬移` | 必須改成 authenticated typed current-publication Query；DB table／前端 state 不自行成為 Authority。 |
| §一／§三：固定 `2500 x 1686`、滿版、重疊與 route allowlist | `仍有效待搬移` | bounds、overlap、action allowlist 已正式化；exact provider dimension與 route set需由 current configuration／provider constraint驗證。 |
| §二：三 audience 的功能意圖 | `已由正式規格承接` 或 `仍有效待搬移` | audience 已正式化；每個 staff／union-staff entry 的 owner、欄位、route 與 authorization 仍待逐項搬移。 |
| §二：舊 `?entry=`／`?target=` 字串、固定示範畫面與假資料 | `已被後續裁決否定` | 不得當 current route、root fact 或驗收 oracle；只能作歷史 mock evidence。 |
| §二：硬編補助回答、服務時間、電話或模型自動回覆 wording | `已被後續裁決否定` | wording 必須來自 reviewed、versioned、published catalog；個案值走 owner Query 或人工。 |
| §二：表單欄位、Diff、日曆色彩、薪資／客服／異常卡片等互動細節 | `仍有效待搬移` | 對 current React component、API schema、owner visibility 與 browser acceptance逐項核對。 |
| §三：current/draft 差異、逐按鈕屬性比較、bounds、no-overlap、action non-empty | `已由正式規格承接` | `29` §8 已承接 observable properties。 |
| §三：綠／橘／紅固定色義與「100% 合規」徽章 | `仍有效待搬移` | 屬 UI acceptance 候選，不得取代 typed validation result；需與 current design核對。 |
| §四：所有 preview／click／diff 僅在本機、零 DB write、零真實推播 | `已由正式規格承接` | `29` §8 的明確不變量。 |
| §四：只靠特定「發布」按鈕與理由欄即可取得 provider publish Authority | `已被後續裁決否定` | UI gesture 不等於 Authority；仍需 authenticated command、idempotency、durable task、provider terminal readback。 |

## 4. `NAS_檔案庫與資料中心管理介面正式規範.md`

此檔恢復為 `source-review`。原 front matter 的 `declared_status: approved` 與 `Data-Center-and-Controlled-Storage-Integration` owner 不再授予 current Authority。

| 原文範圍 | 處置 | Current 解讀／下一步 |
|---|---|---|
| front matter 與 §1：建立獨立 Data Center／Controlled Storage 業務 owner | `已被後續裁決否定` | 共用 storage 不擁有業務生命週期；subject、purpose、可見性與完成條件由 owning Domain 決定。 |
| §1：不向 Web／JSON／log 暴露實體磁碟路徑，metadata 與 bytes 分離 | `已由正式規格承接` | 由 `00` 的 root-fact／storage boundary 與 current typed adapter原則承接。 |
| §1：正式 target 固定為 Synology NAS | `仍有效待搬移` | 僅作部署候選；需指定 current mount／adapter、operator、readiness、backup與production Authority。 |
| §2：契約、服務日期、order notice、baby／meal photo、staff resume／certificate／health exam、Rich Menu image 等 purpose | `仍有效待搬移` | 需搬入正式 controlled-file owner／purpose registry並與 typed enum、schema、consumer tests同步。 |
| §2：匯入 workbook與即時報表一律不得保存 | `仍有效待搬移` | 需依各 owner 的 retention／evidence requirement逐項裁決，不能只以節省空間決定。 |
| §3：Freeze-Before-Send／外發 bytes 必須可追到已封存版本與 digest | `仍有效待搬移` | 具實質 data-integrity需求；需由 owning delivery／document formal spec承接 exact transaction、outbox與readback。 |
| §4：版本、digest、用途可辨識的人類顯示名稱 | `仍有效待搬移` | 可保留為 display metadata候選，但不得當 object identity或storage locator。 |
| §4：實體 object key／路徑或公開 metadata含 client／staff姓名 | `已被後續裁決否定` | current opaque identity與PII邊界禁止以姓名、原檔名、UNC／mount locator形成 identity或公開路徑。 |
| §5：capacity/readiness 可觀測、版本化補充上傳 | `仍有效待搬移` | 需搬入 operational readiness與staging／Preview／Apply正式契約；capacity failure不得偽裝成空清單。 |
| §5：15%／5%固定告警門檻 | `仍有效待搬移` | 只能作可配置 operational候選，不得由舊文件固定為 business rule。 |
| §5／§7：管理員可直接永久刪除 registered／履約中正式檔案或批次刪除 | `已被後續裁決否定` | 本來源不授權不可逆正式刪除；cleanup只可在exact owner／reference／retention／receipt條件成立後執行。 |
| §6：React資料中心三分頁、雙欄 explorer、容量條、搜尋與預覽 UX | `仍有效待搬移` | 逐項與 current React入口、typed Query、download／preview capability與browser acceptance核對。 |
| §6：舊 Streamlit／`#databrowser`相容入口作為 current requirement | `已被後續裁決否定` | `ui/`與Streamlit入口已退役；只保留 current React正式入口，不以舊 anchor復活 legacy UI。 |
| §7：展示／下載／上傳／發送時序的observable acceptance | `仍有效待搬移` | 需拆到 owning UI、controlled-file、document與delivery正式規格。 |
| §7：以刪除成功、容量立即釋放作為必備驗收 | `已被後續裁決否定` | 未有exact deletion contract、retention、reference與readback前不得宣稱。 |
| §8：保存現有 React UX，不以 API 串接整檔覆蓋 | `仍有效待搬移` | 可作 current UI regression acceptance；需綁定實際 component與focused browser tests。 |
| §8：來源文件可對未來 Agent 發出無限期施工禁令或新增 API Authority | `已被後續裁決否定` | 來源文件不是 Authority；修改範圍與API由最新規格、current owner與明確任務決定。 |
| §9.1：authenticated storage routes、Preview零寫入、download不建立public URL | `仍有效待搬移` | 需搬入正式 controlled-file public contract並以 current OpenAPI／route tests驗證。 |
| §9.2：closed owner／purpose pairing | `仍有效待搬移` | 需由 owning formal specs與typed registry共同承接，不能留在source-review作唯一契約。 |
| §9.3：opaque ID、不含PII／locator、digest不是identity | `已由正式規格承接`（原則）／`仍有效待搬移`（exact schema） | 原則由Global storage boundary承接；`cf_`／`cfs_` regex與projection欄位仍需正式化及current-source驗證。 |
| §9.4：staging TTL、Preview／Apply、outer UoW、idempotency、cleanup reconciliation | `仍有效待搬移` | 屬machine contract，必須搬入正式owner spec並對schema、repository、worker與tests逐項驗證。 |
| §9.5：receipt schema、unknown-outcome readback、reconciliation closed outcomes | `仍有效待搬移` | 同上；不得只由source-review持有。 |
| §9.6：reference-aware finalize、lease、Scheduling bridge與no-backfill | `已由正式規格承接`（Task 97方向）／`仍有效待搬移`（exact fields／IDs／object key） | `15`已保存Task 97高階裁決；exact machine contract仍需回寫owning specs並與current schema／tests一致。 |

## 5. Current 狀態與刪除閘門

- 三份 source-review 文件：`RESTORED`。
- 逐條 disposition：`COMPLETE_FOR_RESTORATION`；其中仍有多項 `仍有效待搬移`。
- executable consumer 同步：`NOT_REQUIRED_FOR_THIS_RESTORE`；本次不刪除、不改程式 consumer。未來退役前必須重新搜尋並改綁所有 code、test、validation JSON、launcher與文件 consumer。
- current index 同步：LINE來源處置由 `29` 修正；欄位盤點路徑由 `15` 原有規則及恢復後readback重新成立。NAS exact contract尚未完整搬入owning formal spec。
- 再次刪除來源文件：`BLOCKED`。

只有在每一個 `仍有效待搬移` 項目已搬入唯一 owning formal spec、每一個 `已被後續裁決否定` 項目已從 current consumer／索引移除、executable consumers與 current index 完成同步，且刪除後 deterministic readback／focused tests通過時，才可再次提出刪除。