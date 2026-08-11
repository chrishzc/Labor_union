## 📌 更新摘要

本次更新整合 LINE canonical runtime 的登入、LIFF 身分綁定、未填表登記、人工審核、Rich Menu 發布與使用者選單切換流程，修正 legacy／canonical SSOT 漂移、過期 LIFF 入口、管理員 Session schema 錯誤、發布預覽衝突、Worker 延遲及 Rich Menu 未自動套用等問題。同時補齊 typed error、idempotency、outbox retry、worker wakeup、架構證據與分層回歸測試。

## 🆕 新增功能與檔案

- **Canonical LINE 未填表登記流程**
  - 新增 `api/dependencies/provisional_registration.py`，以 request-scoped dependency 組合 provisional registration application 與 MySQL connection。
  - 新增 `/line-registration` 與 `/api/v1/line/identity/registration/apply`，由 Server 驗證 LINE ID token，再以 typed intent 建立客戶、BeClass 暫存紀錄與確認訊息。
  - 新增 `tests/line/infrastructure/test_line_identity_api_routes.py`、`tests/line/infrastructure/test_line_liff_entrypoint.py`，驗證 registration API、LIFF additional information 格式及 canonical endpoint 邊界。

- **Rich Menu 使用者綁定與版本更新**
  - 新增 `subsystems/line/rich_menu_binding.py`，將 customer、staff、union staff 身分映射至各自 Rich Menu，透過 durable outbox 執行 LINE user link。
  - 身分綁定成功後自動套用該角色最新已發布 Rich Menu；新 Rich Menu 發布成功後，依 audience role 為全部既有 bound LINE identities 建立 publication-versioned rebind intents。
  - 新增 `tests/line/subsystems/test_line_rich_menu_binding.py`、`tests/line/subsystems/test_line_rich_menu_publication_snapshot.py` 與 `tests/line/infrastructure/test_line_outbox_intent_claim.py`，覆蓋冪等鍵、provider menu 固定、全員 fan-out、非重試錯誤及 canonical revision snapshot。

- **管理員登入與 Session 回歸測試**
  - 新增 `tests/test_admin_auth_runtime.py`，覆蓋缺少 `absolute_expires_at`、儲存服務異常、錯誤密碼、absolute deadline、開發略過權限及 Rich Menu typed conflict。

## 🔄 修改與優化檔案

- **管理員登入、安全與開發模式**
  - 登入前檢查 `admin_sessions` 必要欄位，將 schema 未完成與 MySQL 儲存異常轉成可辨識的 typed `503`，錯誤帳密回傳 typed `401`。
  - Session 維持 30 分鐘 idle renewal，但不得超過登入後 8 小時 absolute deadline；refresh、logout 與 request authentication 統一處理 storage error。
  - 開發模式略過登入仍可編輯與預覽，但移除真實 LINE Rich Menu 發布能力；管理中心 capability projection 改用 principal 實際 effective capabilities。

- **LIFF 身分入口與觸發文字**
  - 修正 LIFF URL 為 `https://liff.line.me/{LIFF_ID}/?...`，並在 `liff.init()` 後才讀取 flow context，避免 additional information 被 LINE Login callback 遺失。
  - 客戶綁定入口新增「已填寫表單」與「尚未填寫表單」前置選擇，未填寫者導向 canonical registration page。
  - registration page 移除 mock LINE user 與 legacy `/api/line/register`、`/api/line/config`，統一使用 ID token、runtime-config 與 canonical registration API；初始化失敗時停用表單並顯示明確訊息。
  - 補齊 `綁定訂單`、`我要綁定訂單`、`訂單查詢`、`綁定後台帳號` 等精確 identity command，避免一般「綁定」規則搶走後台帳號流程。

- **身分審核、資料衝突與訊息喚醒**
  - 月嫂、客戶與工會帳號審核將 owner drift、LINE 已被占用及 optimistic version conflict 轉成具體 typed error，不再只顯示泛用「資料已更新」。
  - 身分綁定、審核完成及 provisional registration 建立 delivery task 後，以 Redis best-effort wakeup 立即通知 Worker；Redis 不可用時保留 DB fallback。
  - provisional registration 確認訊息改用 canonical `LineDeliveryRequest` 與 delivery task repository，保留來源 aggregate、correlation ID 與穩定 idempotency key。

- **Rich Menu canonical 設定與可靠發布**
  - LINE 管理 UI 的讀取與儲存改走 `/api/v1/line/configurations/rich_menus`，以 DB revision、expected revision、reason、idempotency key 與 correlation ID 作為 canonical SSOT。
  - 發布預覽 receipt 改鎖定相同 DB configuration revision 與 menu fingerprint，區分未登入與 stale preview typed conflict。
  - 發布紀錄 UI 改支援 canonical publication status 與欄位，移除 legacy `is_current`、時間與錯誤欄位假設。
  - Rich Menu repository 可取得最新 published provider menu；publication worker 成功後在同交易 fan-out 所有符合 audience 的 bound identities。
  - `config/line_menu.json` 的訂單查詢按鈕改為傳送 `訂單查詢` 文字，並補齊可選 image asset 欄位，避免產生失效 LIFF 連結。

- **Outbox 與 Worker 執行流程**
  - canonical outbox claim 與 next-due 查詢改為依 intent type 分流，不再固定只處理 media archive。
  - completion command 新增 retryable 語意；不可重試的 provider rejection 第一次即可進入 dead，暫時性錯誤仍依上限退避重試。
  - canonical LINE worker 納入 Rich Menu binding worker，並把 binding intent 的 next due 納入動態喚醒時間。
  - 開發啟動器將 service monitor、LINE worker 與 Knowledge worker 改用 `python -m` module 入口，確保專案根目錄 import path 正確。

- **架構文件與證據**
  - 更新 LINE Access 正式規格，明定身分綁定與 Rich Menu 新版本發布的同交易 outbox、全員 fan-out、publication/user 冪等 identity 及不需重複綁定原則。
  - 更新 entrypoint review queue，納入 `/line-registration` 與 canonical registration apply endpoint 的 owner、caller 與 retirement evidence。

## 🧪 驗證結果

- LINE domain、subsystem、infrastructure 與 UI client 測試皆通過；完整 `tests/line` 為 `177 passed`。
- Rich Menu canonical configuration、preview、binding fan-out 與管理 UI 相關測試為 `32 passed`；新增重點回歸測試可在 `-W error` 下通過。
- 完整主測試集扣除既有 stale writer inventory manifest 與依 runtime mode 分流的 legacy characterization 後為 `1508 passed, 61 skipped`；legacy runtime characterization 另為 `8 passed`。
- FastAPI 與 Streamlit 本機健康檢查皆回傳 `200`；canonical LINE worker 已驗證可處理 publication、delivery 與 Rich Menu binding intents。
- 目前仍有既有 Starlette `httpx`／`httpx2` deprecation warning，與本次修改無關。

## 🗑️ 刪除/重新命名檔案

- 本次沒有刪除或重新命名 production 檔案。
