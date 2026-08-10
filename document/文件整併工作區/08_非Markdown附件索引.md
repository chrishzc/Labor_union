# 非 Markdown 附件索引

## 狀態

- 盤點日期：2026-08-10
- 範圍：`document/` 下所有非 `.md` 檔案
- 數量：18
- 已完成 path／type／bytes／SHA-256、架構分類與內容裁決；正式規格仍優先於附件內容。

## 分類

| 路徑 | Bytes | SHA-256 | 分類／處置 |
|---|---:|---|---|
| `document/LINE (1).pptx` | 2650667 | `2f1fbc7a15a784bcfcc4d2dc8b33817e854b8de0b85cf07a57d6983b2c9b683f` | `historical`；產品願景與舊技術提案，不形成 current contract |
| `document/月子媒合流程圖.canvas` | 11930 | `28823700dc461119aca174b59995a20fdb57c50f79efc6c35e24354f4f62225b` | `conflict`；固定 3／7／5 日訊息、自動取消、直接 DB 更新、私人管理員群與特定簽署商均由 typed Domain／Task／provider-neutral 決策取代 |
| `document/架構重整/03_追蹤清單與證據/legacy_active_201_可追蹤清單.csv` | 41183 | `53bad0676d25bf9375faec25687f2eb7cc43189e962aaa590ef8e6bd61ff709c` | `generated-live-evidence`；writer exit，不是業務 SSOT |
| `document/資料庫、資料處理/台新範例對帳單.xlsx` | 15132 | `3faef5ff29a153217e379707f69fcead5851a1b352d067eeb990fc73d00ad7f5` | `format-fixture`；Finance Import 真實格式驗收 |
| `document/資料庫、資料處理/永豐範例對帳單.xlsx` | 9729 | `463010d862e307d0fd5b645a7d7a5db5fa8f7f8d22760251abb0f5c0cacf5107` | `format-fixture`；Finance Import 真實格式驗收 |
| `document/資料庫、資料處理/訂單系統.csv` | 1878 | `f0b2f6dfdd8d7a6b3ebc9f0787a0e6d13fa20ad97b7c9c6185d4644790d04869` | `data-lineage-evidence`；Case Import／Orders mapping |
| `document/資料庫、資料處理/假資料_模板.xlsx` | 51876 | `8d8b1dafc9773705bd8e6c8fbbb1a851f5d30157f1e4828232ea6d5d4806e810` | `test-fixture`；不具 production authority |
| `document/資料庫、資料處理/假資料_歷史訂單.xlsx` | 6516 | `c8a69103950e27b29b5c62fdce24bbbebfcf99bdbae92773c15879fae516aad9` | `test-fixture`；不具 production authority |
| `document/資料庫、資料處理/帳務.xlsx` | 8153 | `bd22f7459a8755cba2e7347d8a51f08ef01420534d39b057b04d6317b5967788` | `historical`；含帳號、戶名與撥款對應，限制存取；不覆蓋 Client Finance／Staff Payables SSOT |
| `document/資料庫、資料處理/資料庫來源表.xlsx` | 19944 | `2863081b7773900cd01116aedc0fcffe0bfa6cd12b0eca5d3d43964462c7fe4c` | `historical`；Case Import 欄位 lineage 與來源格式證據 |
| `document/資料庫、資料處理/歷史對帳單.xlsx` | 9968 | `f68eea409471f79cc1071e63336a1896f77875a326a10c01530acb4b1e131a0a` | `format-fixture`；Historical Reprocess 驗收 |
| `document/管理端UI/系統異常警示中心規格書.docx` | 33216 | `2bbfe70babb46a66e6242fdb49fce10a74c6da5748b093b03573aed44c25e825` | `conflict`；草案與 retired services 的歷史證據，Anomalies 正式規格優先 |
| `document/管理端UI/表格需求模板/所需表格.xlsx` | 193118 | `f38c93a66707769241f2e50640a317ba6719b9bc4707990defd86941f3371c0f` | `mixed`；「給服務人員的訂單資訊-1/-2」是 output-shape evidence；「客戶契約」是 historical/legal-template evidence，不授權電子簽署商或公開 Contract API |
| `document/管理端UI/表格需求模板/服務人員契約.xlsx` | 371317 | `247a0e34644ca3551cea393498c349102714bf5604a9a3d5b511929392e3788c` | `historical/legal-template-evidence`；保留契約義務、保險、責任、費率與終止內容；不授權 provider/API，法律效力與保存年限由業務／法務負責 |
| `document/管理端UI/表格需求模板/核銷含印領清冊.xlsx` | 10473 | `1e8309f91581d53cbc676691fad345dadfbadbcc8378eb6eba983835a38cde52` | `output-template-evidence`；Government Subsidy／Finance Query |
| `document/管理端UI/表格需求模板/週報.xlsx` | 425220 | `0ec9706931a09b2e5a8f20572972fe8d9103008f6aeed0c4ee2b8d1f99880013` | `historical-operational-report`；含實際營運、補助案件／金額／核銷季別與排班，限制存取且保存責任敏感；不是 write SSOT，保存年限由業務／法務裁決 |
| `document/管理端UI/表格需求模板/應付帳款.xlsx` | 11128 | `85313655ba131a127326a4a07b7927420d47c45faed511e7a2b4b268ca0340d9` | `output-template-evidence`；Accounts Payable Export 驗收 |
| `document/管理端UI/資料庫原始資料瀏覽_頁面欄位開放權限建議表.xlsx` | 15019 | `a9a9db6d981ae5aa6de3f269c4eb16f6054769afe374a2e2cff089fff600f524` | `conflict`；generic direct-edit proposal，Access Control 與 owning-domain commands 優先 |

## 規則

1. `format-fixture`／`test-fixture` 只定義輸入或驗收格式，不決定 Domain 語意。
2. `output-template-evidence` 只定義使用者輸出形狀；金額、狀態與資格仍由 owning Domain Query。
3. 其中九份涉及業務語意的附件已依目前 bytes／SHA-256 完成人工內容裁決：`LINE (1).pptx`、
   `月子媒合流程圖.canvas`、`帳務.xlsx`、`資料庫來源表.xlsx`、`系統異常警示中心規格書.docx`、
   `所需表格.xlsx`、`服務人員契約.xlsx`、`週報.xlsx`、
   `資料庫原始資料瀏覽_頁面欄位開放權限建議表.xlsx`。內容摘要、來源對照與
   `covered | conflict | historical | out-of-scope` 結果記於
   `03_追蹤清單與證據/evidence/2026-08-09_human_content_review_precheck.md`。其餘九份為
   generated evidence、format/test fixture 或已有正式 Domain 對應的 output evidence，
   由本索引記錄證據責任。
4. bytes 或 hash 改變時，該列內容裁決立即失效；不得沿用舊 hash 的內容審查結論。
5. 附件內容審查不得直接修改 production code 或把視覺欄位推定成 DB SSOT。

## 人工確認 Gate

`15`～`19` 與裁決總表是完整架構 SSOT；附件只保留上述分類的證據責任。
