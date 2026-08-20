---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-react-admin-phase6c-final-streamlit-dependency-cleanup-gap
date: 2026-08-17
owner: Global Entry Point Governance / Runtime Integration Owner
domain: Global Runtime / Dependency Governance
source_gap: PROV-20260817-react-admin-phase6-streamlit-source-retirement-gap
---

# Phase 6C-F：最後 Streamlit dependency／runtime cleanup 缺口

## 0. 為何不能現在建立可執行刪除包

`streamlit`與`streamlit-cropper`仍被10個runtime entries、launcher/preflight/monitor/ngrok、migration rehearsal、
tests與rollback文件共同持有。最終exact write set只能在10個Phase6C per-entry retirement全部完成、Phase6A
validator PASS且Phase6B-HOST／Phase6B-RUN皆release核准後，由Integration Owner在最新base late-bind。

任何模型現在列出`ui/**`、`tests/**`或dependency lockfile的glob刪除，都不是合法Work Package。

## 1. Final successor必備inventory

- `pyproject.toml`與`uv.lock`中streamlit direct/transitive dependency與替代owner；
- launcher、preflight、smoke、monitor、ngrok、migration rehearsal每個caller的retain/replace/remove；
- `ui/app.py`、`ui/pages/**`、`ui/components/**`、`ui/api_clients/**`逐檔manifest；
- 每個Streamlit test的migrate_then_remove/remove/retain disposition與replacement test；
- current README/operations/deployment/entry queue與historical evidence分離；
- previous Streamlit artifact與rollback retention expiry／restore trigger。
- current／previous React artifacts各自的release identity、manifest digest、retention state、restore trigger、
  release-owner approval，以及final cleanup後由哪個runtime owner繼續保存previous React rollback artifact；
- final requirements revision、independent source-inventory revision及兩者producer，必須與Phase6A final-ready receipt一致。

## 2. Activation gates

1. 10個legacy identities與latest approved React registry revision治理完整；Phase5A的21筆只是minimum baseline，
   後續System Status／Form Management等核准identity amendment不得遺漏；10個legacy entries逐筆`removed`且有receipt。
2. `PAGE_REGISTRY`與所有dynamic callers為0，並由獨立manifest驗證，不只靠`rg`。
3. launcher/monitor/ngrok/rehearsal皆已由Phase6B-RUN接管approved React production runtime或有正式retain decision。
4. previous Streamlit artifact rollback retention期已結束並取得release owner批准。
5. Phase6A結果為`PHASE6_READY_FOR_FINAL_DEPENDENCY_CLEANUP`。
6. final requirements與source inventory revision一致且producer獨立；current/previous React artifact disposition
   已逐一裁決為retain/migrate_then_remove/remove，previous React rollback不得因Streamlit cleanup被順便刪除。

## 3. 禁止的虛假完成

- 只刪`pyproject.toml`依賴但保留caller；
- 以skip/xfail/刪測試讓suite綠；
- 修改歷史receipt以消除Streamlit字樣；
- 只搜尋static imports而忽略dynamic registry/launcher/subprocess；
- 把可開React首頁當作10個entry都已rollback-compatible；
- 在同一包同時刪source、切traffic並移除rollback artifact。

## 4. DB gate

本gap沒有DB變更；Scope `PASS`，其餘`NOT_RUN`，結論`DB_CHANGE_NOT_READY`。
