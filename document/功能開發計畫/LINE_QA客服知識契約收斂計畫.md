---
doc_type: feature-plan
declared_status: blocked
date: 2026-08-20
updated: 2026-08-20
priority: P2
owner: Customer Service / Knowledge Retrieval Integration Owner（待人工確認）
domain: Customer Service / Knowledge Retrieval / LINE Integration
subsystem: Service Help / Knowledge Fallback / Evidence Intake
source_artifact: document/line/QA問答集.xlsx
source_artifact_role: input-evidence-only
loader_status: BLOCKED_ARTIFACT_TOOL_RUNTIME_UNAVAILABLE
approval_required: exact human confirmation before any production or formal-spec change
db_change: none
---

# LINE QA 客服知識契約收斂計畫

## 1. Status and activation boundary

本計畫目前為 `blocked`。本輪無法取得 `load_workspace_dependencies` 提供的
`@oai/artifact-tool` runtime，因此尚未 import／inspect
`document/line/QA問答集.xlsx`；不得猜測 workbook 的 sheet、range、題數、答案、空值或重複資料，
也不得以歷史抽取結果冒充本輪證據。

Excel 只可作為 input evidence，不是 SSOT、正式規格、approved answer catalog 或 production
mutation 授權。未完成 loader inspection 與人工 review 前，不得啟用 AI 回答、provider 發送、DB seed、
knowledge publish、LINE webhook 行為或任何 production writer。

## 2. Business scenario

工會需要將 QA 問答素材收斂為可追溯的 LINE 客服 Service Help／Knowledge fallback 契約：
保留既有 identity、group、service-help、knowledge fallback 的分派順序；每題都能追到來源、owner、
人工核准答案與允許的自動化邊界；無法核准或來源不足時，固定進人工客服協處，不由模型猜答案。

## 3. Authority and semantic constraints

- Global 契約將 Excel、UI、cache、read model 與 query view 排除於 root fact／SSOT：
  `document/架構重整/01_規格基線/00_Global_共同契約.md:21-25,110-120`。
- 正式索引將 Customer Service、Knowledge Retrieval 與 LINE Integration 分別交由正式規格擁有：
  `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md:157-163`。
- 規格 20 固定 Service Help intent、六分類別名與
  `identity → group → service help → knowledge fallback` 順序；客服根事實與人工回覆由 Customer
  Service 擁有：
  `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md:29-33,61-71`。
- Knowledge answer 必須維持 `authoritative=false`，不可觸發業務 mutation；published knowledge query
  必須帶來源與版本：`document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md:343-346`、
  `subsystems/knowledge_retrieval/answer_query.py:1-20`。

## 4. Scope after loader recovery

1. 以 `@oai/artifact-tool` 唯讀 import／inspect workbook；保存最小 locator（sheet、range 或 table）與
   inspection timestamp，不輸出整份 workbook 或不必要個資。
2. 逐題抽取並分類：`question`、`answer`、`category`、空值、重複鍵／重複問法、來源欄位與既有版本標記；
   缺欄、空答案、重複或無法判定的列一律進 review queue。
3. 對每題建立人工 review record：`owner`、`category`、`source`、`approved_answer`、
   `automation_boundary`、`disposition`（`service_help`／`knowledge_fallback`／`manual_only`／`reject`）。
4. 將題目對照規格 20 的六個 Service Help 分類與 exact intent；不把 QA 素材直接升格為正式答案、
   Domain rule、FAQ publish 或 AI prompt。
5. 產出可追溯的 conflict／missing／duplicate／blank／unowned 清單，等待人工確認後才可另立 exact
   Work Package 或 formal-spec amendment。

## 5. Out of scope

- 不修改 `document/line/QA問答集.xlsx`，不輸出新 workbook，也不建立歷史抽取副本。
- 不修改正式規格、README/index、02/03 evidence catalog、production code、tests、route、API schema、
  provider、AI model、prompt、DB/schema/seed/backfill 或 migration。
