---
doc_type: gap-package
declared_status: proposed
identity: PROV-20260817-line-access-authorization-normalization-gap
date: 2026-08-17
owner: Access / LINE Architecture Owner
domain: Access / LINE / Knowledge
---

# LINE／Knowledge authorization normalization缺口

正式Access政策是所有enabled internal users具相同業務功能，唯一root只多Account Center；live LINE/Knowledge仍以role→capability
分流。React不得用選單顯示／隱藏掩蓋此live-drift。

人工需裁決並建立successor：正規化FastAPI dependencies與subsystem capability gate、保留actor/audit但移除業務角色差異；驗證
enabled/disabled/revoked、sole-root Account Center exception、所有LINE/Knowledge route matrix。此gap關閉前，新的LINE mutation WPs
不能宣稱production auth完成。0 production write set，0 DB。

DB Gate：Scope BLOCKED，其餘NOT_RUN；`DB_CHANGE_NOT_READY`。

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | BLOCKED | 正式policy與live dependency drift待人工successor |
| Change inventory | NOT_RUN | 0 DB |
| Static release gate | NOT_RUN | 無release |
| Descriptor gate | NOT_RUN | 無schema |
| Read-only plan gate | NOT_RUN | 不適用 |
| Engine verification gate | NOT_RUN | 不適用 |
| Developer acceptance gate | NOT_RUN | 不操作DB |
