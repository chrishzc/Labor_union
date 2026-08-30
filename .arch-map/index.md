# Labor Union Admin

## Responsibility
為工會地端行政系統提供 current architecture 導航：React 管理端與 LINE／檔案等入口經 FastAPI／typed adapters 進入 Subsystem Query／Preview／Apply workflow，由 Domain 擁有根事實與業務規則，Infrastructure 實作 MySQL／外部 provider ports；mutation 受 Global outer Unit of Work、receipt、outbox、idempotency 與 typed error 契約約束。

## Domains
- `orders` — 訂單條款與 lifecycle；path: `domains/orders/index.md`
- `scheduling` — assignment、服務日、檔期、請假／代班與 matching；path: `domains/scheduling/index.md`
- `payroll` — assignment-owned 薪資義務與調整；path: `domains/payroll/index.md`
- `client-finance` — 客戶應收、收款、退款／沖正、調整與核銷；path: `domains/client-finance/index.md`
- `staff-payables` — 月嫂應付、出款與退匯／沖正；path: `domains/staff-payables/index.md`
- `finance-import` — 銀行來源事實、分類與 owner delegation；path: `domains/finance-import/index.md`
- `government-subsidy` — 補助申請、核准、撥款、allocation 與 reversal；path: `domains/government-subsidy/index.md`
- `anomalies` — 異常 projection、告警與 owner-specific remediation routing；path: `domains/anomalies/index.md`
- `case-import` — BeClass／HCM intake、review 與 formal case bootstrap；path: `domains/case-import/index.md`
- `contract-signing` — 核准契約文件版本、簽回 evidence、external-signing session 與 final signed document lineage；path: `domains/contract-signing/index.md`
- `external-integration` — Access 與 LINE transport／identity／delivery boundaries；path: `domains/external-integration/index.md`

## Cross-domain relationships
- `scheduling -> orders` — Scheduling 以既有 case/order lifecycle 與服務日期邊界作為協調前提。
- `payroll -> scheduling` — Payroll 從 assignment／service ownership 建立薪資義務，不反向改寫排班根事實。
- `finance-import -> client-finance | staff-payables | government-subsidy` — 匯入只保存銀行來源與分類，正式業務變更委派給 owning Domain。
- `anomalies -> owning domains` — Anomalies 投影／追蹤 owner facts，不直接改寫 owner root；解除必須以 owner predicate 為準。
- `anomalies -> external-integration/access` — Anomalies central worker消費已提交的Access security-alert intent，注入Anomalies-owned `system_alerts` projection sink；Access不concrete-import Anomalies。
- `contract-signing -> scheduling | orders | client-finance | external-integration` — Contract Signing 擁有文件／簽回與簽署 session evidence；commitment／execution、Orders lifecycle、Finance roots 與 LINE binding／delivery 仍由各 owner 決定。
- `external-integration -> owning domains` — Access／LINE 只提供 actor、identity、webhook／delivery 等邊界，業務命令仍由 owning Subsystem／Domain 決定。
- `all mutation -> Global` — `shared_kernel/`、outer UoW、receipt/outbox/durable job 與 migration governance 提供跨域不變量。

## Navigation notes
本地圖是 current architecture routing evidence，不是產品需求 Authority、architecture compliance/completion claim 或 source/test 的替代品。正式語意先讀 `AGENTS.md`、`document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md` 與 owning spec，再用此圖縮小 source/test scope。`api/`、`ui_react/`、legacy `ui/`、`line/`、`infrastructure/`、`scripts/`、`db/` 是 adapters／runtime／release locations，不因資料夾存在而自動成為 Domain。`contract_integration`、`customer_service`、`knowledge_retrieval`、`staff`、`bootstrap`、`controlled_files`、`reporting`、`jobs` 等 current source 邊界尚未在第一版完整建模；需要時依 current spec/source scoped 擴張。不得以此地圖復活 legacy `system_map*`／`scripts_map.md` gate。
