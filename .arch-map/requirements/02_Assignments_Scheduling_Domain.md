# Assignments／Scheduling Domain

## 1. 文件邊界與所有權

- 狀態：`current-spec`
- Owner：Assignments／Scheduling Domain（`domains/scheduling/`、`subsystems/scheduling/`）
- 單一負責範圍：`generation + effective` 排班世代模型、同日分時班次占用（`SHIFT-01～05`）、`waiting-deposit` 檔期鎖、正式指派（`case_staff_assignments`）與逐日服務事實（`staff_schedule.assignment_id`）、七日緩衝提醒、服務開始與人工排班（`SSTART-01～08`）、請假／順延／局部代班／服務中換人（`handover-v1`／`leave-v1`）及其批次重播與 AutoComplete 鎖定競爭、甘特月曆與歷史指派投影、統一六層確定性加鎖順序，以及 `SCHEDULE-002／003／006` 異常決策矩陣。
- 關聯引用：見 [Global 共同契約](00_Global_共同契約.md)、[Orders Domain](01_Orders_Domain.md)、[媒合候選池與客戶決定及通勤](02A_媒合候選池與客戶決定及通勤規格.md)、[Payroll Domain](03_Payroll_Domain.md)、[Client Finance Domain](04_Client_Finance_Domain.md)、[LINE 客服與月嫂自助服務](20_LINE客服與月嫂自助服務正式規格.md)、[Contract Signing 正式規格](21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md)、[Staff Matching Preferences](24_Staff_Matching_Preferences與不可服務期間正式規格.md)、[歷史訂單生命週期與服務天數帳務](27_歷史訂單生命週期與服務天數帳務正式規格.md)。

## 2. 核心不變量與資料模型（SSOT）

