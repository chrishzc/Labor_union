---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase5-entry-navigation-switch-policy-gap
date: 2026-08-17
owner: Global Entry Point Governance / Integration Owner
priority: P0
source_plan: React管理端遷移與UI真實業務流程驗收計畫.md
---

# Phase 5：逐 entry navigation switch policy 缺口

## Current contradiction

主計畫要求「每次只切一個entry的navigation」，但現有十個Phase5 entry工作包只允許focused tests、queue、
manifest與evidence；沒有任何一包擁有可將單一entry從Streamlit導向React、並獨立切回的routing control。

Current runtime只有：

- Streamlit 8501單一shell，以session/sidebar載入10頁；
- React 5173／未來`/admin/`單一shell，以hash選11+ routes；
- Phase5A proposed `/?entry=<key>`只提供Streamlit rollback，不提供forward navigation switch；
- queue status是治理metadata，不是runtime router。

因此即使所有per-entry tests通過，也只能得到`entry-candidate`，不能宣稱navigation已cutover。

## Human decision required

需凍結唯一presentation routing owner與mechanism：

1. **Option A（推薦）— canonical admin entry map**：由application-owned、checked-in manifest記錄每個entry的
   `streamlit | react` presentation target；operator只可一次切一筆。Streamlit sidebar與production admin landing
   都讀同一server-validated projection；unknown/stale identity fail closed。Hash不作server routing key。
2. **Option B — Streamlit link-out only**：在legacy sidebar逐頁顯示React連結；實作較小，但無獨立default-route
   owner，也難證明new-tab/reload與production artifact selector一致。
3. **Option C — edge/reverse-proxy per-entry routing**：目前React使用hash，server不可見fragment；需要改URL
   contract與deployment topology，不應在Phase5頁面包臨時採用。

推薦Option A，但未經人工核准不構成正式裁決。

## Required successor contract

- manifest identity、revision、operator、one-entry CAS、audit、rollback target與observation window；
- Streamlit source與React replacement group的一對一／一對多映射；
- unauthenticated、TOTP、reload/new-tab、unknown/stale manifest與artifact unavailable行為；
- navigation切換不修改Domain data，不重用API idempotency key，不刪除source；
- local 5173與production `/admin/` URL由runtime profile提供，不能硬編host；
- queue disposition、runtime target與operator receipt必須一致，但queue generator不得自行切換runtime；
- 一次只允許一個entry revision變更，下一entry前必須完成觀測與rollback rehearsal。

## Prohibited shortcuts

- 把queue row改成replacement當作routing已切；
- 在各頁硬編5173或`/admin/#...`；
- 用React shell可手動點到所有頁冒充逐entry切換；
- 以hash fragment作FastAPI／proxy路由；
- 同一批切多個entry、刪Streamlit page或回滾Domain data。

## DB gate

本gap為public-entry policy，0 DB變更。Scope PASS、Change inventory PASS，其餘NOT_RUN；
`DB_CHANGE_NOT_READY`。
