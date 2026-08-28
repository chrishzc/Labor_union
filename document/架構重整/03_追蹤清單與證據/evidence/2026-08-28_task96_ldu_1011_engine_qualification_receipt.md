# Task 96 LDU 1011 engine qualification receipt

- `package_id`: `LDU-1003-CURRENT-01`
- `scope`: `1011_historical_baseline_projector.sql`
- `status`: `passed`
- `qualification`: `validation/receipts/PROV-20260828-local-additive-qualification-historical-baseline-projector.json`
- `payload_digest`: `efb571b242e9d24f6dee96080dc4e322419c9db48bfe87c000f6be12131fd333`

1010 exact candidate作為source；代表資料`clients=1`、`orders=1`。MySQL將`BETWEEN … AND …` CHECK
輸出為巢狀AND，舊normalizer誤判statement 4 drift；以fail-before-fix regression將AND／OR associative contract
攤平後，從既有operation receipt續跑，未重建已完成tables。final verify、fresh bootstrap、strict evidence、
qualification publish與validator round-trip均PASS；canonical rows一致、`backfills=[]`。1012與developer acceptance
仍`NOT_RUN`，總結維持`DB_CHANGE_NOT_READY`。