| 事實 | 唯一權威 |
|---|---|
| 指派歸屬與區段歷史 | `case_staff_assignments`（`generation + effective` 版本模型） |
| 每日正式服務 owner | effective `staff_schedule.assignment_id` |
| 已完成案歷史指派 | `case_staff_assignments.status=completed` 及其正式起訖／時段（無日排班亦唯讀可視） |
| 檔期占用 | 有效逐日服務班次的實際起訖時刻（Taipei `[start, end)`）、等待訂金保留、不可服務期間及歷史預定 |
| actual hours | effective 逐日班次的服務時數合計；合併與分裂的服務量依 [§3.4.2](#service-date-merge-split) |
| assignment status | 明確時段依首／末正式服務時刻與 Business Clock 推導（`planned | active | completed`）；協調模式依 [§3.4.2](#service-date-merge-split) 的日期及生命週期事實投影 |
| leave／substitution lineage | `batch_key` header ＋ append-only `(batch_key, batch_item_index)` events |
| waiting-deposit lock | lock header、服務班次日與 events（自動於接受配對＋確認日期齊備時取得） |
| 七日 buffer | 獨立緩衝事實（只作協調提醒，全案開工時同交易解除，絕不擋正式寫入） |
| 長假／不可服務期間 | 版本化不可服務期間與取消事件（[Staff Matching Preferences](24_Staff_Matching_Preferences與不可服務期間正式規格.md)） |

- **嚴格禁止依賴**：`orders.staff_id`、`planned_hours`、`actual_hours_adjustments`、`replaced_assignment_id` 與 `original_assigned_*`。
- **Generation 模型不變量**：同案同一時刻至多存在一個 `effective` generation；正式區段重建採 Preview → Apply `cancel-old / create-new`（僅改費用／計薪時數／下廚且排班形狀不變者沿用現行 generation）。[純日期合併、分裂及復原](#service-date-merge-split) 使用專用版本命令，保留原 generation 與 assignment identity，以生效日班及不可變操作紀錄保存異動並遞增 Scheduling aggregate version，避免連動帳務來源；取消、替換及停止生效的來源班次均保留歷史並自目前投影排除。

## 3. 公開契約與流程

### 3.1 同日分時占用與甘特月曆（`SHIFT-01～05`）

- **`SHIFT-01／02`（班次與可用性）**：具明確時段的班次以 Orders 每日起訖時間與跨日標記（`0 | 1`）比較「含開始、不含結束」時間區間（首尾相接可排；跨午夜班次占兩曆日而班次與工時歸開始日一次；代班占用實際承接者；月嫂全日不可服務仍阻擋相交；缺時段且可能相交回「時段待確認」）。合併與分裂後的協調時段依 [§3.4.2](#service-date-merge-split)，不得從服務時數自行推導實際起訖時間。
- **`SHIFT-03／04`**：跨案件重複排班僅在同一月嫂的服務時段相交，且兩案 Orders `actual_start_date` 均已存在時成立。只有一案或兩案皆缺實際開始日，均保留為「歷史預定」提醒，不阻擋其中任一案排班。候選排查與正式 Apply 使用相同規則，Apply fresh-read 本次命令保存後的實際開始日；不得以預計開始日、指派狀態或目前日期冒充實際開始日。等待訂金保留一律只作提醒，不阻擋案件排班；保留其來源與既有鎖生命週期。月嫂不可服務及無法確認歸屬的既有占用沿原有驗證。轉換或重建僅排除本次實際被替換來源；兩案各計服務量與工時，不依人日去重。
- **`SHIFT-05` & Calendar Read（甘特圖）**：
  - 逐月逐人顯示現役班次、等待訂金保留（非工作日）、七日緩衝（非工作日／非服務中）、不可服務、唯讀歷史指派與歷史預定。連續日僅於同來源、時段與狀態一致時合併。同日多班上下並列並於跨日續班標示。
  - **歷史指派的整案日期**。工會排班日曆以既有歷史指派決定案件出現在哪位人員的列。能確認整案起訖時，每人每案顯示一個唯讀區塊，按 Orders 起訖標示日期及跨月位置。起訖各自優先採實際日期，缺少時採訂單預定日期。整案期間只供月曆呈現，指派歸屬、逐日服務、檔期占用、出勤及計薪沿用各自的權威資料。既有歷史案件直接讀取原訂單，無須重新匯入。整案起訖缺漏或無法讀取時，保留原指派區段的位置並明示整案日期不可用。
  - **整案日期驗收**。S：已匯入的歷史完成案，其整案起訖為 2026-10-05 ～ 2026-11-02，11 月的指派投影只包含 11 月 1 至 2 日。T：從工會排班月曆辨識整案期間。A：選取 11 月，找到該案並查看年度時間軸及案件明細。R：唯讀歷史區塊從 10 月上旬延伸到 11 月上旬，區塊與明細顯示相同整案起訖，明細不顯示指派編號。
  - **歷史預定**。工會排班日曆保留「歷史訂單－未服務」及從該狀態重啟後仍待儲存正式班表的案件，取最新已採納紀錄中可確認的原月嫂與 Orders 預定起訖日，呈現唯讀預定區段。跨案比較依 `SHIFT-03／04` 的兩案實際開始日判斷阻擋資格；一案或兩案皆缺實際開始日的相交來源，只列歷史預定提醒，不能當作全日硬保留阻擋排班。逐日服務、出勤、計薪及訂金鎖各沿原有來源，案件取消時解除其預定提醒。
  - **衝突與提醒明細**。推薦人選及服務日期月曆逐筆保留來源案號、服務日期、實際起訖時刻、跨日日期與阻擋或提醒類別。同日不同案件不得因種類相同而合併遺失。沒有可確認時段的預定來源顯示「時間未確定」，不補造服務時間。
  - **跨案判定驗收**。S：同一月嫂的兩案具有相交服務時段，分別組合兩案都有、僅一案有及兩案皆無實際開始日。T：辨識衝突並安排服務。A：查詢推薦及月曆後提交排班；再以首尾相接的兩班重查。R：僅兩案都有實際開始日且時段相交時回 typed conflict 並保留案號與時段；其餘缺實際開始日的組合保留提醒並允許排班，首尾相接不構成重複排班。
    - 月查詢確認當月仍有歷史預定後，每人每案顯示一個唯讀區塊。區塊文字、年度時間軸位置、寬度、提示及明細使用 Orders 完整預定起訖。若起訖缺漏或無法讀取，保留當月區段位置並標示整案日期不可用。月查詢與衝突判定仍按實際保留期間處理。
    - S：歷史未服務案或重啟待排班案已有 2026-11-28 ～ 2026-12-27 的預定。T：確認完整保留期間。A：選取 11 月，查看區塊、提示與明細。R：區塊從 11 月下旬延伸到 12 月下旬，完整日期一致。正式班表接手後，原歷史預定區塊退出。
  - **正式指派的區段日期**。排班區塊帶有指派編號時，補充日期只採同一指派的區段起訖。若缺少區段起訖，使用該區塊自身的班次日期。整案實際日期屬於 Orders，指派區段定位使用 Scheduling 的日期。無指派編號的保留或排查沿用各自的有效來源。窄區塊的提示與明細可查看其完整日期。
    - S：同一案件有兩筆不同期間的指派，且另一筆列在查詢結果前面。T：確認各指派的區段。A：查看兩段位置、日期與明細，再以缺少精確指派資料的回應重查。R：各段使用自己的指派日期，缺少時各自回到班次日期。
  - **訂單狀態回歸**。以 [訂單工作分類](01A_訂單看板與事前日期及歷史採納規格.md#22-未完成清單與-beta-看板wb-state-0105) 的十種狀態逐一核對區塊、日期來源與位置。待補件或洽談案沒有排班或檔期鎖時只參與符合條件的排查。取消案不得恢復已解除的保留。歷史服務中、服務完成或帳務完成僅在具可顯示的歷史指派時出現歷史區塊。
  - Calendar「可進行出勤精算案件」下拉選單採單一批次 `GET .../staff/{staff_id}/assignment-schedules` 交集 Orders 摘要（禁止 N+1 或 `orders.staff_id` fallback）。
  - **開案主責（`resolve_opening_primary_staff`）**：查詢從第一個有效服務區段判定開案主責。同一人員的排班版本重建，或首日由他人代班，仍追溯原開案主責；服務前整案換人則由接任月嫂擔任開案主責。服務中換人不改原開案主責。此查詢不修改班表。
    - **首日代班例**：甲是原開案主責，首日由乙代班。即使之後重建乙的該次代班版本，查詢開案主責仍得到甲，不把代班的乙當成主責。
    - **整案替換例**：案件尚未開工，經辦將整案由甲換為乙。查詢開案主責時應得到乙，不再沿用甲。

### 3.2 Waiting Deposit Lock、Assignment Plan 與 Actual Start 重算

- **Waiting Deposit Lock**：支持 Acquire（接受配對＋確認日期齊備時最後條件 Apply 自動執行）、Release-to-unbound、Cancel 與 Convert（首次正式排班必須轉換有效 waiting lock，缺鎖回 `assignment_plan_bootstrap.waiting_lock_required`；訂金逾期不自動釋放）；保留各服務日實際班次（不含週休，buffer 獨立）；等待訂金保留可與他案檔期並列，保留本身不構成正式排班衝突。
- **Assignment Plan Query**：唯讀回傳現行版本與各 owner version（Finance／Payroll 未建立時回 `NULL`，禁止填 0）。
- **Actual Start 已有有效排班重算**：以現行 effective assignments 之順序、月嫂與每段既有 `official-service-day count` 為不變輸入（禁止平移舊日或重分配天數），依序由新 `actual_start_date` 逐日重算各段（保留已核准之請假占用／代班 outcome 與假日事實，任一衝突或 lineage 無法承接回 typed conflict 零寫入，並交 Payroll 搬移 1-to-1 `source_assignment_id` 費率快照）。
- **Holiday facts**：`SchedulingHolidayQuery` 作為版本化唯讀 port，納入 Preview fingerprint 並在 Apply 重鎖重讀（無法讀取回 `holiday_calendar_unavailable`）。

<a id="service-start-and-substitution"></a>

### 3.3 服務開始與排班（`SSTART-01～08`）

```text
客戶與月嫂於原案件群組協調（客戶 LIFF 移除日期/天數修改入口）
→ 月嫂於群組呼叫「月嫂專屬小幫手選單」（輸入「工會」或「小幫手」，純 line_webhook_reply 0 Push 回覆）
  ├─ 【確認開工日】：月嫂或客戶由原生日期滾輪選定約定開工日發起提議 → Reply 群組「開工日期確認單」
  │   → 對方點【確認日期】且無衝突＋契約／訂金／時段齊全（提案方誤點同意靜默無反應；按重新選擇取消本次提議）
  │   → 共同 coordinator 單一 UoW 更新 Orders/Scheduling/Finance/Payroll
  │   → Reply 生效文案（提示查看【服務排程】）→ 正式開工後選單自動隱藏【確認開工日】
  ├─ 【服務排程】：7 欄排班日曆卡片（圖例標註多月嫂區段與排休日）；開工前提示預期排程或先確認開工日，開工後查看已服務天數、排休日與完工日
  └─ 不接受／檔期衝突 → 回覆未成立原因，保留原正式事實
      → 具排班操作權限的管理員從原案件直接調整排班
```

- **核心條款（`SSTART-01～08`）**：
  - **月嫂群組選單與零 Push 額度**：月嫂於案件服務群組操作「月嫂專屬小幫手選單」（含【確認開工日】、【服務排程】、【雙方合意延期】、【專員協助】與【客戶常見疑問標準回答】），互動全程皆使用 Webhook `replyToken` 同步回覆，嚴禁呼叫 Push API 消耗額度。
  - **工會首次儲存班表**：一般案件已選定月嫂、簽約完成、符合訂金條件且尚無正式班表時，授權工會人員核對實際開始日與服務日，並依 [多月嫂排班 §3.4.1](#multi-caregiver-service-correction) 完成逐日分配。工會提交明確記錄為工會確認，由共同 Apply 在同一交易保存日期、正式指派、逐日班次與相關業務結果。若已有同方案人員的有效指派但完全沒有正式逐日班次，須核對該指派並接續建立班次，避免產生重複的有效指派。檔期、版本或承諾不符時整筆阻擋。
  - **班表成立判定**：已確認日期以 Orders 日期版本表示。現行正式排班以有效指派及其有效逐日工作班次為準；存在有效指派且缺逐日工作班次時，顯示待處理並回傳可辨識的擋關原因。
  - **衝突處理**：開工確認遇到檔期衝突時，回覆可辨識的衝突原因，Orders 日期、正式指派、班表與帳務均維持原狀。系統不建立代班需求或待辦，不啟動替代人選意願、入群邀請或代班待辦通知。具排班操作權限的管理員依 [多月嫂排班 §3.4.1](#multi-caregiver-service-correction) 在原案件直接調整，確認時沿用既有 fresh-read、typed conflict 與單一外層交易契約。
  - 客戶提及服務日期或天數變更時，依 [客戶資料與訂單異動流程](20_LINE客服與月嫂自助服務正式規格.md#53-客戶資料與訂單異動流程) 處理。停用雙方「確認日期表／拒絕日期表」卡按鈕（確認日期表路由固定回 `410`）。
  - 服務中局部代班保持全案原 `actual_start_date` 與第一期款到期日；只有全案實際開工日改變時同交易同步第一、二期到期日。未來開工日之排班先保存正式結果，到期由背景 canonical lifecycle worker 轉為 `服務中`。
  - **共用入口**：`POST /api/v1/line/staff-self-service/service-start/*`、工會 `POST /api/v1/line/mobile-admin/service-start/*` 及 `GET/POST /api/v1/scheduling/service-start/*`；一般具備權限工會人員皆可操作（不限 `system_admin`）。各入口的退役分支依 [入口治理](19_Global_Entry_Point_Governance.md#32-已停用移除之端點與替代邊界)。

<a id="leave-substitution"></a>

### 3.4 雙方合意延期、局部代班與服務中換人（`leave-v1`、`handover-v1`）

- **雙方合意延期（`leave-v1`）**。適用於已正式排班、尚未完工的案件。月嫂與客戶協調原服務日及延期補班日，總服務天數與政府補助時數守恆。月嫂依 [LIFF 選日與群組確認流程](20_LINE客服與月嫂自助服務正式規格.md#42-雙方合意延期leave-v1) 提議。預檢唯讀。客戶同意後，於單一 UoW 重讀檔期並以 `leave-v1` 的 `execution_dates` 更新正式班表。正式確認時的檔期衝突依 [§3.3 衝突處理](#service-start-and-substitution) 辦理。
- **批次重播與 AutoComplete 競爭**：`batch_key` 加鎖檢查 header／item_count／連續 ordinal／snapshot／fingerprint（同鍵異內容回 `batch_key_request_identity_conflict`）；Apply 與 [Orders AutoComplete](01_Orders_Domain.md#32-autocompleteorderservice-與完工後日期更正) **皆須先鎖定同一 Orders lifecycle aggregate 驗證 expected version**，先提交者勝出、後到者以 stale 失敗零寫入。
- **服務中換人（`handover-v1`）**：針對已開工、仍有剩餘服務日且未鎖定之案件指定原 segment：選定接任月嫂詢問意願（附全部剩餘日）→ 願意後單人邀請並取得真實入群 membership → 工會填入交接日（`>= 今日` Taipei 時鐘，不得遺漏或改動已服務日與原薪資）→ 委派 `LeaveSubstitutionBatchIntent.handover_date` Preview／Apply 於單一 UoW 更新排班、原月嫂保留已付／匯出段與 Payroll handover 差額（見 [Payroll §3.5](03_Payroll_Domain.md#35-服務中換人付款承接staff-handover)）＋發送無按鈕群組結果表（維持最多 4 個有效 segments）。

<a id="multi-caregiver-service-correction"></a>

#### 3.4.1 多月嫂排班

本節的帳務承接屬服務歸屬及約定條件更正；純日期合併與分裂使用 [§3.4.2](#service-date-merge-split) 的帳務不變契約。

- **一般訂單首排**。授權經辦從 [案件人力配置](31_MultiCaregiver_Admin_UI正式規格.md#case-staffing) 帶入已確認的日期與人員。每個服務日恰分配給一位月嫂，同一位月嫂可負責交錯或不連續的日期。完成分配後按「儲存班表」。新增、替換月嫂或改變各人分配天數時，須記錄調整原因及協調依據。儲存在同一交易重讀並驗證有效推薦方案、簽約承諾、總服務量及檔期。任一條件未通過時整筆回滾，原契約、客戶確認及定金核銷紀錄均予保留。
- **編輯範圍**。已排班案件讀入正式班次，可調整月嫂、服務區段或服務日期，每個服務日恰分配一次。涉及約定總天數、每日時數、每日時段或客戶價金變更時，依 [Orders Terms](01_Orders_Domain.md#34-order-terms-previewapply-與時段下廚契約) 保存。由 Orders Terms 提交的全案排班替換使用既有世代、指派血緣及檔期衝突檢查。既有月嫂意願、入群及通知流程仍可使用，線下已協調者由經辦記錄原因及依據後辦理。
- **調整後續排班**。一般服務中可從交接日起由另一位月嫂承接原區段剩餘班次，或將指定後續服務日交由已同意代班的月嫂承接。歷史服務中依 [歷史服務歸屬與後續排班](27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-service-attribution-correction) 接續。一般案件的預覽逐日顯示所選區段異動，其餘班次、已服務紀錄及原開工事實維持。
- **人工局部代班**。具排班操作權限的管理員從原案件開啟多月嫂排班，依目前正式班次選定後續服務日並分配已同意代班的月嫂，記錄協調依據與原因。原日期換人時，原服務日、約定服務量、全案開工日、客戶應收與付款到期日維持。班表保存無須等待入群，也不發送邀請或群組通知。Preview／Apply 依原案件、正式指派及各 owner 版本驗證，在同一交易保存班表與帳務；不使用代班待辦識別或待辦版本，也不提交待辦結案。其他日期與人員調整依本節的編輯範圍辦理。
- **更正已服務紀錄**。一般服務中可依證據重新分配所選區段的已服務日，後續班表維持原安排。一般完工案可重新分配原正式服務日，每個原班次恰分配一次，保留原完工事件與服務資料鎖。歷史已服務部分依 [歷史服務歸屬與後續排班](27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-service-attribution-correction) 處理。經辦保存原因及來源證據，沿用本案已確認的服務量、時數與客戶計價基準。同時需更正已服務部分與調整後續班次時，各自預覽及確認，下一次預覽讀取前一次生效結果。
- **交易契約**。Query 與 Preview 零寫入。Apply 先鎖定並驗證目前 Orders lifecycle、Scheduling、相關歷史服務量、Payroll、Staff Payables 及結清來源版本。服務歸屬有效且正式班次無檔期衝突時，Apply 儲存正式排班或歷史服務天數。區段、服務量、檔期或來源版本衝突回 typed error 並零寫入；交易錯誤整筆回滾。
- **帳務同交易承接**。預覽逐一顯示受影響月嫂及款項來源的應付差額與核銷狀態。依受影響的受款人與來源判斷，其他區段已有核銷仍可調整本次未付款、未核銷的區段。原應付有人工改額時先確認採用的計算結果。確認時重讀核銷及班表，變動則要求重新預覽。各 owner 在同一外層交易提交正式排班、[Payroll 應付更正](03_Payroll_Domain.md#service-attribution-payroll-correction)及 [Staff Payables 分來源待付與追償](16_Staff_Payables與Client_Refund正式規格.md#service-attribution-settlement)。原出款及核銷連結保留，同鍵同命令回原收據，同鍵異內容回 typed conflict。既有人工分期無法由班表推導分來源金額時，正式排班與帳務待核對事件一同提交，受影響的舊應付暫停再核銷。經辦從本案帳務或排班頁補上各區段補助金額及依據，預覽並確認後按來源處理應付與追償，保留原受款人、來源及核銷。補證只更新帳務與核對事件，沿用當時最新正式班表。歷史單的原付款證據與帳務重開依 [歷史服務歸屬與帳務完成](27_歷史訂單生命週期與服務天數帳務正式規格.md#historical-service-attribution-correction) 處理，符合重啟條件的案件重啟後沿一般流程建立與編輯正式班表。

<a id="service-date-merge-split"></a>

#### 3.4.2 合併與分裂服務日期 ^service-date-merge-split

- **服務量與所有權**。本功能只重組同一案件的實際服務日期、各日時數及當日月嫂。Scheduling 擁有逐日服務量及人員歸屬；事前確認與正式排班的保存分界沿用 [Confirm Service Dates](01A_訂單看板與事前日期及歷史採納規格.md#32-confirm-service-dates-與休假覆寫契約)。原訂合約天數、每日時數、每日時段及總服務時數均不變，合併或分裂前後的逐日時數合計必須相同。未選取的班次保持原安排，不以實際日期數等於合約天數作為本功能的儲存條件。
- **合併與分裂**。兩個各 4 小時的服務日可合併到操作者指定的一個日期，該日服務 8 小時；一個 8 小時服務日可分裂到指定的兩個不同日期，每日各 4 小時。日期不必相鄰或同週、同月，不限制操作次數。已合併或分裂的結果可再觸發反向操作，依下述復原規則回到該次調整前的正常排班。不得因日期來自不同月嫂而禁止合併。
- **逐日時數與復原**。逐日服務時數未覆寫時沿用案件原訂每日時數；合併或分裂的結果保存明確的 4 或 8 小時，不另設獨立時段模式欄位。保存結果時，須能追溯該次來源日期、各日月嫂、逐日時數原值及結果日期的配對。再次觸發已合併結果的分裂，恢復原來兩個日期及各自的人員與時數；再次觸發已分裂結果的合併，恢復原來的一個日期、人員與時數。選取分裂結果中的任一日期時，可辨識並一併復原同組的另一日，不要求重新手選原日期或猜測相鄰日期。原值未覆寫者復原為未覆寫，恢復原訂時段的正常呈現；原值已有其他排班調整者恢復該次操作前的原值。重新載入畫面後仍可復原，只更動該次配對涉及的班次，不回退整案班表或其他日期的後續異動。來源或結果已被其他操作改動時依目前版本重新核對，不得盲目覆寫。
- **當日月嫂**。公會業務規則為同一案件同一服務日只由一位月嫂負責，不提供同案同日多人分時服務。合併後選定一位月嫂負責當日完整 8 小時；分裂後每個日期亦各有一位月嫂。人員歸屬供排班與工時統計，不改寫原帳務受款人或金額。
- **時段**。原訂上下班時間不調整。合併或分裂後的日期採自行協調模式，實際起訖由月嫂與客戶自行協調，不要求在本功能填寫或另存具體上下班時間。排班仍明確保存當日服務時數，不能以協調文字代替時數。呈現方式見 [Admin UI §2.4](31_MultiCaregiver_Admin_UI正式規格.md#service-date-merge-split-ui)。不得把原訂時段或以 4／8 小時推算的時段當成已確認的實際時段。協調模式是合法的排班資料，不屬 §3.1 的時段資料缺漏，不因缺少具體時刻而拒絕儲存。同人跨案的日期重疊保留為協調提醒，不能據未知時段判定時間重疊或宣稱該時段可用，也不得自動視為全天禁排；月嫂已登錄的全日不可服務等明確衝突仍依其事實處理。
- **指派狀態**。既有來源班次重組後保留可追溯的原開工與完工事實。協調模式先依既有完工事實保留 `completed`；尚無開工事實或尚未到該區段首個服務日者投影 `planned`；已有開工事實且區段尚未結束者投影 `active`，區段服務日期均已過者投影 `completed`。狀態以 Business Clock 的臺灣日期及既有生命週期事實判斷，不杜撰具體上下班時間；本操作本身不建立或撤銷 Orders 開工、完工事件。
- **帳務不變**。本功能不新增、重算、重分配或更正客戶應收、月嫂應付、薪資費率快照、補助金額、核銷及付款到期日；既有受款人、款項來源及付款紀錄保留。跨月嫂合併也不得轉移既有款項，不要求先辦理帳務重開或補證，不觸發本節以外的服務歸屬帳務更正。原開工、完工事件與其帳務基準不由本功能改寫，排班起迄顯示取調整後的實際日期。
- **變更開始日後恢復正常排班**。案件已有合併或分裂結果，再變更服務開始日時，只提供「取消合併／分裂結果並重新排班」這一種確認結果。確認後取消目前合併／分裂結果，以調整前的正常服務量及人員歸屬，依新開始日、原訂每日時數及目前適用的排休／假日規則重算；清除逐日時數覆寫，恢復原訂時段的正常排班模式。一般日曆與合併／分裂入口讀取同一份新日期，不沿用舊結果或其可復原配對。歷史操作紀錄保留。事前日期與已有正式班表都適用；沒有正式班表時不因此建立正式指派。只修改輸入、預覽或取消確認皆不保存，開始日未變時也不取消既有調整。沒有合併／分裂結果的案件維持原本開始日與人工選日流程。
- **保存與讀回**。Query／Preview 零寫入。Apply 沿用相關 Orders／Scheduling 版本、單一 outer UoW 及正式排班 writer，重新核對來源日期、時數、當日唯一人員及總時數。正式班表只保留一個 effective generation；除本節明確取消結果並重排的開始日變更外，其他重排、請假或再次合併分裂仍承接逐日時數與異動配對，明確復原時依該次來源原值恢復。取消結果及新日期的保存須在同一交易完成。版本或同案同日歸屬衝突須可辨識，失敗整筆回滾，不留下部分日期。相同命令重送不重複合併、分裂、復原或取消重排，也不得因重送而來回切換狀態，不發送外部通知。成功後回讀目前生效的逐日結果，報表沿用 [營運報表](34_營運報表與統計口徑正式規格.md#weekly-service-daily-hours) 的口徑。
  - 正式日期調整與復原在同一交易經 Orders writer 同步 `actual_end_date` 為最後有效服務日並推進 Orders lifecycle version，不改原開工／完工事件及付款基準；事前調整則於正式首排承接後同步。最後協調日的完工時點依 [Orders §3.2](01_Orders_Domain.md#32-autocompleteorderservice-與完工後日期更正) 採臺北日終，不能因合法日期筆數變動暫停完工。

| S：具體情境與前提 | T：使用者任務 | A：操作 | R：可判定結果 |
|---|---|---|---|
| 案件原訂 20 天、每天 4 小時，已安排 80 小時，其中兩日各 4 小時。 | 將兩日合成一天。 | 選兩日、指定合併日期與一位月嫂，儲存後重新查詢。 | 實際為 19 日、80 小時；指定日由選定月嫂服務 8 小時，原訂天數及全部帳務不變。 |
| 一個 8 小時服務日，兩個目標日期位於不同週或不同月。 | 分裂後再次合併。 | 分成兩日各 4 小時，讀回後再選這兩日合併。 | 兩次儲存均成功，總時數及原帳務相同；不以跨週、跨月或曾調整過為由拒絕。 |
| 11/9 與 11/12 原各 4 小時，分屬兩位月嫂，合併到 11/10 由一位月嫂服務 8 小時。 | 復原合併。 | 重新載入後對 11/10 再觸發分裂並保存。 | 原 11/9、11/12 及各日月嫂、時數原值恢復，移除該次 11/10 結果；原為未覆寫者恢復原訂時段呈現，其他日期與帳務不變。 |
| 11/9 原 8 小時，分裂為 11/10 與 11/12 各 4 小時。 | 復原分裂。 | 重新載入後從其中一天觸發合併並保存，再重送相同命令。 | 一併收回同組兩日並恢復原 11/9 的月嫂及時數原值；重送仍為相同復原結果，不再次切換，其他日期與帳務不變。 |
| 兩個 4 小時來源日期分屬不同月嫂。 | 選一人完成合併後服務。 | 選定合併日與其中一位月嫂後儲存。 | 當日只有選定月嫂的 8 小時班次，原受款人及款項不轉移，也不要求帳務解鎖。 |
| 另一位經辦已修改來源班次，或結果在同案同日安排兩位月嫂。 | 避免覆寫或產生多人同日服務。 | 提交過期版本或同案同日多人結果。 | 回傳可辨識衝突，原班表及全部帳務維持；不得只保存其中一部分。 |
| 原訂 20 日、每日 4 小時，兩日已合併為一日，或原訂每日 8 小時的班次已分裂；分別有事前日期及正式班表。 | 變更開始日並恢復正常排班。 | 輸入新開始日，預覽並確認取消合併／分裂結果及重新排班，再重新載入。 | 恢復原訂正常服務量、每日時數及調整前的人員歸屬，日期依新開始日重算；兩個入口一致、沒有舊覆寫或舊結果的可復原配對，原帳務與歷史紀錄保留。 |
| 案件已有合併／分裂結果。 | 在確認前核對新班表並避免部分保存。 | 只改開始日後取消；另以過期預覽確認取消重排。 | 前者無寫入；後者回可辨識衝突，開始日、既有調整與班表均維持，不能只取消結果或只改日期。 |
| 合併後採協調模式，當日同一月嫂另有其他案件班次，沒有已知全日不可服務。 | 保存日期並辨認仍需協調的占用。 | 儲存合併結果並查看日曆。 | 不因本功能未填上下班時間而拒絕，顯示跨案日期重疊提醒，不捏造時段或判為全天禁排。 |

### 3.5 確定性加鎖順序、Durable Job 與 `SCHEDULE` 異常矩陣

- **統一六層鎖順序**（所有 Scheduling command 共用，禁止局部重訂或半途加鎖；若 fresh 重算發現新增未鎖定月嫂直接回 `scheduling_lock_set_stale` 整筆回滾）：
  1. Case / Scheduling aggregate
  2. 所有受影響 `staff` mutex rows（去重後依 `staff_id` 升冪）
  3. Replay batch header / children
  4. Effective generation 與 assignments（`assignment_id` 升冪）
  5. Schedules / waiting locks / buffer facts（日期與 row id 排序）
  6. Payroll / Client Finance obligations（aggregate identity 排序）
- 複雜排班變更（如 `ApplyAssignmentPlan`、`ApplyLeaveSubstitutionBatch`）可回 `202 Accepted` 與工作識別。這只表示受理，不表示班表已生效。以工作識別查詢結果，取得成功收據並重新讀到同次正式班表，才算完成。若工作仍待處理或結果不明，不顯示已生效；若最終拒絕，依原錯誤判斷，班表不留部分寫入。背景工作仍在同一交易完成全部鎖定與提交。
- **異常決策矩陣（`SCHEDULE-002 / 003 / 006`）**：只以 `Preview/ApplyAssignmentPlan`（尚未有實際服務日時）或 `Preview/ApplyLeaveSubstitutionBatch`（已有實際服務日時）修復 lineage 斷裂、同月嫂重疊或日數總量違規；成功後於同交易寫入 `anomaly.recheck` intent 並在 fresh authoritative readback 後刪除異常。

### 3.6 Typed Commands、Ports、Errors 與 Writer Exit

- **Commands**：`QueryStaffAvailability`、`Preview/ApplyAssignmentPlan`、`Preview/ApplyLeaveSubstitutionBatch`、`Acquire/Release/Convert/CancelWaitingDepositLock`、`QueryCaseCalendar`。
- **輸入 Ports**：`OrdersTermsFactsPort`、`OrdersActualStartFactsPort`、`ClientDepositSettlementFactsPort`、`PayrollImpactCandidatePort`、`ClientFinanceImpactCandidatePort`、`BusinessClockPort`。
- **Stable Errors**：`invalid_scheduling_intent`、`case_not_found`、`staff_not_found`、`assignment_not_found`、`coverage_incomplete`、`service_ownership_conflict`、`staff_occupancy_conflict`、`waiting_lock_conflict`、`buffer_conflict`、`scheduling_generation_conflict`、`scheduling_lock_set_stale`、`stale_preview`、`batch_key_request_identity_conflict`、`invalid_batch_replay_snapshot`、`scheduling_data_integrity_violation`、`holiday_calendar_unavailable`、`idempotency_conflict`、`transaction_failed`。
- **Writer Exit**：僅 Scheduling adapters 可寫 effective assignment、`staff_schedule`、waiting lock、buffer 與 generation；`services/assignment_schedule_rest_date_service.py`、`caregiver_availability_lock_*`、`caregiver_matching_*`、`multi_caregiver_schedule_*`、`order_assignment_synchronization.py`、`payment_service.py`、`actual_hours_adjustment_confirmation_service.py` 與 `db_service.py` 均不得直接修改核心根事實。

## 4. 驗收標準

- 已簽約且定金已核銷的單月嫂成立案件可直接保存多人首份班表，原契約與定金核銷可查。服務中可調整後續班次，保留已服務日與其人員歸屬。完工未核銷案可修改人員、區段與日期，保留原完工事件與班表版本。部分已核銷案件可調整其他未核銷區段，保存後原核銷連結不變。
- 班次重疊、服務量不守恆或預覽所用來源版本變更時，確認回 typed conflict 或驗證錯誤且零寫入。一般單驗證原款未付、部分付款、已付及人工改額已確認的更正，排班與差額同交易生效，原核銷可追溯。驗證交易回滾、同鍵重播及追償防重。
- 既有人工分期分別驗證未核銷及部分已核銷。補證前可保存與回讀最新班表，舊應付原核銷可追溯，受影響的舊餘額暫停出款。補證預覽零寫入，確認後自備及補助分開計算，一來源的超付不抵銷其他來源待付。同鍵重送沿用原結果。

1. Unit／Subsystem 驗證 `SHIFT-01..05`（非重疊雙班、首尾相接、跨午夜歸屬、不可服務與 buffer 分離）、6 層升冪防死結鎖、`scheduling_lock_set_stale` 回滾、`batch_key` 重播／錯荷拒絕，及 Leave vs AutoComplete 競爭零部分寫入。
2. 管理員從原案件直接調整後續服務日的人員，記錄協調依據後，無入群證據也可預覽儲存。正式班表與應付結果一致。錯案、過期版本、服務量不守恆或檔期衝突時零寫入。
3. `SSTART-01..08` 驗證客戶／月嫂／工會各工作面按鈕與 `410` 舊確認阻擋；`handover-v1` 驗證群組單人邀請與真實入群證據。另驗證局部代班／換人不覆寫已服務日或全案開始日，及甘特圖唯讀 `historical_assignment` 並列顯示。

| ID | S：情境與前提 | T：人員任務 | A：操作 | R：可判定結果 |
|---|---|---|---|---|
| SSTART-CONFLICT-01 | 開工日期提案已成立，確認時月嫂有阻擋排班的檔期衝突 | 確認開工安排 | 由對方在原群組確認日期，再查正式日期、班表與帳務 | 回覆衝突原因，各正式事實維持原狀，不建立代班需求、待辦、意願詢問或邀請 |
| LEAVE-CONFLICT-01 | 延期提案預檢通過，客戶確認前檔期已變動而發生衝突 | 確認延期補班 | 客戶點選同意後，重新查詢正式班表與帳務 | 延期未生效並回覆衝突原因，原服務日與帳務保留，無代班待辦或代班待辦通知 |
| SSTART-LEAVE-01 | 開工或延期提案符合資格、版本及檔期條件 | 保存雙方同意的日期 | 由非提案方確認開工日，或由客戶同意延期，再讀回正式結果 | 各自沿既有單一交易完成正式排班與相關 owner 結果，不經代班待辦 |
| SCHEDULE-MANUAL-01 | 管理員有原案件排班權限，已與代班月嫂協調且有可用檔期 | 直接調整原案後續排班 | 開啟原案多月嫂排班，選定後續服務日與人員，填寫依據後預覽、確認並讀回 | 班表與帳務同交易生效，原日期換人維持約定服務量與全案開工日，無待辦識別或結案要求 |
| SCHEDULE-MANUAL-02 | 原案調班預覽後來源版本改變，或提交內容有錯案、服務量錯誤、檔期衝突 | 阻擋無效調班 | 分別提交各項不符條件的調整並重查正式結果 | 回可辨識 typed conflict 或驗證錯誤，原正式班表與帳務維持，無部分寫入或自動重送 |
