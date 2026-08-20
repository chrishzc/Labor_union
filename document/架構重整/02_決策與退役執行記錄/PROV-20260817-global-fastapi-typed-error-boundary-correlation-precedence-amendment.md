---
doc_type: work-package-amendment
declared_status: completed
identity: PROV-20260817-global-fastapi-typed-error-boundary-correlation-precedence-amendment
date: 2026-08-17
owner: Global / API Boundary Integration Owner
domain: Global
amends: PROV-20260817-global-fastapi-typed-error-boundary
prerequisites: PROV-20260817-react-admin-phase3-scenario-lineage-governance completed with PHASE3_SCENARIO_LINEAGE_METADATA_READY
approval_required: 核准此 exact Global FastAPI Correlation Precedence Amendment Work Package
base_branch: main
base_head: 8615225481c8f72a9629289285516189b270cb36
---

# Global FastAPI Correlation Precedence Amendment

## Activation record

使用者已於2026-08-17明確回覆：

> 核准此 exact Global FastAPI Correlation Precedence Amendment Work Package

本修訂已進入`in-progress`，並解除原Global WP的`GERR-01`文件裁決阻擋；production仍須通過原WP全部門禁。

## 0. Business scenario

管理端每次HTTP request需要一個可在Network、error envelope與server boundary一致查找的公開correlation。
既有完整typed error有時使用route自產值；若同時要求payload完全無損與request header唯一值，兩者無法同時成立。

本修訂只裁決公開error serialization的precedence，不改Domain command、receipt、audit、outbox、job、
idempotency、DB或provider side effect。

## 1. Exact decision

1. canonical runtime correlation `C`：合法request `X-Correlation-ID`原樣使用；缺少時產生`uuid4().hex`；
   blank、leading/trailing whitespace、超過191字元或不符合`^[A-Za-z0-9][A-Za-z0-9._:-]{0,190}$`時，
   產生安全`uuid4().hex`並回422，攻擊者輸入不得回顯。
2. Correlation boundary必須在所有受控namespace的router、dependency及FastAPI parameter validation前
   解析header，而且不能只寫入`request.state`：
   - header absent：產生`C`，並在ASGI request scope注入唯一`x-correlation-id: C`，使既有required或
     defaulted `Header(alias="X-Correlation-ID")` consumer及Domain command都收到同一`C`；
   - exactly one valid value：原樣保留並注入同一值；
   - exactly one invalid value或two-or-more values：產生安全`C`、不呼叫下游、回422 fixed envelope，且
     不回顯任何輸入值。
   所有受控namespace的成功、304、framework error與typed error response都只能有一個
   `X-Correlation-ID: C`，且error的`detail.error.correlation_id`必須等於`C`。非受控provider／public
   namespace維持原契約。
3. 完整既有typed `detail.error`採**response-only correlation rebase**：只把公開回應的
   `correlation_id`換成`C`；`category/code/message/field_errors/domain_blockers/retryable/current_version`、
   HTTP status及`Retry-After`／`WWW-Authenticate`逐值保留。
4. Boundary不得重建、覆寫或重新提交Domain command，不得讀寫receipt／audit／outbox／job，不得改變
   idempotency identity或既有持久correlation。Boundary不得把route hard-coded／legacy correlation序列化至
   response、header或boundary自身log；選定真query route的capture log亦不得出現該legacy值。其他route／
   Domain既有logging不在本包write set，不得把這項驗證宣稱為全系統log coverage。
5. Correlation不是跨retry的業務receipt identity。相同Idempotency-Key＋payload重放時，操作者應以正式
   `receipt_id`／`job_id`追蹤結果；不得把舊correlation偷塞入error作第二追蹤欄位。
6. 不完整或legacy error仍走原Global WP的strict allowlist／status-based redacted fallback。

## 2. Exact write set

本修訂核准階段只允許文件／evidence：

- 本 amendment
- `PROV-20260817-global-fastapi-typed-error-boundary-work-package.md`
- `PROV-20260817-global-fastapi-typed-error-boundary-gap.md`
- `document/架構重整/02_決策與退役執行記錄/README.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-global-fastapi-typed-error-boundary/contract-matrix.md`
- `document/架構重整/03_追蹤清單與證據/evidence/PROV-20260817-global-fastapi-typed-error-boundary/open-findings.md`
- `tests/test_order_reopen_router.py`（只修正missing／duplicate／invalid correlation的既有route contract測試）

Production與正式Global規格仍沿用原Global WP的exact write set；本修訂只新增上述既有route regression
test的寫入權。本修訂不新增或修改business route production、DB、React page或provider write authority。

## 3. Acceptance

- valid／missing／invalid／duplicate `C`均驗證header=envelope；invalid／duplicate input不回顯且0 downstream。
- missing header必須由boundary注入到真`Header(alias="X-Correlation-ID")` consumer；不得只在request state
  或response端補值。
- 真typed error在old correlation與`C`不同時，只允許correlation欄改變，其餘七欄、status與protocol headers相同。
- 真query route的hard-coded correlation不出現在public response/header或boundary／該route capture log；
  不宣稱覆蓋本write set外所有Domain log。
- 真mutation route證明合法header原值或missing時boundary產生並注入的`C`確實進入command；不得使用自製
  test-only handler代替FastAPI runtime。`tests/test_order_reopen_router.py`須將舊的missing-header=422 assertion
  改成：有合法Idempotency-Key且缺correlation時，不因correlation缺失而422；valid payload時captured command、
  response header一致，其他payload validation失敗時422 envelope/header仍使用同一`C`。
- static/runtime spy證明boundary沒有DB/UoW/repository/outbox/job/provider import或call。
- same-key replay不得因response rebase讀寫或比較既有receipt correlation；無隔離engine evidence時該項維持
  `BLOCKED_ENGINE_EVIDENCE`，不得以unit mock宣稱完成。

## 4. Activation／completion

本amendment已取得人工逐字核准，GERR-01已關閉，原Global matrix已重新freeze並完成writer驗收。

本amendment完成只代表correlation precedence已裁決；Global boundary仍須通過原WP全部TestClient、React、
redaction、auth與full regression gates。

2026-08-17 completion：missing／valid／invalid／duplicate header與response-only rebase均由真FastAPI
TestClient覆蓋；backend exact suite 72 PASS，React nested decoder focused 69 PASS。Boundary未讀寫DB、
receipt、audit、outbox、job或provider。

## 5. DB gate

Scope／Change inventory `PASS`（0 DB）；其餘`NOT_RUN`；結論`DB_CHANGE_NOT_READY`。
