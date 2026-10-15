---
doc_type: work-package
declared_status: completed
owner: Scheduling / Orders / Client Finance presentation
updated_date: 2026-10-15
implementation_authorization: granted-by-user-2026-10-15
---

# 服務安排兩步與自動排班

Authority：使用者通過兩步預覽，明確授權接線與實際 Chrome 驗證；同回合補充簽約完成入口改至服務安排。
業務權威沿用 `01_Orders_Domain.md`、`02_Assignments_Scheduling_Domain.md` 的此次裁決及既有 canonical writers。

## 範圍與驗收

| 驗收 | 實作與證據邊界 |
|---|---|
| 日期表可先存，正式指派仍為空 | 既有 service-dates Q/P/A；兩步工作台與月曆 |
| 一份人工紀錄完成指定對象確認 | 人工 snapshot + recipient commands；未選對象維持待確認；不發 LINE |
| 全數確認且條件齊備自動建立一次班表 | typed discovery → existing assignment job → canonical Apply／owner readback |
| 條件未齊保留確認，付款或放行後自動續辦 | Finance deposit-skip Q/P/A；金額仍未付、reservation 不提前釋放 |
| 名冊更正開始日後原子更新各段班表並返回同案核對 | actual-start Q/P/A／receipt + roster dirty／unknown-outcome guard |
| 更換入口維持，導向推薦頁既有換人操作 | 相同 case／recommendation replacement open request；不重寫換人規則 |
| 不再要求人工完工，顯示 authoritative 完成時刻與自動狀態 | readonly Orders status Query、existing due dispatcher／canonical completion job |
| 簽約完成後接續服務安排 | ContractExternalSigningActions callback；收款 owner 入口仍存在 |

## 執行與效果上限

允許本機 source、focused tests/build 與已登入 Chrome 的 local UI 驗收。DB 驗收使用 localhost
development `union_db` 的指定合成案及既有 `lu_test_recommendation_ui_20261014_*` 合成案；所有業務
異動走正式 writer、保留 receipt 與前後回讀。隔離 worker 只處理列入驗收的 case，無 provider delivery。
不新增 schema、不做 production／deployment／Git 提交；不處理歷史簽回修復或重寫名冊換人流程。
歷史重啟的既定人員安排維持原 canonical 流程，不由缺少 matching lineage 的資料補造 normal snapshots。

必要 focused tests、build、Chrome UI、`git diff --check` 與 architecture closure 通過後即關閉。
暫存 probe、回讀與 screenshot 保留在 ignored `scratch/service-arrangement-preview-20261014/`，不新增永久 raw receipt。

## 2026-10-15 驗證結果

- PASS：前端 focused tests 155／155；Python focused tests 72／72；production build。
- PASS：`git diff --check`；architecture closure（無 error／warning）。
- PASS：已登入 Chrome 實際操作兩個隔離合成案；日期先保存時指派仍為空，逐一記錄確認後保留確認結果，
  訂金未付時阻擋，自人工放行後背景建立一次班表。訂金實收始終為 0，未補造付款紀錄。
- PASS：名冊尚無班表時只更正實際開始日，返回同案服務安排重新試算；已有班表時經既有 preview／apply
  同步更新開始日及整段排班，約定開始日維持原值。
- PASS：隔離案經正式日期更正流程改為已到期安排後，由既有 due dispatcher 與 completion handler
  自動完成。最終 Query 為 completed、完成時刻 `2026-09-05T17:00:00+08:00`，未操作人工完工。
- PASS：簽約完成仍顯示完成結果，按下一步才進入服務安排；換人入口開啟同案推薦頁既有換人區塊。
- PASS：桌面與 390px 手機畫面核對，手機無水平溢出。名冊原有 nullable 虛擬帳號 Query 事實同步至 DTO，
  合成案與既有缺值案件可正常開啟，不補造帳號。

