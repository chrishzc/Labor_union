# Local DB release 1003 保留資料升級至 current 規格

- `spec_id`: `PROV-20260828-local-db-1003-to-current-upgrade-spec`
- `declared_status`: `approved`
- `convergence`: `SPEC_READY`
- `authority`: 2026-08-28 人工要求確保另一台目前只到 DB release 1003 的電腦可升級並正常 local 啟動
- `owner`: Global Migration／Developer Local Runtime
- `research`: `NO_RESEARCH (R0)`；canonical manifests、runner、launcher 與 tests 已足以裁決

## 1. Objective 與四條分離流程

另一台 development 機器的既有資料必須由 exact release 1003 保留資料升至 runner 當下解析的 canonical
latest，完整通過後才允許 normal no-auth local startup。

- release 1003：`labor-union-matching-coordination-successor-2026-08-22-v1`；artifact
  `1003_matching_coordination_successor.sql`。
- 2026-08-28 current parser latest：`labor-union-service-before-replacement-2026-08-28-v1`；artifact
  `1012_service_before_replacement.sql`。current chain為51 manifests／101 artifacts；此值只是本revision
  的readback，不得硬編進runner。
- current gap：1004 controlled-file、1005 contract external signing、1006 historical review remediation、1007
  finance recovery evidence、1008 historical adoption noop、1009 anomaly reclassification、1010 historical
  operational baseline、1011 historical baseline projector、1012 service-before replacement。

fresh bootstrap、preserve-data upgrade、fixture reset 與 normal startup 是四條不同流程。任何一條 PASS 都不得
替代另一條；`start_local_development` 不得隱式套 schema。

## 2. Requirements

- `LDU-R1`：latest 與 ordered chain 只由 canonical manifests 解析，不硬編 1009；plan 列出 baseline、latest
  及每個 1004→latest artifact 的 `absent | exact | partial | drift`。
- `LDU-R2`：只接受連續 exact prefix；chain hole、partial、drift、unknown、hash／descriptor mismatch 全部
  fail closed，且零 DDL。
- `LDU-R3`：每個待套 release 都須有同 release／fingerprint／artifact 的 current published qualification，
  並具 fresh 與 1003 representative-data source→candidate→apply→verify evidence。
- `LDU-R4`：developer path 只依序套既有 schema-only releases；每 release 建立 machine/server/DB/baseline
  綁定 backup、receipt 與 journal。禁止 seed、row backfill、DROP、replacement、reset、`--switch`。
- `LDU-R5`：每步 readback owned objects exact；中斷後只從 current exact prefix 續跑，不重套成功 release，
  原 backup／journal 遺失固定停止。
- `LDU-R6`：`--require-current` 只有整條 canonical chain exact 才可通過；terminal artifact exact 不能遮蔽
  中間缺口。
- `LDU-R7`：Windows／Unix startup 在 API、UI、worker 前執行 full-chain current gate；launcher `--dry-run`
  只證明 wiring，不是 DB plan。
- `LDU-R8`：升級完成後 normal Task96 no-auth startup 的 API `/health`、React `/admin/` 與 proxy GET 通過；
  optional LINE credentials 缺失只能 skip LINE，不得掩蓋 required process failure。
- `LDU-R9`：builder的三份final engine evidence必須由dedicated deterministic producer從canonical manifest／
  descriptor、runner final receipts、actual dump hashes與fresh DB readback產生，不得手工拼接。producer只接受
  explicit release/artifact、`lu_test_*` development source／candidate／fresh identities與同release final receipts；
  驗證source與candidate不同、source未變、target exact、全體canonical table count／stable fingerprint一致、
  zero data write／seed／backfill／destructive，輸出strict JSON至ignored scratch且atomic no-overwrite。它不得發布
  qualification、修改schema/data、接受intermediate receipt，或把old phase4 summary轉抄為current evidence。
- `LDU-R10`：fresh bootstrap前置field-authority audit必須依mapping所屬persisted field context判定legacy
  reference；`orders.contract_id`仍fail closed，但其他Domain合法的catalog／descriptor `contract_id`不得被token-only
  掃描誤判。context pattern由versioned audit manifest明列、strict編譯；無pattern的既有mapping維持exact token掃描。
- `LDU-R11`：ordered planner只把「前置release尚未套用，且descriptor所有parent tables都尚不存在」的future
  drift標為`dependency_pending`；future exact仍是chain hole，parent table已存在的partial／drift仍BLOCKED。
  1008 predecessor check必須由既有typed comparator判為absent。Apply allowlist只可接受canonical hash-locked
  1008同一atomic ALTER內`DROP CHECK`後以同名`ADD CONSTRAINT`替換；任何其他DROP或資料mutation仍禁止。

## 3. Acceptance 與 failure semantics

- `LDU-A1`：1003 exact＋1004…latest absent形成 ordered ready plan。
- `LDU-A2`：1003、1005 exact但1004 absent形成 hole blocker，零 DDL。
- `LDU-A3`：任一 partial／drift／unknown回報精確 artifact／reason，零 DDL。
- `LDU-A4`：qualification 缺失、過期或衝突時，零 backup／DDL。
- `LDU-A5`：disposable真 MySQL以代表舊資料完成1003 source→dump→candidate→sequential apply→verify；source
  不變，candidate objects exact，代表資料 count／PK／stable fingerprint相同，`backfills=[]`。
