# Task 96 LDU 1012 engine qualification receipt

- `package_id`: `LDU-1003-CURRENT-01`
- `scope`: `1012_service_before_replacement.sql`
- `status`: `passed`
- `qualification`: `validation/receipts/PROV-20260828-local-additive-qualification-service-before-replacement.json`
- `payload_digest`: `fbe29795150a08ce2b9ffdcb9d92a1c6e7f21c5e3d320b18fca2b56647760a60`

1011 exact candidate作為source；代表資料`clients=1`、`orders=1`。MySQL將released descriptor中的
`NOT REGEXP` CHECK輸出為等價normalization，舊normalizer在statement 5後誤判drift；以fail-before-fix
regression限制為該released expression的等價投影後，從既有operation receipt的statement 18續跑，未重建
已完成objects。final verify、fresh bootstrap、strict evidence、qualification publish與validator round-trip均
PASS；canonical rows一致、`backfills=[]`。exact 1003 read-only plan已列出1004→1012完整順序。

1006～1012 engine chain為`passed`。本receipt產生當時，normal no-auth API／React／Browser為
`NOT_RUN`；後續`2026-08-28_task96_ldu_local_noauth_runtime_receipt.md`已取得macOS本機`passed`
evidence。另一台實體Windows開發機developer acceptance仍`NOT_RUN`，因此總結維持
`DB_CHANGE_NOT_READY`。
