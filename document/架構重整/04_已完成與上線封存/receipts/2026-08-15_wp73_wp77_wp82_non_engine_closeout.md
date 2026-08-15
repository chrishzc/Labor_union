---
doc_type: evidence-receipt
declared_status: completed
date: 2026-08-15
owner: Case Import / LINE Integration / Global Migration
scope: WP73, WP77, and WP82 non-engine closeout
---

# WP73 / WP77 / WP82 non-engine closeout handoff

## Purpose

This receipt records only completed non-engine work. It is not implementation completion,
archive authorization, deployment authorization, or a substitute for browser, provider, source-data,
or real MySQL evidence.

## WP73

- Completed non-engine scope: Case Import-owned workbook coordinator, authenticated multipart API,
  typed receipt, temporary-workbook cleanup, HCM import-center card, idempotency boundary, and
  privacy-safe focused evidence are documented in the Work Package and HCM upload receipt.
- Remaining engine/interactive gate: a valid HCM row must create its formal root in a controlled
  environment, and the actual Chrome extension path must be exercised.

## WP77

- Completed non-engine scope: Staff historical adoption and HCM review contracts, release successor,
  descriptor, focused evidence, and target-host operator handoff are recorded in the Work Package and
  its receipt.
- Remaining engine/data gate: complete Staff-source replay, valid HCM/Client ordering and
  reconciliation, plus final preserve-data verification from the supported prior schema.

## WP82

- Completed non-engine scope: `config/line_menu.json` defines LIFF `?target=registration`;
  `line/static/gateway.html` maps it to `/line-registration`; legacy service-registration text uses
  the long-lived LIFF fallback in `subsystems/line/service_help_application.py`.
- Completed operator/documentation scope: Docker MySQL client selection and the exact 185 recovery
  boundary exist in `scripts/update_local_database.py` and
  `scripts/migrate_preserved_database_additive_schema.py`; `.env.example`, `README.md`, and focused
  contract tests describe the portable container flow.
- Remaining engine/provider gate: authenticated Rich Menu Preview/Apply publication and a Docker
  MySQL partial source -> candidate -> exact recovery receipt. No LINE provider action was performed.

## Archive disposition

2026-08-15 使用者明確指示跳過所有列出的實機／provider／engine 驗收並封存 WP73、WP77 與 WP82。
本 receipt 因此隨三份 Work Package 移入 archive，僅證明非實機範圍與人工豁免；未執行的實機
驗收不得解讀為 PASS。後續若要啟用、重啟或修改任一能力，須先建立 successor Work Package，
並在受控環境完成相應的 browser、provider、source-data 或 MySQL evidence。