- `LDU-A6`：allowlisted developer copy完成停服務、plan、backup、apply、full-chain current與before/after保存。
- `LDU-A7`：舊 DB normal startup在建立 child前阻擋；升級後 no-auth API／React／required workers與Browser GET通過。
- `LDU-A8`：1006後模擬中斷，重跑從1007開始，1004～1006不重套。
- `LDU-A9`：同一final engine run可機械重建metadata backup／fresh bootstrap／preserve candidate三種evidence；
  copied、stale、cross-release、cross-server、source-changed、partial descriptor、缺table、row fingerprint差異、
  非`lu_test_*`或非development輸入全部零發布fail closed。三份evidence通過builder preview後才允許explicit publish。
- `LDU-A10`：H projector合法的descriptor `contract_id`不阻擋bootstrap；在任一active scan path加入同列
  `orders.contract_id`或Orders SQL context後audit必須失敗；invalid regex manifest也必須回typed validation error。
- `LDU-A11`：exact 1003 plan將1004與dependency-pending 1005列為待套，不再誤報drift；1004套用後1005為
  absent。1008 exact predecessor為absent、任意第三種check expression為drift。1008 canonical statement可執行，
  改名constraint、拆成standalone DROP或加入其他DROP／DML皆被allowlist拒絕。

target非localhost development allowlist、DB為`union_db`／system、服務未停、1003非exact、latest執行中漂移、
chain／qualification／descriptor／backup／journal不一致、出現非schema-only效果、row fingerprint改變、lock／timeout
或startup health失敗時固定停止。

## 4. Change inventory 與 current gate

本規格不新增或改寫 SQL：`schema-only=existing 1004..latest`、`system-seed=none`、
`business-row-backfill=none`、`destructive=none`。

| Gate | Status | Current evidence |
|---|---|---|
| Scope | `PASS` | 本規格與人工2026-08-28 Authority |
| Change inventory | `PASS` | 只使用既有schema-only releases |
| Static release | `PASS` | parser解析101 artifacts、terminal 1012；fresh assembly／cutover／full release已收錄1012 |
| Descriptor | `PASS` | 1004～1012 owned-object descriptors與candidate current exact |
| Read-only plan | `PASS` | exact 1003已列出1004→1012 ordered qualifications exact plan |
| Engine verification | `PASS` | disposable representative-data preserve candidate、fresh bootstrap與1003→1012 chain已驗證 |
| Developer acceptance | `NOT_RUN` | 另一台機器尚未執行 |

DB summary：`DB_CHANGE_NOT_READY`。

Terminal status：`SPEC_READY`。

## 5. Deterministic qualification builder contract

`LDU-R3`的published qualification不得手工拼接。builder固定為本機deterministic工具，輸入為explicit
release/artifact及三類final evidence：metadata backup、fresh bootstrap descriptor readback、1003
preserve-data candidate/apply/verify。每份evidence必須strict JSON、`status=verified`、同一release/artifact/
manifest/descriptor identity，且具完整schema fingerprint、dump SHA-256、row count/fingerprint、target
projection exactness與`backfills=[]`；缺欄、跨版、cross-artifact或intermediate receipt固定拒絕。

strict JSON包含nested duplicate key拒絕；metadata backup必須另帶backup dump SHA-256。fresh與preserve
不得只提供自行計算的target fingerprint，必須提供完整owned-object projection；builder以canonical descriptor
正規化後逐欄比對並重算fingerprint。row evidence的table identity只接受canonical schema inventory中的名稱，
避免把任意名稱、secret或PII帶入published receipt。

builder由canonical manifest與descriptor重算artifact hash、release fingerprint、manifest inventory、
target projection、zero seed/backfill/destructive policy、policy evidence與payload digest；不能信任輸入中的
重複canonical欄位。預設只輸出preview到stdout且不寫檔；explicit publish只允許
`validation/receipts/`下符合命名規則的新JSON，先以current validator round-trip，再atomic create；目標存在
固定停止，不允許overwrite。publish只接受同一process由builder直接產生、未經copy／手工重建的payload；
builder不得連DB、產生engine evidence、把supporting evidence升格為verified，
或自行發布1006～1012 receipt。

驗收包含deterministic same-input same-payload、tampered hash/version/status/target/row evidence negatives、
preview zero-write、publish path/overwrite fail closed、validator round-trip及secret/PII最小化。

## 6. Final engine evidence producer contract

producer重用`migrate_preserved_database_additive_schema`的schema snapshot、table evidence、target-state classifier、
dump／operation receipt與canonical manifest loader，不另定義schema公式。每個release使用final predecessor source、
未寫資料的fresh path與單一release preserve candidate；source dump須與metadata backup同一bytes identity，Apply後
重新讀candidate descriptor與全部canonical tables，並再次讀source證明未變。row fingerprint只保存hash與count，
不得保存row內容、secret或PII。

producer輸出只屬supporting evidence，不是qualification或developer acceptance。任何DB mutation仍由既有
bootstrap／migration runner擁有；producer本身只讀DB與既有artifact。若runner final receipt缺少可驗證的
source/candidate/server/dump binding，producer固定停止，不得從名稱或舊receipt推測。

```yaml
convergence:
  status: READY
  blockers: []
```
