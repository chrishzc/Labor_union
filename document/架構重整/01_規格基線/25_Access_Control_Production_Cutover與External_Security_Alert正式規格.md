# Access Control Production Cutover 與 External Security Alert 正式規格

## 1. 文件邊界與所有權

- 狀態：`proposed-spec`
- Owner：Access Control / Global Security
- 單一負責範圍：Access Control 的 production cutover 安全邊界、external security-alert outbox 後續契約與必要驗收順序。
- 關聯引用：見 [`Access_Control_Production_Cutover_and_External_Security_Alert_Work_Package.md`](../02_決策與退役執行記錄/Access_Control_Production_Cutover_and_External_Security_Alert_Work_Package.md)、[External Integration / Access Control](17_External_Integration_LINE_Access正式規格.md)、[Global Deployment 與治理](18_Global_Deployment與治理正式規格.md)

本文件只保存後續的正式收斂契約，不構成 deployment、production schema apply、Cloud IAM／OIDC 設定、外部通知 provider、secret 操作或任何 runtime cutover 授權。

## 2. 業務場景與不變量

本機已驗證的帳密、TOTP、root 帳號中心、Bearer-only human transport 及 durable security-alert outbox，不能替代真正 production target 的可用性與外部告警責任。production cutover 必須同時證明：

1. 有明確、已授權的 target、operator、時窗與 rollback owner；不得從 `.env`、本機 Docker database 或任意 host 名稱推論 production target。
2. human authentication 永遠不接受 shared key；local/test 的 machine-only `INTERNAL_SERVICE_SHARED_KEY` 與 production Google-signed OIDC 僅代表受 allowlist 約束的 machine caller，不得冒充 `AdminPrincipal`。
3. production 不允許 auth bypass；遺失 root 不建立 HTTP break-glass endpoint，而是走受控、可稽核的離線復原程序。
4. 依規格 17 保留的 security decision audit 與主交易原子保存。外部告警只能在 commit 後由 durable outbox 投影，sink 不可用不得偽造告警已送達，也不得回滾已提交的安全決策。
5. keyring、資料庫 migration、時鐘與至少兩位可用的人員 MFA 均有可驗證的 cutover evidence；不得在 Git、UI、receipt 或 log 保存 password、Bearer、TOTP seed、recovery code 或 keyring 原文。

## 3. 外部 Security Alert 後續契約

現有 outbox 已能將本機高風險 security decision 投影到既有系統告警。本規格保留 production 外部 security alert 的最小後續契約：

- 事件：production auth-bypass attempt、root offline-recovery attempt，以及 audit persistence rollback 的外部告警語意；後者必須有獨立、去敏的 failure evidence，不能把失敗的 Domain audit 假裝成已提交事件。
- 身分與關聯：事件必須帶穩定 event identity、correlation identity、occurred time、outcome 與去敏資源摘要；不得含 secret、TOTP／recovery code、密碼、Authorization、完整 IP 或個資。
- delivery：由 commit 後 worker bounded retry、保存 attempt outcome；retry exhausted 必須形成可查詢的 failed alert fact 與人工處理入口。
- external sink：provider、recipient、escalation、值班、保留期與可接受延遲尚待裁決；不得假定 email、LINE、Slack 或特定雲端服務。

## 4. 必要驗收與 cutover 順序

cutover 必須依序滿足下列驗收：

1. 明確 target／operator／window／rollback authorization 與唯讀 preflight。
2. fresh 與 preserve-data MySQL evidence，並在 target 前確認 canonical release、owned-object descriptor 與 no-drift baseline。
3. 真實 MySQL concurrent row-lock、stale-version 與 outbox partial-failure 驗收。
4. browser-level「帳號建立 → 本人 enrollment → MFA login → 跨頁 → logout」以及所有既有管理頁 Bearer-only、同權驗收；帳號中心另驗證 root-only。已登入 React 人員 request 若以目前 Bearer 收到 401，必須清除同一 token 並立即卸載受保護 shell、返回登入頁；晚到 401、未帶 token 的登入挑戰、403、network／5xx 與不同 service token 不得清除目前人員 Session。
5. keyring backup／restore rehearsal、clock synchronization、兩位人員 enrollment，以及 production profile 拒絕 bypass。
6. 只在維護窗內執行 deployment、schema release、登入與高權限 smoke；結果與 rollback evidence 必須寫入去敏 release receipt。

任何 preflight、schema descriptor、keyring、clock、MFA enrollment、external alert sink 或 rollback 責任不明，均為 fail closed：停止 cutover，不以重新啟用 shared key 或長期 MFA bypass 取代修復。

## 5. 非目標

- 不新增 role、capability 或業務功能的差異化授權。
- 不新增 production HTTP break-glass、直接外部 side effect 或把 provider credential 寫入 repository。
- 不把 developer-local database replacement、disposable MySQL 或 mock 宣稱為 production release。
