# 追蹤清單與證據索引

盤點清單、候選清單與原始證據。這裡的文件**不構成規格授權**——多份文件本身
明文警告其 `status`／`disposition` 欄位只是起始提案，不能被當作可直接刪檔、
移除功能的授權依據，實際決策要看 `02_決策與退役執行記錄/`。

| 檔案 | 一句話摘要 |
|---|---|
| [模組正式位置對照表.md](模組正式位置對照表.md) | 舊 `services.*` 模組路徑 → 現在正式路徑（`domains`／`subsystems`／`infrastructure`）的查詢表，含已遷移、已退役無替代、仍在用未退役三類。 |
| [legacy_active_201_可追蹤清單.md](legacy_active_201_可追蹤清單.md) / [.csv](legacy_active_201_可追蹤清單.csv) | 201 筆依 path pattern 產生的 legacy finding 初步分類清單；status 欄不是執行授權。 |
| [過期文件候選清單_20260803.md](過期文件候選清單_20260803.md) | `document/文件整併工作區`、`document/架構重整` 範圍內可能過期文件的候選清單（第一版）。 |
| [31_可刪暫存清單.md](31_可刪暫存清單.md) | 可丟棄測試產物（MySQL test evidence／pytest basetemp 等）的盤點，同樣不授權直接刪除。 |
| [LINE_merge功能未移植_history_20260811.md](LINE_merge功能未移植_history_20260811.md) | 第一版刻意不移植的 merge legacy 行為，以及未來重新評估前必須補足的架構條件。 |
| [evidence/](evidence/) | 上述決策包／收據對應的原始 evidence 產物（JSON／SQL／receipt）。 |