使用者於 2026-10-15 明確授權啟動本機正常背景工作並驗證自動排班／到期完工；先前自動審核的範圍缺口
已由此授權解除。正常 worker 在 localhost `union_db` 啟動，認證 readiness 與持續 heartbeat 為 PASS；
既有合成案仍受檔期衝突保護，未強制排班。未啟動 LINE 寄送 worker，不涉及 production。

停用隔離 API 的測試專用 worker 後，以同一個 `scripts/run_durable_job_worker.py` 與正常 private cycle
驗證 `RECOMMEND-UI-MOBILE-FULL`：Chrome 完成日期／雙方確認／契約測試簽回／檔期保留／人工放行，
Query 由 ready、0 指派變為一筆成功 assignment job。再從實際 UI 正式更正開始日及班表至 2026-09-08～12，
due discovery 找到 `2026-09-12T17:00:00+08:00`，正常 completion job 成功且 owner／UI 回讀 completed。
兩個 job 均一次成功；重跑 cycle 沒有增加 assignment／completion job，實收訂金仍為 0。
本輪日常 Chrome 控制連線逾時，改以已安裝 Chrome 的隔離工作階段操作真實 HTTP API；不測試正式登入權限。

## UI 預覽一致性修正

前一輪功能接線雖通過，畫面仍沿用過多既有表單與版本摘要，未符合已核准預覽；已重新對照兩個步驟。
日期設定恢復左右配置、原有服務方式標示、橫向日期摘要、簡潔月曆與右側主要按鈕；例行試算／版本明細
收為次要檢視，錯誤與結果未明的復原操作仍可見。生效後以 owner 現行日期唯讀呈現，只經原開始日更正
流程調整；不再編輯舊確認表。確認頁恢復對象卡、確認人數、狀態提示與條件格；未知條件標為待核對，
不以缺少 blocker 推定通過。確認紀錄與指派明細保留為次要檢視。

- PASS：最後受影響四個前端測試檔 35／35（包含現行班表唯讀／更正入口回歸）；production build。
- PASS：正常 cycle 實際排班與完工、重跑無重複 job、owner 狀態回讀；原 Python focused 72 項未因 UI 修正重跑。
- PASS：桌面日期設定、現行日期、確認頁與手機畫面實際核對；390px 無水平溢出。
- 畫面一致性修正當時，既有 `RECOMMEND-UI-DESKTOP` 合成案只作唯讀檢查；後續直接儲存驗收的正式 writer 異動如下節。
- 最後畫面及本機正常／隔離執行前後證據留在同一 ignored scratch 目錄。

## 日期直接儲存與下一步（同日後續裁決）

使用者要求將「無固定週休」放到星期列右側、移除日期預覽操作，並把下方重複開始日表單縮成上方
日期欄位下的一個保存按鈕。儲存完整日期表正式回讀成功後自動進入「確認排班」；單獨保存開始日
維持原步驟，保留待完成日期表的狀態。未改後端 API 或 root writer；預覽檢查在一次保存操作內完成，
結果未明沿用原操作身分及原保存意圖，不能將開始日單獨保存復原擅自變成日期表寫入。

- PASS：受影響日期／工作台測試 32／32，含重複點擊、開始日單獨保存與未知結果復原、日期版本衝突、
  回讀成功後導向確認排班；production build。
- PASS：隔離 Chrome 操作真實 API，`RECOMMEND-UI-DESKTOP` 單獨保存實際開始日為 2026-11-17 後，
  order version 4→5、日期版本仍為 null，停留設定步驟。再一次點擊保存服務日期，日期版本 null→1、
  日期為 2026-11-17～21，自動切到確認排班；原約定開始日 2026-11-16 不變，指派仍為 0。
- PASS：桌面量測無固定週休按鈕與最後一個星期選項同列；無預覽按鈕、無下方重複開始日表單；
  390px 無水平溢出。證據為同一 scratch 目錄的 `direct-save-chrome-evidence.json` 及 35～37 號實際畫面。
