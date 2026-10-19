# NAS 網頁首次設定版 r2

映像：`chris23144638/cecec:nas-websetup-r2-20261016`，平台 linux/amd64。

這次只調整已確認的項目：移除首次建帳啟用碼、固定管理網址必填、NAS 特有的 16 字元最低密碼及 API 固定 8 並行限制。首次用網頁填帳號、顯示名稱、密碼及確認密碼即可建立 root；密碼沿用原專案最低 10 字元規則。

保留登入／MFA、資料庫 TLS、資料持久化、CPU／記憶體上限、原 Chromium PDF、匯入與既有背景工作程式。沒有替換 PDF 技術，也沒有新增背景工作框架。

## 本次部署範圍

使用者已確認 NAS 支援 HTTPS，並決定先保留目前 HTTPS 限制。網站憑證、專案 HTTPS 入口與 DSM 反向代理仍待確認，本次不修改這些項目，也不改用 HTTP。

因此本包可以完成容器啟動；NAS 上的網頁建帳與功能測試，要等專案 HTTPS 入口接妥後才執行。DSM 管理介面本身支援 HTTPS，不代表專案已可從該網址開啟。

Compose 保留現有網路方式：不發布 API、MySQL 或 Redis 的主機連接埠。沒有預設 18443，也沒有要求填 NAS_SETUP_KEY 或 NAS_PUBLIC_ORIGIN。既有來源 IP 限制仍須由 NAS 部署設定完成及實測；映像不會自動設定 NAS 防火牆。

## Container Manager 操作

1. 在電腦上傳映像至自己的 Private Docker Hub：`docker push chris23144638/cecec:nas-websetup-r2-20261016`。此交付沒有代為上傳或部署 NAS。
2. NAS 下載上述標籤。這是程式映像，不需要解壓縮。
3. Container Manager → 專案 → 建立；專案名稱使用 `lu-nas-websetup`，選定專案資料夾，來源選「建立 compose.yaml」，把本包 `docker-compose.yml` 的全文貼到編輯區。這份設定沒有需要手動填寫的啟用碼或網址。
4. 確認舊測試專案沒有同時執行，再完成及啟動。初始化服務完成後退出 0，db、redis、api 應健康。不要同時啟動兩個共用相同資料卷的主專案。
5. 本輪先停在容器健康狀態。專案 HTTPS 入口確認後，再以該入口開啟 `/admin/`；沒有 root 時會自動進入建帳畫面。

若是更新前版，保留原 `lu-nas-websetup-*` 資料卷，只更新相同主專案的設定與映像。r2 沿用原初始化格式，不重建或重設 root、MFA、密碼與資料。原來更早的 `lu-nas-preview-*` 測試卷不自動搬移。不要用刪除資料卷來排除啟動問題。

## 網頁建立 root

只填登入帳號、顯示名稱、密碼及確認密碼，不需要啟用碼。伺服器仍要求 HTTPS，且提交來源須與目前開啟的網站一致；這項檢查由請求網址取得，不需部署者預填固定網址。

建立成功後顯示「前往登入」。沿用原登入與 MFA，不自動登入或繞過驗證器。root 建立後關閉首次設定，重啟不重開；沒有新增密碼重設或 root 復原入口。

## 初始資源上限

| 容器 | CPU | 記憶體 |
|---|---:|---:|
| 一次性 initialize | 0.25 核 | 384 MiB |
| MySQL | 0.50 核 | 512 MiB |
| Redis | 0.10 核 | 64 MiB |
| API（包含前端） | 0.50 核 | 768 MiB |

API 維持一個程序，取消額外的 8 並行拒絕限制；這不代表無限排隊或不會逾時。CPU 限制可以讓處理變慢；記憶體不足仍可能 OOM。2 GB NAS 的實際承載能力須實測，不以本機結果保證。

## 保留的測試順序

1. 容器啟動、MySQL TLS 連線與初始化。記錄 DSM 記憶體及交換空間。
2. 專案 HTTPS 入口接妥後，網頁建立 root；確認再次建立被拒絕，停止／重啟後原帳號保留。
3. 登入、MFA、未登入存取拒絕與少量管理查詢。
4. PDF：使用原 Chromium 路徑產出一份 PDF，確認可開啟、頁面內容與版面。單純產生空白 PDF 不代表正式合約流程通過。
5. 匯入：使用合成測試檔走既有 Preview／Apply；確認結果與重新查詢一致，不連正式資料。
6. 其他背景工作：既有 `scripts.run_durable_job_worker`、`scripts.run_incident_worker`、`scripts.run_knowledge_worker` 程式保留於映像。依測項啟動所需 worker，沿用它們原有 Private API 認證；本輪未改這些認證，也沒有自動啟動會執行工作的 worker。須實際完成工作與確認產出；只排入佇列不能記 PASS。缺少所需設定時標 BLOCKED，未執行標 NOT_RUN，不宣稱所有功能已可用。
7. LINE Worker 最後：在 Container Manager 建立另一個手動專案，貼入 `line-check.yml`。此容器無網路、無資料卷，僅載入既有 Worker 並執行 `--help`，成功退出 0 代表程式與 CLI 可啟動。不要求 OIDC、不做認證握手、不進入工作循環或發送訊息；不等同 LINE 業務已可運作。

NAS 管理測試入口仍沿用前版停用 LINE API／Webhook／LIFF 的範圍，本輪沒有恢復這些入口。PDF、匯入與非 LINE 路由沒有因此移除。

## 資料與交付限制

- DB 密碼與 MFA 等金鑰由第一次啟動自動產生，不放在映像或交付包；API 降權執行，不掛入 DB root 密碼或 DB 伺服器私鑰。
- 保留目前自動產生的 90 天資料庫 TLS 憑證，沒有新增續期機制。此為資料庫憑證，與待確認的網站憑證不同。
- 本次以原已驗證程式映像 `labor-union-nas-test:local`（`sha256:94e262661523875abae4626b4e5131518d2bac7287cc8381bfba0837fbc07d70`）為基礎，只疊加這次 NAS 設定變更。這不是目前工作區其他進行中功能的重新建置。
- `bundle.json` 記錄建置來源；`verification.json` 分開列出 PASS／FAILED／BLOCKED／NOT_RUN。NAS、網站憑證／代理、真實匯入／背景工作與正式 PDF 流程，沒有執行就不列通過。
