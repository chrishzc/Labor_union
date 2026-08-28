# Local DB release 1003 保留資料升級至 current 工作包

- `package_id`: `LDU-1003-CURRENT-01`
- `declared_status`: `approved`
- `package_status`: `PACKAGE_READY`
- `controlling_spec`: `PROV-20260828-local-db-1003-to-current-upgrade-spec.md`
- `requirements`: `LDU-R1`～`LDU-R11`
- `acceptance`: `LDU-A1`～`LDU-A11`

## Ordered work

1. single integration writer把 local additive discovery／plan由「只選latest」改為完整 ordered missing chain，輸出
   每個 artifact state、qualification與blocked reason；`--require-current`驗整條chain。
   同步把field-authority preflight由global token-only修正為manifest-owned persisted-field context；保留真正
   `orders.contract_id`負例與invalid-pattern fail closed，不放寬其他mapping。
   ordered classifier另須區分dependency-pending與真drift，並只為hash-locked 1008 atomic同名CHECK replacement
   開放最小DDL classification；不得建立generic DROP例外。
2. 建立deterministic final engine evidence producer：只讀canonical manifest／descriptor、final migration receipts、
   actual dump與`lu_test_*`DB readback，原子輸出三種strict supporting evidence至ignored scratch。它必須重讀
   source不變、fresh zero-row、candidate target exact與全canonical table count/fingerprint preservation；stale／
   cross-release／cross-server／partial／missing-table／non-development全部fail closed，且不得發布qualification。
3. 建立deterministic qualification builder：strict讀取同release/artifact的final backup/fresh/preserve
   evidence，由canonical manifest/descriptor重算qualification payload；preview zero-write，publish只允許
   validation receipts新檔且validator round-trip／atomic create／no overwrite。再對1004～latest逐release
   重驗current qualification；以真 MySQL fresh及含代表資料1003 source建立source→candidate→sequential
   apply→verify evidence。
   strict reader必須拒絕nested duplicate keys；backup evidence帶dump hash；fresh/preserve帶完整owned-object
   projection並由canonical descriptor重算，row table identity限canonical inventory。publish只接受同process
   build result，拒絕copied／hand-built mapping與任何nested secret/PII擴張。
4. developer runner加入逐release backup／journal／exact readback／resume；失敗不得replacement或盲目重跑。
5. 同步 Windows／Unix launcher、operator docs與focused tests；old DB startup零child阻擋，current DB才啟動。
6. 在合法 localhost development database完成受控apply與normal no-auth API／React／Browser acceptance，
   最後由fresh Luna/high read-only verifier獨立檢查。operator updater不得以`lu_test_*`前綴限制configured DB；
   qualification producer、disposable rehearsal與自動化驗收仍使用`lu_test_*`隔離namespace。

## Write set 與 hot spots

- `scripts/migrate_preserved_database_additive_schema.py`
- `scripts/update_local_database.py`
- `scripts/launchers/update_local_database.bat`
- local development no-auth launchers與其README
- release-scoped qualification／validation receipts
- focused migration／plan／launcher tests與本工作包evidence
- qualification builder source／focused tests；published qualification只有engine evidence PASS後才建立
- final engine evidence producer source／focused tests；supporting evidence只寫ignored scratch且不得冒充qualification

共同 catalog、manifest、receipt index與README由同一 integration writer處理。禁止改寫已發布SQL／hash-locked
artifact、建立新 DDL、由自動化驗收操作`union_db`、production、reset、replacement、`--switch`或全庫cleanup。
2026-08-28人工已明確授權operator-facing local updater接受configured `union_db`；這不授權測試或Agent自行對其Apply。

## Verification

依序：static catalog／descriptor tests → read-only ordered plan tests → fresh disposable MySQL → 1003 representative
source preserve-data candidate → final evidence producer negatives／source re-read → builder preview／publish →
interruption/resume → configured local developer database acceptance → no-auth local startup／Browser。

Windows operator commands必須分開報告：

- wiring：`scripts\launchers\update_local_database.bat --dry-run`
- real read-only plan：`.venv\Scripts\python.exe -m scripts.update_local_database --mysql-container mysql_db`
- explicit preserve-data apply：`.venv\Scripts\python.exe -m scripts.update_local_database --apply --confirm-configured-database --mysql-container mysql_db`
- current gate：`.venv\Scripts\python.exe -m scripts.update_local_database --require-current --mysql-container mysql_db`
- startup wiring：`scripts\launchers\start_local_development_no_auth.bat --dry-run`
- current後startup：`scripts\launchers\start_local_development_no_auth.bat`

