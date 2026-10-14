# 客戶名冊合併與照護編輯

狀態：completed
Authority：2026-10-13 本 chat 使用者授權開始實作；最新澄清三節只記錄獎金文字、樓層費人員輸入總額。
規格：`../01_規格基線/33_案件與月嫂整合名冊正式規格.md` §5「客戶名冊合併與照護資料編輯」CR-1–5／AC-CR-1–4。
spec_route：SPEC_READY；convergence：READY，blockers：[]。

## 執行範圍

單一 Agent 修改本機 code／formal spec／Arch Map，執行 focused tests、build 及 Browser 驗證。
不 stage／commit／push／deploy，不修改 production 或 provider，不進行 migration、reset 或刪除既有 dirty 成果。
沿用 Client Profile／BeClass／Orders writer；BeClass correction JSON 已能保存 named scalar，本次不新增資料表。

## Coverage 與順序

| requirement／acceptance | current source／reuse | work | verification |
|---|---|---|---|
| CR-1–2／AC-CR-1 | ClientRosterPage、ClientRegistryPage、Drawer | 合併清單、抽出案件編輯區、保留深連結 | registry／roster focused UI、build、Browser |
| CR-3／AC-CR-2 | BeClass correction Domain／workflow／repository、registry typed Query | 擴充 scalar 欄位與 effective readback | correction unit、registry contract、HTTP、disposable MySQL |
| CR-4／AC-CR-3 | Orders Terms、BeClass financial sync | 三節／樓層文字修正；保留既有樓層金額與胎數流程 | 文字修正不金融同步、胎數與 Orders focused regression |
| CR-5／AC-CR-2、4 | Drawer closeDisabled、owner version、idempotency | 草稿保持、舊預覽失效、保存／回讀状态、延遲回應防護 | UI race／recovery regression、Browser |

## 失敗與停止

validation／stale／binding conflict 保留草稿並提示，Apply 不假成功、不盲重送。
原始資料、付款與歷史 events 保持 immutable；缺金融 root 沿用既有規則。
任何與最新 Authority 不符的正式金額、root ownership 或 schema 需求回到同份規格收斂。
驗收通過即停止；只保存最小 aggregate 完成狀態於本檔，工具 logs／畫面暫存放 scratch。

## 驗證結果

- Static：passed；production build、strict TS、`git diff --check`。僅有既有大型 bundle 提示。
- Module／Subsystem：passed；72 個 focused React cases、61 個 Python owner／query cases；Python 停用与本案無關的自動載入 pytest plugins。
- Engine：passed；5 個 HTTP／disposable MySQL cases。唯一開發測試庫 `lu_test_drawer_20261013_69b14d02_registry`；原始保存字串 before／after 不變、有效 scalar 回讀、NULL、同 key replay、stale 409、後續 bootstrap／胎數同步均通過。未修改 `union_db`、production 或 provider。
- Browser：passed；1875×1000 與 390×844。實際畫面確認主檔／照護／訂單條件、手機輸入框寬度、保存／草稿保持、樓層費未保存關閉確認、Enter／Escape 與焦點回復；合成 API fixtures，不使用真實 session。畫面與最小結果在 ignored `scratch/client-registry-drawer/`，供本次交付查看。
- Architecture closure：passed；以任務起點 `f67aff0aa32af4d566755e9209cebd2d120c3d37` 驗 source／test ownership，errors／warnings 為空。新增 Case Import named projection claim 與 Drawer consumer，未建立新 owner 或第二個 writer。
- AC-CR-1–4：passed。full suite／deployment：not_run，無此任務需求／授權。

完成邊界：保留所有既有 dirty／untracked 成果，branch／HEAD 未切換，沒有 stage／commit／push。獎金只保存協調文字；樓層費及胎數保留既有正式計費流程。

## 服務月嫂與抽屜換人（2026-10-13 後續裁決，completed）

Authority：使用者要求加入服務月嫂並能修改，明確選擇沿用既有正式換人流程、在抽屜內操作。對應 Spec 33 CR-7／AC-CR-5；Scheduling spec 的服務前 successor／已服務代班分流保持有效。

- 服務月嫂顯示 Scheduling effective assignments 的每段人員、期間、正式天數，Staff bounded Query 補姓名及公會編號；查詢失敗不推定未指派，舊案件晚回應不污染新案件。
- 重用 ServiceBeforeReplacementActions 的 Query／Preview／確認／Apply，草稿、送出／回讀中及結果未明回報外層關閉保護；未知結果只沿用原 payload／idempotency identity 對帳。完成後重讀案件／指派／歷程，其他區草稿保留。歷程唯讀追加既有 Scheduling 更換主事件，無新 writer、schema、計費或通知流程。
- PASS：77 個 focused React cases（含正式換人與 Drawer accessibility）；33 個 registry Python contract cases；修正測試型別後 35 個受影響 React cases 再次通過；production build；既有 disposable localhost MySQL 換人歷程 Query（唯讀）；1875×1000／390×844 Browser 合成資料顯示、換人表單、草稿關閉確認與無橫向溢出；Architecture closure（base `b0beaf33f806a67040945f4c2aa4cf1fe9b6bd5b`，無 errors／warnings）；`git diff --check`。
- 實際案件換人、provider、deployment：NOT_RUN。Browser 不送真實 mutation；MySQL 檢查不寫入資料。保留其他工作中的 dirty 成果，未切 branch 或提交。

## 服務月嫂位置與接任選擇修正（2026-10-13，completed）

Authority：使用者要求服務月嫂移到變更歷程正上方，並補上真正的人選操作；沿用先前已確認的正式換人規則。對應 CR-7 後續介面與分流修正。

- 服務月嫂為 Drawer 倒數第二區；正式指派的換人以明確 R-04 操作起始，不要求使用者挑選不相符的候選階段。完成登記後自動接上三步：查詢／勾選與保存候選、接案意願、選定推薦與客戶確認；重用原有 typed clients、idempotency／receipt／fresh readback。畫面不將推薦或換人登記冒充正式指派。
- 接任三步維持各自草稿及未知結果，保存候選／意願後更新推薦清單；候選意願結果未明時，即使清單重讀失敗，外層關閉仍鎖定。正式契約、日期確認與排班 gate 不旁路。
- Scheduling loader 在已有正式服務 proof 時不讀無關的舊 Matching reuse snapshot；未服務案件仍驗證完整 Matching sources。截圖案件 `115000998` 的本機正式 Query／HTTP GET 唯讀驗證為 10 個已服務日及 `substitution_referral`，未改資料。
- PASS：110 個 unique focused React cases（含抽屜、推薦、候選與鍵盤回歸），42 個 Scheduling API／loader cases；production build；桌面 1875×1000／手機 390×844 的合成 Browser 實際保存候選、意願、接任推薦與客戶接受，且驗證服務月嫂緊鄰歷程、手機無橫向溢出；Architecture closure（base `5bd260f84dde8561614492cf842e5aa9f61a1111`，無 errors／warnings）；`git diff --check`。
- 真實 mutation／provider／deployment：NOT_RUN。Browser 寫入僅存在合成 handler 記憶體；本機真實案件只讀。保留所有其他 dirty 成果，未 stage／commit／push 或切 branch。
