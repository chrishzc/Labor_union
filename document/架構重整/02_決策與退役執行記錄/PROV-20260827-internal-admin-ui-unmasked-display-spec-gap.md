---
doc_type: specification-gap
declared_status: proposed
date: 2026-08-27
owner: global-ux / access / domain-query-owners
authority_status: REQUIREMENT_APPROVED
priority: P3
---

# 工會內部管理 UI 完整值顯示規格缺口

## 1. 最新人工裁決

已通過權限驗證的工會內部人員，在管理 UI 執行日常業務時，所有畫面需要的一般業務資料不再做
遮蔽顯示。目標是防止外部攻擊者批量取得資料，不是防止具業務權限的工會人員查看工作所需資料。

本項優先度低，排在 Task 96 的 P0／P1 功能與異常閉環之後。需求 Authority 已確認；2026-08-31
最新人工裁決進一步固定：授權內部 UI 與 verified applicant 查看自己資料的 LIFF／自助 readback，
先直接顯示 owner typed Query 的完整一般業務值，遮罩功能延後到真實測試後另行裁決。既有 surface
仍須先完成 inventory 與 bounded package，不得直接做 repository-wide replace 或刪除安全測試。

## 2. Scope interpretation

### In scope

- React 工會內部管理端中，使用 enabled persisted-human session 且具該 owner Query permission 的頁面。
- 畫面實際需要的姓名、電話、地址、一般聯絡資料、案件／人員業務資料、帳務業務顯示值與其他
  canonical owner facts。
- Data Browser、Orders、Staff、Clients、Finance、Anomalies、Operations Reports、LINE internal admin、
  Account／Data Center 等內部 surface 的現有 masking inventory與逐包替換。

### Out of scope／仍須保護

- LINE 對客／群組訊息、公開頁、未登入或 disabled session，以及非本人或未通過 verified identity 的
  Client／Staff LIFF／自助 readback。verified applicant 查看自己的 bounded 資料屬完整值顯示範圍。
- credential、secret、MFA material、完整銀行驗證資料、raw provider payload、NAS／filesystem 實體 locator、
  raw request／exception／log／receipt／evidence與非業務必要 technical identity。
- 未具 owner permission 的跨域資料、任意整表 dump、client-selected fields、任意 SQL、無範圍 export或
  download。
- 以 UI 裁決改寫 Domain root、資料保留、稽核、外部 provider或 production deployment。

## 3. Security invariant

完整值顯示只改 presentation／typed Query view，不降低下列防線：

1. authentication、enabled root與owner-specific authorization；
2. server-owned field allowlist、stable filtering、cursor pagination與 bounded page size；
3. rate limit／bulk-export capability／download gate與可稽核 receipt；
4. cache key包含 actor permission scope，登出／權限改變時清除受保護 cache；
5. 401／403／stale／schema failure零資料穿透，前端不得保留前一使用者的完整值；
6. API、log、error、receipt與 evidence 仍遵守最小必要揭露。

## 4. Required inventory before task packaging

每個 surface 至少列出：route/page、API endpoint、owner、permission、current masked fields、target complete
fields、list/detail/copy/export/download行為、pagination、rate limit、cache、error boundary、現有 tests、write set
與 Chrome scenario。相同 API 被外部 LIFF／LINE 共用時必須拆成 permission-bound internal view，不得直接
解除共用 response 的 masking。

優先以互不重疊的 owner families 分包：

1. Orders／Clients／Staff directory；
2. Finance／Reports／Data Browser；
3. Anomalies／Data Center；
4. LINE internal administration；
5. Access／Account與 shared transport/cache regression。

共享 schema、API client、permission catalog、design tokens與 test fixtures 同一批次只有一位 integration
writer；其他 lane 只處理明確隔離 surface。

## 5. Acceptance

- enabled human＋正確 permission：畫面與 copy/export（若該功能另有 capability）顯示 canonical 完整值。
- 未登入、disabled、權限不足、跨 owner、過期 session：完整值零洩漏；late response不得覆蓋新 session。
- list仍 bounded、可續頁、可取消 stale request；不得新增全表一次載入。
- external LINE訊息與非本人LIFF／self-service contract維持recipient-specific資料最小化；verified applicant
  查看自己的bounded一般業務值時顯示完整值。
- raw secrets、storage locator、technical-only identifiers、log／receipt／evidence不得因本項出現在 UI。
- 每包完成 focused backend／React、authorization negative、TypeScript、build、strict UTF-8、diff check，最後
  使用真 FastAPI＋allowlisted `lu_test_*`＋enabled persisted-human Chrome逐頁驗收。

## 6. Current status

- Requirement：`approved`
- Specification inventory：`in-progress`（尚未逐 surface完成）
- Task pack：`NOT_READY`
- Production implementation／runtime／Browser：`NOT_RUN`
- DB change：預期 `none`；如 inventory發現需 schema或新的 permission root，必須另走 DB change gates。
