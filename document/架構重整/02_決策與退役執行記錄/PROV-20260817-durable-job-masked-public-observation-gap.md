---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-durable-job-masked-public-observation-gap
date: 2026-08-17
owner: Global Durable Jobs Integration Owner
domain: Global / Jobs
---

# Durable Job Masked Public Observation 缺口

現有public Jobs view仍可穿透raw receipt/error/payload，且尚未有按bounded command family限制的closed terminal
outcome contract。此缺口的唯一backend successor已定為
`PROV-20260817-durable-job-public-outcome-contract-work-package`；它不是Core owner，也不得反向修改
worker／repository／caller。

該successor只有在Core、Caller Integration Bridge與六個bounded caller adoption全部PASS後才可啟動，並只負責：

- masked、closed、versioned public observation schema；
- bounded command-family allowlist與typed terminal／non-terminal outcome；
- resource-safe Jobs dependency composition；
- 不把JobAccepted或provider acknowledgement顯示成Domain成功。

React client/page必須再後置於public outcome contract PASS；本gap與successor均不得直接授權React接raw
`receipt`、`error`或`payload` dict。

DB Gate：Scope `BLOCKED`；Change Inventory `PASS`（目前0 DB）；其餘`NOT_RUN`。結論`DB_CHANGE_NOT_READY`。
