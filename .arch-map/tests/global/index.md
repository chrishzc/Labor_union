kind: test-index
schema_version: 2
architecture: ../../index.md
test_root: tests/global/

# Ownership
`tests/global/` 僅收納同一 oracle 實際跨越多個 Domain／Subsystem 的系統行為；focused owner contract 仍回到最低 canonical owner root。

# Current routing
- Historical precision restart 到正常 Scheduling 與 weekly operations report 的完整 readback，由 Orders `historical-precision-restart` module 宣告為 higher-boundary integration root。
