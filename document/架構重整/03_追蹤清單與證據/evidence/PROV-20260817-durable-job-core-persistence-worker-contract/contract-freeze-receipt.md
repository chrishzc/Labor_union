# Durable Job Core contract freeze receipt

- Equality：`command_type + command_version + canonical_payload + submitted_by`；correlation 只作觀測。
- Payload：object／string keys／finite JSON；UTF-8、sorted keys、compact separators、`allow_nan=False`；`1 != 1.0`。
- Key：`^[a-z0-9][a-z0-9._:-]{0,190}$`；uppercase 在 DB 前拒絕。
- Actor：`admin_user_id:<positive-id>` 或 approved lowercase `system:<owner>`；case-sensitive immutable identity。
- Replay：same key/same equality 回既有 job identity；type/version/payload/actor 或 collation mismatch 為 typed conflict。
- Reader：NULL、invalid JSON、wrong type、legacy fallback 全部 fail closed。
- Terminal：schema version 1 closed union；success 只保存 result reference；failure 只保存去敏 typed fields。
- Transactions：canonical repository 0 hidden commit/rollback；worker 分離 recovery、claim、terminal；heartbeat 獨立且在 terminal 後。
