---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-durable-job-caller-adoption-gap
date: 2026-08-17
owner: Global Durable Jobs Integration Owner
domain: Global / Jobs + bounded callers
---

# Durable Job Caller Adoption 缺口

Core no-hidden-commit port完成後，六個enqueue owner檔、八種command type仍須由各bounded owner逐一採用。
現有caller可能吞掉same-key/different-payload conflict、依賴repository hidden commit或把JobAccepted冒充Domain成功。

本缺口的execution graph固定如下；不得再以「逐caller另立」作為未指名的模糊後續：

1. `PROV-20260817-durable-job-core-persistence-worker-contract-work-package`：凍結canonical
   command equality、no-hidden-commit port與worker terminal contract。
2. `PROV-20260817-durable-job-caller-integration-bridge-work-package`：提供唯一的outer UoW／application
   composition；bounded caller不得直接取得MySQL concrete repository。
3. 六個enqueue owner依下列exact successor採用：
   - Assignment Plan：`PROV-20260817-durable-job-assignment-plan-caller-adoption-work-package`，
     command type `assignment_plan_apply`。
   - Finance Import：
     `PROV-20260817-react-admin-phase4a-finance-import-public-contract-hardening-work-package`，
     command types `finance_import_batch_apply`、`finance_import_correction_apply`、
     `finance_import_historical_reprocess_apply`。
   - Government Subsidy：
     `PROV-20260817-durable-job-government-subsidy-caller-adoption-work-package`，
     command type `government_subsidy_apply`（其bounded action union不得拆成新的Global command owner）。
   - Payroll Rebuild：`PROV-20260817-durable-job-payroll-rebuild-caller-adoption-work-package`，
     command type `payroll_rebuild_apply`。
   - Staff Payout：
     `PROV-20260817-react-admin-phase4b-staff-payout-public-contract-hardening-work-package`，
     command type `staff_payout_apply`。
   - Orders Auto Completion：
     `PROV-20260817-durable-job-orders-auto-completion-caller-adoption-work-package`，
     command type `orders_auto_completion_apply`。
4. 只有Core、Bridge與上述六個owner adoption均PASS，
   `PROV-20260817-durable-job-public-outcome-contract-work-package`才可啟動masked public observation。

各successor仍須取得自己的exact人工核准；本gap只記錄依賴與責任分配，不構成production授權。
任一caller發現需要DB schema／migration／seed／backfill時，固定停止並另立DB scope，不得擴張上述包。

DB Gate：Scope `BLOCKED`；Change Inventory `PASS`（目前0 DB）；其餘`NOT_RUN`。結論`DB_CHANGE_NOT_READY`。
