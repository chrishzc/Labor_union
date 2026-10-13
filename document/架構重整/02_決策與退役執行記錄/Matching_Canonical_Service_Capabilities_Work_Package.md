# 內建媒合條件共用名冊來源

狀態：completed；Owner：Scheduling matching-coordination。

本包是規格 24「2026-10-13 內建媒合條件共用名冊 canonical 來源」的 bounded change-control；不新增業務規則。人工 Authority 為「不接受不同步」及「服務方式，例如周休二日」。比較基準為 `4bf84332099e01dd0b7274f1446c0e0826b83391`；保留起始 dirty／untracked 成果。

| 規格要求／驗收 | 修改與既有機制 | 直接驗證 |
|---|---|---|
| MATCH-CAP-01／①②④ | Domain 純比對；availability adapter 讀 clients.service_type 與 staff_weekly_rest | 方式同義、方式衝突、總天數不影響結果 |
| MATCH-CAP-02／①②④ | 同一 read adapter 讀 staff_time_slots，不使用數字偏好副本 | 整數時數、四小時標準值、其他與含糊值 |
| MATCH-CAP-03／③④ | 重用 Staff canonical writer 及每次 fresh-read Query，正式分段不硬性篩除 | 保存→查詢、舊數字偏好不覆蓋、單選／合選、空白需求 |
| MATCH-CAP-04／⑤ | 保留 HTTP key／response schema；既有 checkbox 改名「服務方式」 | 既有 API／UI focused tests、diff check、architecture closure |

執行順序：更新同一 owning spec → Domain 比對與 read adapter／query → checkbox 與直接 regression → focused 驗證與 map projection／closure。

Write set：`domains/scheduling/staff_matching_preferences.py`、`infrastructure/mysql/segmented_availability_repository.py`、`subsystems/scheduling/segmented_availability_query.py`、`api/routes/caregiver_segment_availability.py` 的欄位說明、`ui_react/src/components/OrderCandidateQueryPanel.tsx`、其既有 focused tests、Scheduling matching-coordination 的 module／integration test roots、規格 24、本包與最小 map leaf 更新。

效果上限：本機程式／測試／文件修改，local development DB 僅唯讀驗證。不得改 Staff／Client writer、schema、migration、外部效果或既有 dirty 成果，不 stage／commit／push／deploy。

停止條件：規格要求及最低充分驗證通過。若服務方式無法辨識，依已定案未符合處理，不猜測／不回退舊數字偏好；驗證環境阻擋時如實記錄。回復只限本包新增 diff，不覆蓋使用者成果。

驗證：focused Python 40 passed、API 1 passed、React 7 passed；architecture closure passed。Local development DB read-only check passed：畫面期間有 6 筆可查詢案件，無條件候選總數 12，僅每日時數條件候選總數 6，服務方式及合併條件為 0，符合已保存的「週一至週五」與「休周日」差異。無 DB mutation、schema 變更或外部效果。

驗證過程排除：初次 Python API TestClient 在沙箱停滯、Vitest 檔案解析受沙箱限制，改用正常本機權限後皆 passed；最初 DB probe 額外假設所有候選均登錄 8 小時而 failed，已移除該非需求假設，依每案已登錄時數正確篩選的原始 acceptance 重驗 passed。未改寫資料或放寬不相符結果。

Final scope／diff check：passed；只包含本包 write set，不覆蓋起始使用者成果。部署／外部通知：not_run（本包不包含）。

追加人工 Authority：使用者要求更新本機正在執行的服務，並實際在畫面確認兩項篩選。原有 localhost 8000／8001 API 已依精確程序身分重新啟動，兩者 health passed；5173 Vite 已讀取新版元件，舊 checkbox 文案不再存在，登入設定未變更。

Browser 驗收 passed：使用者完成既有管理員登入後，以實際案件與真實 API 操作。服務地區／下廚料理關閉，服務方式／每日時數四組結果為：皆關閉 2 位、只開時數 1 位、只開方式 0 位、兩者皆開 0 位；每次 HTTP 200 且 UI 候選數相符，已目視檢查勾選狀態及結果。方式 0 位符合保存的「週一至週五」與「休周日」差異，未修改任何業務資料、加入候選或發送通知。姓名遮蔽截圖及必要結果位於 ignored `scratch/matching-filter-runtime-20261013/`；驗證用 Chrome 獨立保留，不再因登入等候逾時關閉。Production deployment／external notification：not_run。

追加 Git Authority：使用者明確要求 `commit push`，允許提交本包修正、tests、spec 與 map，並推送目前 `main` 至既有 `origin`。此指示取代原執行期間的禁止 stage／commit／push；其他 dirty／untracked 成果及 ignored 瀏覽器設定檔／截圖不納入，不切 branch、不 force push。
