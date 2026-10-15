# 客戶名冊單案虛擬帳號修改

Package：CLIENT-REGISTRY-VA-20261015；狀態：直接儲存與未簽客戶契約重新產生均已完成必要本機驗收，已關閉。
Owner／consumer：Client Finance 單案帳號 writer、客戶名冊 UI；完成下列驗收後關閉。
Authority：2026-10-15 使用者要求功能並選擇以新帳號取代本案全部舊匯入對照；最新明確要求「不用原因跟預覽功能」。
後續 Authority：已產生但還沒簽署的契約，修改虛擬帳號後也要能重新產生、帶入新帳號。文件端語意依規格 21，沿用既有入口與 UoW。
唯一規格：[Client Finance §8.1](../01_規格基線/04_Client_Finance_Domain.md#81-客戶名冊單案虛擬帳號修改2026-10-15-人工裁決)，SPEC_READY／convergence READY，無 blocker。
研究路由：NO_RESEARCH；使用現有 mapping schema、匯入互斥鎖、admin receipt、MySQL UoW 與名冊 Drawer。

| Requirement／Acceptance | 現行來源 | 必要步驟 | 直接 oracle |
|---|---|---|---|
| VA-01、02／A1、A2 | §8 格式與對照順位；人工裁決 | Domain 格式、Client Finance 單案 Query／Apply、既有 MySQL adapter | 無／單／多舊對照取代、他案保留、非法格式／不存在／占用拒絕 |
| VA-04、05／A2、A3 | Global 2.3、既有匯入鎖／receipt schema | fresh-lock、mapping IDs 集合版本、receipt 與一次 outer commit | stale、replay、異 actor／內容 conflict、receipt failure rollback |
| VA-03／A4 | 現有 virtual_account_resolution | 沿用 mapping 優先；名冊帳務顯示使用相同 resolver | 修改後契約／核銷 resolver 讀取新對照；內建帳號不變 |
| VA-06／A5 | 最新人工裁決、現有 ClientRegistryDetailEditor 關閉鎖 | typed client、帳號面板直接儲存、Drawer 組合與回讀 | 無原因／預覽的單次 Apply→readback；stale 重讀、unknown 同 key 核對與鎖定 |
| 未簽契約重新產生 | 最新人工裁決、規格 21 管理端契約下載 | 既有 client source writer 簽署檢查、既有 PDF prepare、UI 入口與新版回讀 | D36 舊／新版本帳號、來源不變重用、已簽拒絕零寫入、準備中／已交接新版下載 |

Write set：Client Finance 格式／單案 workflow、既有 legacy virtual account repository、其 API schema／dependency／route composition；
名冊帳務 projection、typed client 與帳號面板、ClientRegistryDetailEditor；相應 owner tests、兩個既有 Arch Map leaves、此 package 與 §8.1。
本次文件延伸只包含既有 client contract source application、external signing composition、ContractExternalSigningActions、對應既有測試與 owning map／規格；不新增 API、資料表或簽署流程。
舊交接的既有 client-inclusive hash 由原 repository 以同案／方案的保存客戶版本證明；不改寫 session hash，current 月嫂文件仍必須一致。
不改其他 dirty work、DB schema、歷史契約／流水、匯入 additive 語意或公式。依序完成後端／consumer、UI、focused 驗證與 map closure。
效果上限：本機 code／test／build；測試不得連 production 或 external provider，不執行真資料修改、部署、Git stage／commit／push。
停止：契約矛盾、需要 schema／外部效果或必要環境不可用時回報受影響 gate；不可用確認不宣稱通過。
回復：僅撤回本 package 自有 diff，保留 entry dirty paths；正式 runtime 修改靠同一 writer 新命令，不改歷史 receipt。
Evidence：測試與 build 結果於交付訊息；臨時畫面／結構輸出留 ignored scratch，無外部效果不另建永久 receipt。

直接儲存 revision 驗收：PASS — 後端 19 項、前端 71 項 focused／regression tests，覆蓋不填原因、不預覽的單次儲存、
mapping IDs stale、跨案占用、同 key 結果核對、receipt failure rollback 及名冊清單回讀鎖。
PASS — 桌面／手機合成資料瀏覽器操作與實際畫面、完整 `npm run build`、source TypeScript check、
本次範圍 diff／strict UTF-8 檢查與 architecture closure。建置僅有既有 bundle size 提示，不擴張拆包 scope。
真 MySQL lock scheduling／production migration／deployment／external provider：NOT_RUN；本次沒有 schema 或真資料異動。

未簽契約重新產生 revision：PASS — 後端 95 項與前端 42 項，共 137 項 focused／regression tests；
實際 XLSX D36 舊／新帳號、同來源重用、signed-received／外部回報／contract identity 拒絕、舊交接 hash 與月嫂版本衝突。
PASS — 完整前端建置、合成資料桌面／手機畫面與重新產生後兩次下載均為新 document ID、本次 diff／架構檢查。
未重新送交外部簽署平台或發送 LINE；舊檔保留，實際新版送簽屬操作人員後續流程。
