# Task 96 LDU local no-auth runtime receipt

- `package_id`: `LDU-1003-CURRENT-01`
- `scope`: macOS allowlisted exact-1003 zero-child gate＋current-1012 canonical no-auth runtime／Browser
- `status`: `passed`
- `database_effect`: zero schema／row mutation；既有MySQL container重用，未recreate／restart

## Runtime evidence

- exact-1003負向：official no-auth launcher回`schema_update_required`／exit 2；8000、5173 listeners前後不變；
  修正版重跑時`mysql_db` container ID與StartedAt前後相同。
- current正向：`lu_test_task96_ldu_candidate_1012_r1`通過`--require-current`，baseline 1003、latest 1012。
- launcher正向：明示`Reusing running MySQL container: mysql_db`；FastAPI 8000、React 5173 ready。
- required workers：runtime monitor、durable worker、incident worker皆持續呼叫private API並回200；LINE設定缺失
  依契約skip，未偽造provider成功。
- HTTP：`/health` 200、`/admin/`含`id="root"`、React relative proxy 200、no-auth`/admin/auth/me` 200。
- Browser：fresh reload直接顯示「開發模式管理員」，訂單管理讀到`T96-LDU-REP-001`；沒有登入頁，
  console `0 error / 0 warning`。
- cleanup：前一輪normal runtime收到Ctrl-C後exit 130，8000／5173均釋放；最終驗收runtime重新啟動並保留。

## Final verification

| Check | Status | Evidence |
|---|---|---|
| Root focused＋adjacent | `passed` | `204 passed, 1 skipped`；bash syntax、`git diff --check` PASS |
| Fresh Luna/high | `passed` | R11 `56 passed`，P0=0、P1=0；先前R9 manifest／雙平台launcher驗證問題均已修正 |
| Engine chain | `passed` | 1006～1012 qualifications exact；source/candidate代表資料count與fingerprint保留 |
| Local no-auth runtime／Browser | `passed` | current gate、API、React、proxy、required workers、Browser與cleanup如上 |
| 另一台實體開發機 | `not_run` | 仍須在該機以自己的exact-1003 DB執行backup→apply→current→Windows Browser |

## DB gate result

| Gate | Status | Evidence |
|---|---|---|
| Scope | PASS | approved spec／`LDU-1003-CURRENT-01` |
| Change inventory | PASS | schema-only；seed/backfill/destructive none |
| Static release | PASS | 51 manifests／101 artifacts；latest 1012 |
| Descriptor | PASS | per-release exact |
| Read-only plan | PASS | exact1003 ordered 1004→1012 qualifications exact |
| Engine verification | PASS | representative preserve＋fresh逐版＋current readback |
| Developer acceptance | NOT_RUN | 另一台實體機尚未執行 |

總結依規範仍為`DB_CHANGE_NOT_READY`；本機normal no-auth runtime／Browser slice已`passed`。