2026-08-28 entry recheck：canonical runner latest已由1010前進至1012，ordered work仍依dynamic
canonical manifests，coverage不變；任何測試或實作不得把1010、1011或1012硬編成永久terminal。

Package status：`PACKAGE_READY`；runtime status：`in-progress`；DB summary：`DB_CHANGE_NOT_READY`。

## Execution ledger（2026-08-28）

- `LDU-ORDERED-RUNNER-SOURCE`: `completed`。dynamic 1003→latest plan、continuous exact prefix、
  per-release qualification/backup/journal/apply/replan/resume及strict current identity已完成。
- `LDU-NOAUTH-LAUNCHER-WIRING`: `completed`。Windows/Unix current gate均早於children；新增Unix
  no-auth thin wrapper，README與launcher tests已同步。
- `LDU-WINDOWS-RUNTIME-SUPERVISION-SOURCE`: `completed`。Windows supervisor已具備
  same-snapshot PID/CreationDate lineage、required/optional worker survival、React root readiness、
  nonzero failure propagation、machine-readable events與identity-verified scoped cleanup；unknown不得
  冒充exited/complete。no-auth `.env`使用atomic UTF-8 no-BOM writer。主代理
  `41 passed`；fresh Luna/high final2 `29 passed`，PowerShell parser PASS，P0/P1/P2=0。
  實體Windows runtime仍`NOT_RUN`。
- evidence：主代理合併回歸`113 passed`；fresh Luna/high r3 ordered/current `76 passed`、launcher
  `18 passed`、adversarial `10 passed`，P0=0、P1=0。
- `LDU-QUALIFICATION-BUILDER-SOURCE`: `completed`。strict evidence、canonical projection/table inventory、
  deterministic preview、direct-build-only atomic publish與current validator round-trip source已完成；主代理
  combined `162 passed`，fresh Luna/high r3 P0=0/P1=0。未建立任何qualification receipt。
- `LDU-FINAL-ENGINE-EVIDENCE-PRODUCER`: `completed`。final operation綁定canonical single-release identity、
  source/candidate dump與live readback、完整canonical table preservation、target-owned fresh zero-write及atomic
  no-overwrite已由root `127 passed, 1 skipped`與fresh Luna/high驗證；supporting evidence只寫ignored scratch。
- 1004/1005 published qualification有效；1006～1012已完成代表資料 preserve candidate、fresh bootstrap、strict
  evidence、canonical validator round-trip及qualification publish（payload digests `cdff9071…7429c`、
  `724e4118…c01a8`、`effa5acf…eec2`、`0e088fe3…5a54`、`b400945c…97f4`、`efb571b2…d333`、
  `fbe29795…0a60`）。exact 1003唯讀ordered plan已列出1004→1012完整順序及qualification exact狀態。
- Engine：1006～1012 `passed`；read-only plan gate `passed`；macOS normal no-auth API/React/required
  workers/Browser與owned cleanup `passed`；另一台實體developer acceptance `not_run`。因此總結仍為
  `DB_CHANGE_NOT_READY`。
- Fresh Luna/high final DB verifier確認source/candidate row count與fingerprint一致、1006～1012 validator exact及
  candidate current；其兩個P1（producer header超限、mysqldump `--events` privilege）已以root regression修正。
  Unix no-auth live-drift亦已修正：前端bypass、missing `.env` process values、DB port、owned child cleanup及
  required worker survival；後續再補MySQL container reuse、雙平台launcher與64字元／system-schema安全門。
  2026-08-28人工後續裁決已移除operator updater的`lu_test_*`名稱限制；qualification／rehearsal隔離規則不變。
  final root `204 passed, 1 skipped`，fresh R11 P0=0/P1=0；normal Browser已驗收。
- receipt：`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_ordered_chain_launcher_slice_receipt.md`。
  本slice另見`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_hproj_rpre_static_release_receipt.md`。
  1006 engine slice另見`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1006_engine_qualification_receipt.md`。
  1007 engine slice另見`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1007_engine_qualification_receipt.md`。
  1008 engine slice另見`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1008_engine_qualification_receipt.md`。
  1009 engine slice另見`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1009_engine_qualification_receipt.md`。
  1010 engine slice另見`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1010_engine_qualification_receipt.md`。
  1011 engine slice另見`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1011_engine_qualification_receipt.md`。
  1012 engine slice另見`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_1012_engine_qualification_receipt.md`。
  local no-auth runtime另見`03_追蹤清單與證據/evidence/2026-08-28_task96_ldu_local_noauth_runtime_receipt.md`。
  Windows supervisor source另見`03_追蹤清單與證據/evidence/2026-08-28_task96_windows_runtime_supervision_source_receipt.md`。
