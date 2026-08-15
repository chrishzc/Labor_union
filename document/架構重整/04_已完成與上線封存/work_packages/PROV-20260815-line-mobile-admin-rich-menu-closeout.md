---
doc_type: work-package
declared_status: completed
date: 2026-08-15
owner: LINE Integration / Customer Service / Access Control
priority: P0
base_ref: main@538c836a
---

# PROV-20260815 LINE 手機管理與圖文選單收尾 Work Package

## 1. 場景與目的

工會已綁定的 LINE 人員，從圖文選單開啟 LIFF 手機管理頁後，必須能安全地處理客服回覆與月嫂身分審核；圖文選單的發布仍必須走既有 Rich Menu Preview／Apply、receipt 與 outbox。

本包收斂遠端合併帶入的手機管理、圖文選單與 staff self-service 程式，不重新實作既有 Customer Service、LINE Identity Review、Rich Menu publication 或 Access 根事實。

## 2. 已完成的合併漂移修復

遠端 commit `6506efb4` 重新加入的 `db/schema_parts/189_line_staff_self_service_identity_flow.sql` 與 canonical `191_line_staff_self_service_identity_flow.sql` bytes 完全相同。canonical release、descriptor 與 fresh-schema assembly 只引用 `191`；重複的 `189` 未分類，會使 schema assembly 與 preserve-data plan fail closed。

本次只移除未發布、未被 release 引用的 `189`。不修改 `191`、已發布 release manifest、descriptor、業務資料或任何資料庫。聚焦 static regression 必須維持通過。

## 3. Current SSOT 與不得退役的文件

- `17_External_Integration_LINE_Access正式規格.md`：LINE identity、Rich Menu publication／outbox 與 Access 邊界的 current SSOT。
- `20_LINE客服與月嫂自助服務正式規格.md`：工會選單、客服系統、月嫂驗證、staff self-service Query 與 LINE 請假入口的 current SSOT。
- `23_LINE身分管理與解除正式規格.md`：LINE 身分綁定／解除的 current SSOT。
- `88_LINE_Staff_Self_Service_Merge_Repair_Work_Package.md`：已完成且已封存，只作 historical evidence；不得復活或擴張為本包授權。

因此沒有 current formal spec 可退役。本包完成後可封存的是本包本身與其 closeout evidence，不是上述正式規格。

## 4. Scope

1. 保留已掛載的 `/line-mobile-admin` 與 `/api/v1/line/mobile-admin/*`，為八個 API／page entry 與 Streamlit「工會人員權限」頁補齊 entrypoint queue、業務情境、操作者、owner 與 focused regression。
2. 驗證 LIFF ID token、已綁定且 enabled 的工會人員、Customer Service reply 與 identity-review decision 均透過各自 owner workflow、版本、idempotency、receipt／outbox；Query 不得 commit 或產生業務寫入。
3. 將 remote rich-menu aliases、tab switch 與 LIFF target 收斂至 canonical configuration／Preview／Apply／publication worker；清除或退役任何直接讀取 legacy `line_users.role`、直接 enqueue 或繞過 identity-binding outbox 的路徑。
4. 將 `line_staff_self_service` 限為 verified staff 對自己已指派訂單／排班的 Query；不得擴張為 profile writer 或請假 mutation。
5. 維持既有 `191_line_staff_self_service_identity_flow.sql` release lineage，並驗證移除重複 `189` 後的 assembly／preserve-data read-only plan。

## 5. Access 裁決與實作原則

目前 `15`／`17` 的 approved policy 是所有 enabled internal users 擁有相同業務功能，不可由 role／capability 差異限制業務操作；remote mobile-admin route 卻以 `LineCapability` 依角色限制客服與身分審核。

依 current formal baseline 採第一項：mobile-admin 僅保留有效 LINE token、綁定且 enabled 的 internal user 與各 owner command 的既有驗證；移除 persisted role／capability 造成的差異 gate。Identity Review owning application 所需 scope 由此已驗證 human actor 固定提供，不代表角色授權。

## 6. Out of scope

- TOTP、帳號建立／停用、MFA enrollment、`LEGACY_SHARED_KEY` 退役。
- LINE provider 正式發布、實體帳號綁定或 production／shared-staging DB mutation。
- 新增 Staff profile writer、請假 request writer、直接變更排班、訂單、帳務或薪資。
- React 重寫；Streamlit 僅維持薄 client，未來可替換。

## 7. Write set（核准後才生效）

- `api/routes/line_mobile_admin.py`、`line/static/mobile_admin.html`、`api/main.py`。
- `config/line_menu.json`、Rich Menu publication／binding、LINE bot legacy exit paths。
- entrypoint review queue、正式 LINE／Access 規格的必要 amendment、focused route／page／publication tests 與 evidence。
- 已完成的 repository-only drift 修復：刪除 `db/schema_parts/189_line_staff_self_service_identity_flow.sql`；不新增或修改 migration release artifact。

## 8. Acceptance

- mobile-admin 的未驗證、未綁定、disabled、stale version、replay／payload conflict 與 owner rejection 都有 typed result；成功回覆或審核只由 owner committed workflow 產生 receipt／outbox。
- 所有 mobile-admin API、page、Streamlit page 與 staff self-service entries 都在 entrypoint queue 有精確裁決，validator 通過。
- generated Rich Menu image、alias switch、LIFF target 與 publication receipt 的 focused regression 通過；實際 provider publish 另需明確授權。
- 不存在 `189`，release chain／descriptor／fresh assembly 唯一引用 `191`；schema assembly、preserve-data plan contract 與 LINE staff self-service schema tests 通過。
- 所有 current formal specs 保留 active；本包若完成，依 archive gate 封存本包及 receipt。

## 9. DB gate（僅限本次重複 artifact 移除）

| Gate | 狀態 | 證據／限制 |
|---|---|---|
| Scope | PASS | 使用者明確要求處理合併漂移；只刪除未發布的 duplicate artifact。 |
| Change inventory | PASS | repository-only cleanup；無 schema SQL 內容、seed、backfill 或 production row effect。 |
| Static release | PASS | canonical release／descriptor／assembly 維持只引用 `191`。 |
| Descriptor | PASS | `191` descriptor 未修改。 |
| Read-only plan | PASS | `python -m scripts.update_local_database` 預覽只列既有 200／201，191 為 exact。 |
| Engine verification | NOT_RUN | 本次沒有要套用的 DB change。 |
| Developer acceptance | NOT_RUN | 未授權操作既有 `union_db`。 |

結論：對任何資料庫套用仍是 `DB_CHANGE_NOT_READY`；本包不要求也不授權 DB apply。

## 10. 下一切片：LINE 月嫂請假申請

本包完成後，依 `document/功能開發計畫/Scheduling_月嫂請假申請待辦與管理端處理開發計畫.md` 建立獨立 Scheduling Work Package。LINE 是 verified staff 的 intake channel：提交請假日期與說明只建立 Scheduling-owned pending request／待辦；管理員受理後 deep-link 至既有 leave-substitution Preview，再由人工 Apply 及 canonical receipt 決定正式排班。不得由 LINE 或待辦直接改排班。

## 11. Completion evidence

- `document/架構重整/03_追蹤清單與證據/evidence/2026-08-15_line_mobile_admin_rich_menu_closeout_receipt.md`
- schema／entrypoint／LINE focused regression：`62 passed`。
- 實際 LINE provider publish 與 LIFF 實機驗收維持 `NOT_RUN`，因本包未取得外部 provider 執行授權。
