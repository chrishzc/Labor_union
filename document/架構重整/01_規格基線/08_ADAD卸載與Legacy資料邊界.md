# ADAD 卸載與 Legacy 資料邊界

## 1. 卸載決策

本專案自 2026-08-02 起不再使用 ADAD 套件、Task、Checkpoint、Source Lock、
system map gate 或 pre-commit gate 進行開發。

後續開發依根目錄 `AGENTS.md` 執行：

1. 先完成並由人工確認 `Global → Domain → Subsystem → Module` 整體架構與 SSOT。
2. 架構確認後，才撰寫 production code 與分層 pytest。
3. 所有程式修改必須逐條完成 Clean Code Rule 1～5 自我檢查。

## 2. 已解除的執行綁定

- 移除 `.agents/skills/adad-workflow`。
- 移除指向 `adad_pre_commit.py` 的 active 與 backup Git hooks。
- 移除 ADAD Task snapshot migration script、test 與 system map schema。
- 根層 Agent 規範與 PR checklist 不再引用 ADAD gate。

## 3. 歷史紀錄保存

未受 Git 保護的 Task、Source Lock 與舊快照已移至：

```text
history/adad/
├── tasks/
└── task_snapshot_archives/
```

`history/adad/` 僅供必要時人工查閱，不是現行規格、SSOT、授權或自動化輸入。
該目錄由 Git 忽略，不得由 production code、測試、hook 或 Agent workflow 載入。

## 4. Legacy system maps

下列 dirty tracked files 含既有未提交成果的 provenance，本次不刪除：

- `system_map.md`
- `system_map.yaml`
- `api/api_system_map.md`
- `api/api_system_map.yaml`
- `services/services_system_map.md`
- `services/services_system_map.yaml`
- `ui/ui_system_map.md`
- `ui/ui_system_map.yaml`

它們自卸載日起只供歷史比對，不是業務規格 SSOT，也不授權或阻擋任何修改。
在重要契約完整搬入一般架構文件並完成人工核對前，不得因「清理 ADAD」直接刪除。

## 5. Legacy 契約搬移狀態

已完成：

- Finance Import／canonical bank facts：`09_Finance_Import_Domain.md`。
- preserve-data migration／candidate DB cutover：
  `10_Global_保留資料Migration與Cutover_Subsystem.md`。
- 逐 canonical row 的 `finance_import_manual_review`、修正並原子入帳，以及
  `IMPORT-006` 匯入完整性聚合、刷新、敏感資料與 Anomalies ownership：
  `09_Finance_Import_Domain.md` 及 `06_Anomalies_Domain.md`。

已在一般架構文件補齊：

- Scheduling 的 mutex ordering、batch replay 與鎖後重驗：
  `02_Assignments_Scheduling_Domain.md`。
- Orders 服務時間三欄、deposit receipt／reversal 與 actual-start reconfirm 綁定：
  `01_Orders_Domain.md` 及 `07_跨Domain交易與pytest驗收架構.md`。

以上內容必須從規格、live code、schema、writer、caller 與測試重新核對後寫入一般架構文件；
不得直接把 legacy system map 的生命週期狀態或舊提案搬成新 SSOT。
