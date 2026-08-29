# 非 Markdown 核心附件索引

## 狀態

- 盤點日期：2026-08-29
- 範圍：`document/` 下目前存在的所有非 `.md` 檔案
- 數量：22
- 本索引只負責附件定位、完整性與證據分類；正式規格仍優先於附件內容。

## 現存附件

| 路徑 | Bytes | SHA-256 | 分類／處置 |
|---|---:|---|---|
| `document/line/QA問答集.xlsx` | 177985 | `fc9ef455d027fa9fbb4f48269410246a8af36a6cceeca6a15cd35837b323870b` | `knowledge-source`；須經 owner／category／approved answer review 才能 publication |
| `document/月子媒合流程圖.canvas` | 11840 | `89a52c2890d5f6b09dab90d7c6cd134fce67b769d3a5e26184dd2ca6ae0026cf` | `historical/conflict`；不覆蓋 typed Domain 與 provider-neutral 正式裁決 |
| `document/架構重整/03_追蹤清單與證據/evidence/entrypoint_review_queue_v1.jsonl` | 217314 | `dc6f6f78351d0a0915c27c3b4ed1ecc14d6f1f874b846d7ec9c8cc60f07f0a03` | `generated-live-evidence`；entry point review queue，不是業務 SSOT |
| `document/架構重整/03_追蹤清單與證據/legacy_active_201_可追蹤清單.csv` | 40981 | `27c05c1d4c8e5b573a2b408a4b9e1cd7a4318b56ea7111cf2fb90b6729aab74d` | `generated-live-evidence`；legacy finding inventory，不是刪除授權 |
| `document/管理端UI/系統異常警示中心規格書.docx` | 33216 | `2bbfe70babb46a66e6242fdb49fce10a74c6da5748b093b03573aed44c25e825` | `historical/conflict`；Anomalies 正式規格優先 |
| `document/管理端UI/表格需求模板/所需表格.xlsx` | 193118 | `f38c93a66707769241f2e50640a317ba6719b9bc4707990defd86941f3371c0f` | `mixed-output/legal-template-evidence` |
| `document/管理端UI/表格需求模板/服務人員契約.xlsx` | 371317 | `247a0e34644ca3551cea393498c349102714bf5604a9a3d5b511929392e3788c` | `historical/legal-template-evidence`；保存責任由業務／法務裁決 |
| `document/管理端UI/表格需求模板/核銷含印領清冊.xlsx` | 10473 | `1e8309f91581d53cbc676691fad345dadfbadbcc8378eb6eba983835a38cde52` | `output-template-evidence`；Government Subsidy／Finance Query |
| `document/管理端UI/表格需求模板/週報.xlsx` | 425220 | `0ec9706931a09b2e5a8f20572972fe8d9103008f6aeed0c4ee2b8d1f99880013` | `historical-operational-report`；限制存取，保存責任由業務／法務裁決 |
| `document/管理端UI/表格需求模板/應付帳款.xlsx` | 11128 | `85313655ba131a127326a4a07b7927420d47c45faed511e7a2b4b268ca0340d9` | `output-template-evidence`；Accounts Payable Export |
| `document/管理端UI/資料庫原始資料瀏覽_頁面欄位開放權限建議表.xlsx` | 15019 | `a9a9db6d981ae5aa6de3f269c4eb16f6054769afe374a2e2cff089fff600f524` | `historical/conflict`；owning-domain commands 與 Access Control 正式規格優先 |
| `document/資料庫、資料處理/1,HCM.xlsx` | 7538 | `9dd4a2839949317603667cdbfb09855d960ec3fcc0d3cbcf5519734ac1da5b7c` | `format-fixture`；HCM import |
| `document/資料庫、資料處理/2.staff.xlsx` | 7914 | `17a4d66587baf9647b063a1b64f28b0e4e7cd81f4ea2fd4d3641e31d05e38059` | `format-fixture`；Staff import |
| `document/資料庫、資料處理/3.client_beclass.xlsx` | 9855 | `15e9bbf41070c750f50863fe83b3b6a03d49c1f612acb751a609febd5391edfd` | `format-fixture`；Client BeClass import |
| `document/資料庫、資料處理/假資料_模板.xlsx` | 51876 | `8d8b1dafc9773705bd8e6c8fbbb1a851f5d30157f1e4828232ea6d5d4806e810` | `test-fixture`；不具 production authority |
| `document/資料庫、資料處理/假資料_歷史訂單.xlsx` | 6375 | `c3f1145d966dce945ff2613114f893ee7250645187916e28db47bdaa8682d138` | `test-fixture`；不具 production authority |
| `document/資料庫、資料處理/台新範例對帳單.xlsx` | 15132 | `3faef5ff29a153217e379707f69fcead5851a1b352d067eeb990fc73d00ad7f5` | `format-fixture`；Finance Import |
| `document/資料庫、資料處理/永豐範例對帳單.xlsx` | 9729 | `463010d862e307d0fd5b645a7d7a5db5fa8f7f8d22760251abb0f5c0cacf5107` | `format-fixture`；Finance Import |
| `document/資料庫、資料處理/歷史對帳單.xlsx` | 9968 | `f68eea409471f79cc1071e63336a1896f77875a326a10c01530acb4b1e131a0a` | `format-fixture`；Historical Reprocess |
| `document/資料庫、資料處理/訂單系統.csv` | 1875 | `127961a57eaca166529023231618edfdb72edfd599235c0bde63bbceaf1a3158` | `data-lineage-evidence`；Case Import／Orders mapping |
| `document/資料庫、資料處理/帳務.xlsx` | 8153 | `bd22f7459a8755cba2e7347d8a51f08ef01420534d39b057b04d6317b5967788` | `historical-sensitive`；不覆蓋 Client Finance／Staff Payables SSOT |
| `document/雲端部署/比較圖/Cloud_Run_連線方案比較圖.svg` | 14346 | `30bee64ee6f18d198192bd2eedb8c155d1c92f9356073a41d12bf3bf914bd2c3` | `design-evidence`；不構成 cloud deployment 授權 |

## 規則

1. `format-fixture`／`test-fixture` 只定義輸入或驗收格式，不決定 Domain 語意。
2. `output-template-evidence` 只定義輸出形狀；金額、狀態與資格仍由 owning Domain Query。
3. bytes 或 SHA-256 改變時，該列內容裁決立即失效，必須重新盤點。
4. 附件內容不得直接推定成 DB SSOT、provider 選擇或 production mutation 授權。
5. 法律、營運與敏感附件的刪除／保存期限須另經業務或法務裁決。
