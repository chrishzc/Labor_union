# 非 Markdown 核心附件索引

## 狀態

- 盤點日期：2026-09-09
- 範圍：`document/` 下目前存在的所有非 `.md` 檔案。
- 數量：22
- 本索引只負責附件定位、完整性與證據分類；正式規格、current register 與 owning Domain 契約優先於附件內容。
- 完整性欄改用 repository current tree 的 Git blob SHA；blob identity 改變即需重新盤點該列。

## 現存附件

| 路徑 | Git blob SHA | 分類／處置 |
|---|---|---|
| `document/line/AI客服QA題庫.jsonl` | `a0912f35c84621628bc5b84f3df98a8074017b03` | `knowledge-source`；publication 前仍須 owner／category／approved-answer review |
| `document/line/QA問答集.xlsx` | `562f4fa6bab3d2a319be63b1b7a6a7bbea6fef81` | `knowledge-source`；review input，不自行成為 LINE 回覆 Authority |
| `document/架構重整/03_追蹤清單與證據/evidence/writer_inventory_v3/writer_inventory_v3_candidate.findings.jsonl` | `f01efb8f02bcde994916bb5cf757022cd3df91a2` | `generated-live-evidence`；production writer inventory v3 candidate set |
| `document/架構重整/03_追蹤清單與證據/evidence/writer_inventory_v3/writer_inventory_v3_candidate.manifest.json` | `8f00ed5bad6d3ac0257616f3b67905adf7b29ba8` | `generated-live-evidence`；candidate manifest |
| `document/架構重整/03_追蹤清單與證據/evidence/writer_inventory_v3/writer_inventory_v3_disposition.manifest.json` | `193d16f34e1f988de1d277fa8524953d7e1780db` | `generated-live-evidence`；current disposition summary |
| `document/架構重整/03_追蹤清單與證據/evidence/writer_inventory_v3/writer_inventory_v3_disposition.records.jsonl` | `7ea4e42d21d3bebde238fdfa1fe3648763c5c3bc` | `generated-live-evidence`；current per-identity disposition records |
| `document/管理端UI/表格需求模板/所需表格.xlsx` | `4fe0b35602f6e389579623e4a864aff49407499e` | `mixed-output/legal-template-evidence`；保留作輸出／需求來源，不自行決定業務公式 |
| `document/管理端UI/表格需求模板/服務人員契約.xlsx` | `f3b05146ed63a9d863f52f7d7290cbde699d0883` | `historical/legal-template-evidence`；保存責任由業務／法務裁決 |
| `document/管理端UI/表格需求模板/核銷含印領清冊.xlsx` | `2eab40d7102e57ff1efbcc5cc2620ba688698832` | `output-template-evidence`；Government Subsidy／Finance Query 決定正式值 |
| `document/管理端UI/表格需求模板/週報.xlsx` | `6863956b219926708baee9e3f82f291f088f8cae` | `historical-operational-report`；限制存取，保存責任由業務／法務裁決 |
| `document/管理端UI/表格需求模板/應付帳款.xlsx` | `d07c9d953c1e635a37dd7ead83c857aeb28436ef` | `output-template-evidence`；Accounts Payable Export shape source |
| `document/管理端UI/資料庫原始資料瀏覽_頁面欄位開放權限建議表.xlsx` | `726e63967cb58e7391e1f3b9bebcd7164b7ff608` | `historical/source-review`；目前仍可作 internal-admin surface permission/masking inventory 輸入，formal Access／owner contracts 優先 |
| `document/資料庫、資料處理/1,HCM.xlsx` | `7b54c07b176b9fb7e4c8b438774f4a4bd13f2716` | `format-fixture`；HCM import |
| `document/資料庫、資料處理/2.staff.xlsx` | `8881fee0fc099b264b10ef89f2c63ad6d55552ac` | `format-fixture`；Staff import |
| `document/資料庫、資料處理/3.client_beclass.xlsx` | `5c8db9e9de539cbd0af13ea35e75af91199b2e64` | `format-fixture`；Client BeClass import |
| `document/資料庫、資料處理/假資料_模板.xlsx` | `c11974ed5f845b10d45cc4b02a86ceca17f5b21c` | `test-fixture`；不具 production Authority |
| `document/資料庫、資料處理/假資料_歷史訂單.xlsx` | `c8bae7774558defb5bb8fe16c114efc465826b` | `test-fixture`；不具 production Authority |
| `document/資料庫、資料處理/台新範例對帳單.xlsx` | `ea3798ce6cce6f2158e26f0eb2003d4372c7cccb` | `format-fixture`；Finance Import |
| `document/資料庫、資料處理/永豐範例對帳單.xlsx` | `8137aa76df1040819150ba3577d8d6da9b6da461` | `format-fixture`；Finance Import |
| `document/資料庫、資料處理/歷史對帳單.xlsx` | `0aa035f1990d1d863e47ed89794bc68eef6a850b` | `format-fixture`；Historical Reprocess／Finance Import lineage |
| `document/資料庫、資料處理/訂單系統.csv` | `bcdf840f24a785a5183ff36ea3e7b8a7257e5292` | `data-lineage-evidence`；Case Import／Orders mapping |
| `document/資料庫、資料處理/帳務.xlsx` | `17a89a4d253915196f3d0318eb3dd15f2cee0d7f` | `historical-sensitive`；不覆蓋 Client Finance／Staff Payables SSOT |

## 規則

1. `format-fixture`／`test-fixture` 只定義輸入或驗收格式，不決定 Domain 語意。
2. `output-template-evidence` 只定義輸出形狀；金額、狀態與資格仍由 owning Domain Query 決定。
3. `generated-live-evidence` 只在 current generator／validator／closeout consumer 仍存在時保留；consumer 消失後應回 Git history。Task 已結案的 historical receipt 不得因仍被技術腳本讀取就升格成新 source revision 的持續核准 Authority。
4. Git blob identity 改變時，該列內容裁決立即失效，必須重新盤點。
5. 附件內容不得直接推定成 DB SSOT、provider 選擇或 production mutation 授權。
6. 法律、營運與敏感附件的刪除／保存期限須另經業務或法務裁決。
