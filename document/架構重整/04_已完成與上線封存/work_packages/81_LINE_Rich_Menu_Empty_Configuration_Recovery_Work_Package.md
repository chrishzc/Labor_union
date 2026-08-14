---
doc_type: work-package
declared_status: in-progress
date: 2026-08-13
owner: LINE Integration / Developer Experience
priority: P0
---

# 81 LINE Rich Menu Empty Configuration Recovery Work Package

## 人工核准與場景

2026-08-13 使用者明確授權修復：canonical DB 的 Rich Menu current revision 可能存在但 payload 為精確 `{}`，使 runtime 無法解析 `menus`；同時 legacy CLI 仍從本機 JSON 旁路發布。

## 範圍與不變量

- bootstrap 不得覆寫任何既有非空 DB revision。
- 只允許專用 operator command 對 `rich_menus` 的既有、精確 `{}` current revision 追加一個由 `config/line_menu.json` 驗證後產生的新 revision。
- 修復必須走既有 optimistic revision／idempotency／audit／outer UoW；不能 UPDATE 舊 revision、不能直接 SQL。
- current 缺失、非空 JSON、格式錯誤、種類錯誤或並發 stale 一律零寫入並可辨識。
- `line/setup_rich_menus.py` 不得再由檔案設定或 system actor 建立發布；保留名稱但 fail closed，明示 authenticated Preview／Apply replacement。
- 不會在本工作包呼叫 LINE provider、操作既有資料庫或變更 Rich Menu business policy。

## DB change inventory

| 分類 | 變更 | replay / rollback |
|---|---|---|
| schema-only | 無 | 不適用 |
| system-seed | 精確 `{}` 的 Rich Menu current revision 追加 canonical JSON revision | CAS/idempotency replay；append-only revision 保留 rollback evidence |
| business-row-backfill | 無 | 不適用 |
| destructive | 無 | 不適用 |

## 驗收

1. `{}` current revision 只追加一次合法 Rich Menu revision，並寫入 audit。
2. 非空設定與缺失設定不被 repair command 覆寫。
3. 缺少 `--apply` 時 command 零寫入；stale／idempotency conflict 維持 fail closed。
4. legacy CLI 不讀 JSON、不建立 publication，並導向 authenticated Preview／Apply。
5. focused unit／CLI contract regression 通過；任何實際 DB repair 仍由 operator 另行確認與保存 receipt。
