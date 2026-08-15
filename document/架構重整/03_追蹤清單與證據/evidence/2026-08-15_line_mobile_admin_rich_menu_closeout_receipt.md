# LINE 手機管理與圖文選單收尾驗收收據

日期：2026-08-15
範圍：`PROV-20260815-line-mobile-admin-rich-menu-closeout`

## 完成結果

- 移除未發布且未被 canonical release 引用的重複 schema artifact `189_line_staff_self_service_identity_flow.sql`；唯一 release／descriptor／assembly artifact 為 `191_line_staff_self_service_identity_flow.sql`。
- mobile-admin 僅接受有效 LIFF ID token、bound 且 enabled 的 internal user；不再依 persisted role／capability 造成客服或身分審核業務功能差異。
- mobile-admin read path 不再呼叫 Unit of Work commit；Customer Service reply 與 Line Identity Review decision 仍委派給 owning application，保留其版本、idempotency、receipt 與 outbox。
- `line-mobile-admin` 的 7 個 POST API、LIFF page 及 Streamlit 權限頁均已在 entrypoint review queue 登錄為 `active`，含 business scenario、operator 與 canonical owner。
- `20_LINE客服與月嫂自助服務正式規格.md` 已補列 mobile-admin current contract；17、20、23 皆維持 current SSOT，未退役。

## 驗證

| 檢查 | 結果 |
|---|---|
| schema assembly、init-db part、staff self-service release、preserve-data plan contract | PASS（41 passed） |
| mobile-admin／客服／entrypoint／legacy role retirement focused suite | PASS（62 passed） |
| `python -m scripts.update_local_database` 唯讀 plan | PASS；191 exact，未套用 DB 變更 |
| `git diff --check` | PASS |
| 實際 LINE provider publish／LIFF 實機 | NOT_RUN；不在本次授權範圍，不能視為已發布 |

## Restore triggers

- mobile-admin LIFF identity、客服回覆或 review command regression；
- Rich Menu publication／binding outbox incident；
- entrypoint governance 或 schema assembly regression。
