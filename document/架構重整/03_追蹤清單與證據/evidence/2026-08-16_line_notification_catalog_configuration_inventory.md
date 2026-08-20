---
doc_type: evidence-receipt
status: completed
date: 2026-08-16
scope: LINE Notification Catalog current configuration inventory
---

# LINE Notification Catalog 現行設定盤點收據

本收據僅記錄 `lu_test_dataset_contract_signing_v4` 的去敏 current revision 指紋，不含訊息文字、個資、token 或 provider 設定；不構成實體 LINE 發送驗收。

## 查詢結果

以 application database principal 查詢 `line_configuration_current`：

| Configuration kind | Current revision | definition SHA-256 |
|---|---:|---|
| `message_templates` | 1 | `f4a2f6cfa42a522ba4732f55547bc8f6ce3a7686aa2dc6b311d3f0fccfa569ca` |
| `message_schedules` | 2 | `ee7ebe619ec602821d45bd638212551eda7e92867d62908036c8157651d0993d` |
| `notification_rules` | none | — |

## 與 committed bootstrap 的比較與裁決

- `config/message_templates.json` 為身分綁定、客服與新好友引導範本；沒有可直接挪用為服務日寶寶日誌／餐食照片提醒的核准範本。
- `config/message_schedules.json` 只定義 `follow` 新好友三日引導；不承接 order 或 service-time event。
- 因 current configuration 尚無 `notification_rules` revision，Catalog 在沒有管理員經 API Preview／Save 啟用規則前必須 fail closed；不得建立 delivery task。
- 未來管理員必須先在既有 Template configuration 發布合適範本 revision，再以 Notification Rule API 引用該 revision；不以程式硬寫正式訊息。

## 可重現查詢

以 `.venv\Scripts\python.exe` 和 application connection 執行：

```sql
SELECT config_current.configuration_kind, config_current.revision_id,
       revision.definition_snapshot
FROM line_configuration_current AS config_current
JOIN line_configuration_revisions AS revision
  ON revision.id = config_current.revision_id
WHERE config_current.configuration_kind IN
  ('message_templates', 'message_schedules', 'notification_rules');
```

將 `definition_snapshot` 僅以 SHA-256 留存即可；不得把實際訊息內容帶入 receipt。
