---
doc_type: work-package
declared_status: completed
date: 2026-08-14
owner: LINE Integration / Global Migration
priority: P0
---

# 88 LINE Staff Self-Service Merge Repair Work Package

## 人工核准與場景

2026-08-14 使用者核准將 `upstream/main` 的 LINE 身分與月嫂自助功能合併到
`cloud_run`，並要求修復所有不符合正式規格的架構與 schema。遠端新增的
`staff_self_service` identity purpose 必須保留，但不得破壞 API-only DB runtime、durable
LINE delivery 或 preserve-data migration gate。

## Global → Domain → Subsystem → Module

- Global：MySQL 只由 FastAPI composition 存取；外部 LINE side effect 只消費已提交的
  delivery task；migration 只在隔離 candidate 套用。
- Domain：LINE Identity 擁有 `staff_self_service` purpose 與 verified binding 語意。
- Subsystem：Staff Self-Service 只查 verified staff 自己的 assignment／schedule；Service Help
  只建立 durable delivery task，不在 transaction 內呼叫 provider。未經正式規格核准的請假
  mutation 不進入 runtime。
- Module：Private API worker client 不持有 DB credential；schema part、release manifest、
  descriptor 與 validation artifact 共同描述 enum upgrade。既有 capability-grant 路徑以 410
  fail closed，所有已驗證且啟用的內部使用者維持相同 business access。

## Change inventory

| 分類 | 變更 | replay / rollback |
|---|---|---|
| schema-only | `line_identity_flows.flow_purpose` additive ENUM `staff_self_service` | exact 後重播不改資料；未知 drift fail closed |
| system-seed | 無 | 不適用 |
| business-row-backfill | 無 | 不適用 |
| destructive | 無；不移除既有 enum value 或 row | candidate 失敗即丟棄，source dump 保留 |

## Write set

- LINE identity／staff self-service merge paths。
- `scripts/run_line_worker.py` 與 API-side LINE composition boundary。
- `subsystems/line/service_help_application.py`、LINE messaging adapter。
- authentication effective-capability projection、capability-grant 退役路徑與 entry-point queue。
- 移除未核准的 staff leave mutation 與對應 UI。
- `db/schema_parts/191_line_staff_self_service_identity_flow.sql`。
- 對應 migration manifest、descriptor、validation release、tests、active index 與 evidence。

## Out of scope

- production database、shared staging 或正式 LINE provider mutation。
- Dockerfile、Cloud Run、IAM、VPN、network 或 production deployment。
- 將 reply token 直接保存在新 root fact，或在 DB transaction 內呼叫 LINE provider。

## Acceptance

1. merge conflict 全部消失，雙邊非衝突功能保留且無重複 migration identity。
2. Worker／Monitor 無 DB credential 或 MySQL concrete import。
3. Service Help 回覆只建立 committed durable delivery task。
4. canonical release chain 與唯讀 plan 包含 `191`；altered enum exact descriptor 可辨認 drift。
5. disposable MySQL fresh bootstrap 與 preserve-data candidate upgrade 通過，舊資料不變。
6. focused tests 與本機服務 smoke 通過；完整 non-integration regression 必須執行，且本次
   write set 不得留下失敗。既有且可由 merge 前 HEAD 重現的受保護 baseline drift 必須揭露，
   不得在本工作包擅自重產。
7. 已驗證且啟用的內部使用者不因 legacy role／persisted grant 產生 business access 差異；
   development bypass 仍禁止 LINE provider publication。
8. Runtime 不暴露未核准的 staff leave mutation，identity flow open 使用 caller-provided
   idempotency key。

## 完成證據

- `start_local_development.bat --dry-run`：`ready`。
- `start_local_development.bat --smoke-test`：API、Streamlit、Runtime Monitor、File Watcher、
  Durable／Incident／LINE Worker 全部啟動並由受控 smoke 清理，結果 `passed`。
- `scripts.update_local_database --require-current`：`union_db` 為
  `labor-union-line-staff-self-service-2026-08-14-v1` exact，未執行 schema mutation。
- focused architecture/runtime/schema regression：`68 passed`、`35 passed`、`15 passed`、
  `7 passed`；real MySQL preserve-data candidate：`1 passed`。
- 完整 non-integration：`1992 passed, 81 skipped, 17 deselected, 4 failed`；四項均為 merge 前
  HEAD 可重現的 BreezeSign legacy-name audit 或受保護 verification receipt digest drift，與本
  work package write set 無重疊。