- 不直接建立或發布 Knowledge item，不自動核准答案，不將 Excel row 當作客服、LINE 或 Knowledge 的根事實。
- 不改 Service Help routing、identity/group precedence、delivery、webhook 或 customer-service ticket state。

## 6. Dependencies and human review queue

- **Loader/runtime**：恢復 `load_workspace_dependencies` 與 `@oai/artifact-tool` 後，先做唯讀 import／inspect。
- **Owner**：人工指定每題 Customer Service、Knowledge Retrieval 或其他 bounded owner；未指定者 `unowned`。
- **Category**：人工確認六個正式 Service Help 分類；不可從鄰近文字自行推導正式分類。
- **Source**：人工確認來源 URI／文件版本／可信層級；沒有可追溯來源者 `manual_only` 或 `reject`。
- **Approved answer**：人工核准 exact wording、有效期限與禁答邊界；不能由模型或 workbook 自稱 approved。
- **Automation boundary**：人工決定可否使用 published cited knowledge；涉及 identity、案件、服務日、費用、
  狀態或業務 mutation 一律不得由 QA 素材自動回答或執行。
- **Conflict queue**：任何與規格 20、17、23、現有 Service Help 或 Knowledge owner 衝突者，維持 `blocked`，
  等待 architecture／business owner 裁決。

目前 workbook inspection locator：`NOT_AVAILABLE`（loader blocker；沒有任何 sheet/range/row 統計可宣稱）。

## 7. Exact write set

本計畫 lane 唯一 write set：

- `document/功能開發計畫/LINE_QA客服知識契約收斂計畫.md`

本檔只記錄 proposed／blocked contract 與 review queue，不授權任何 production、DB、provider 或正式規格變更。

## 8. Acceptance and required tests

### Acceptance

- loader recovery 後能以 artifact-tool receipt 指出精確 workbook locator、檢查範圍與遮罩後的 counts。
- 每題都有 owner、category、source、approved answer、automation boundary 與 disposition；空值、重複、缺來源、
  conflict 均有明確 review outcome。
- Service Help 分派順序與六分類別名仍符合規格 20；Knowledge fallback 只消費已發布且可引用來源的答案。
- 未取得人工核准前，結果只能是 blocked／manual-only／unavailable，不得宣稱 AI、provider、DB seed 或 production ready。

### Required tests（後續 exact Work Package 才可執行）

- fixture-level：六分類別名、identity/group precedence、unknown intent fallback、exact replay 不重複 ticket/task。
- contract-level：每個 published answer 有 source URI/version/citation；未核准、過期或缺來源答案 fail closed。
- safety-level：空值／重複／PII／prompt-like content 不進 production answer；AI/provider 呼叫為零，manual fallback 可追蹤。
- integration-level：Service Help 只建立 canonical durable delivery 或客服 ticket，不直接寫 Domain；任何 mutation 仍走
  owning Domain Preview／Apply／receipt／re-query。
- 文件級：strict UTF-8、`git diff --check`、evidence locator 與 review queue 可重現。

## 9. Decision and evidence links

- 需人工決策：是否採用任何 QA row、正式 category／owner、approved answer、source trust tier、automation boundary、
  是否另立 formal-spec amendment／exact Work Package。
- Source evidence：`document/line/QA問答集.xlsx`（目前未能以規定 loader inspect）。
- Formal authority：`document/架構重整/01_規格基線/00_Global_共同契約.md`、
  `document/架構重整/01_規格基線/15_正式規格索引與裁決總表.md`、
  `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md`。
- Current implementation witnesses：`subsystems/line/service_help_application.py:53-77,179-204`、
  `subsystems/line/knowledge_question_application.py:7-16`、`subsystems/knowledge_retrieval/answer_query.py:8-20`、
  `api/routes/knowledge_retrieval.py:31-70,156-170`。
