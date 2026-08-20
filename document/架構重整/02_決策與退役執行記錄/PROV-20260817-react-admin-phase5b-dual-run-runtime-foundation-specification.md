---
doc_type: implementation-specification
declared_status: proposed
identity: PROV-20260817-react-admin-phase5b-dual-run-runtime-foundation
date: 2026-08-17
owner: Global Deployment / Developer Experience
authority: awaiting-exact-human-approval
approval_required: 核准此 exact Phase 5B Work Package
prerequisites: PROV-20260817-react-admin-phase5a-entry-governance-rollback PASS
base_branch: main
base_head: late-bound-at-approval
dirty_baseline: integration-owner-must-capture-before-writer
base_drift_rule: launcher, preflight, smoke or React runtime boundary drift requires fresh read and re-freeze
db_change: none
---

# React Phase 5B：最小三服務 dual-run foundation 規格

## 1. 目的與完成上限

Phase 5B只建立本機三服務並行foundation：

```text
FastAPI  127.0.0.1:8000
Streamlit 127.0.0.1:8501
React/Vite 127.0.0.1:5173
```

同一受控launcher必須啟動三服務、逐一驗HTTP health、記錄owned PID，並在失敗／結束時只清理由本次
launcher建立的process tree／process group。

本規格不切entry、不改default navigation、不建立production hosting、reverse proxy、CSP或SPA artifact，
也不retire Streamlit。完成上限為`local-three-service-foundation-validated`。

## 2. Frozen runtime contract

### 2.1 Commands and ports

- API：專案Python執行`-m uvicorn api.main:app --host 127.0.0.1 --port 8000`。
- Streamlit：專案Python執行`-m streamlit run ui/app.py --server.address 127.0.0.1 --server.port 8501`。
- React：在`ui_react`執行`npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`。
- 三個ports任一已被未知process占用，必須在第一個child process前fail closed；不得自動漂到5174。
- Windows只終止owned PID tree；Unix只終止owned process group。不得掃port後殺未知process。

### 2.2 Independent health

| Service | Ready predicate |
|---|---|
| API | `GET http://127.0.0.1:8000/health`回200 |
| Streamlit | `GET http://127.0.0.1:8501/_stcore/health`回200 |
| React | `GET http://127.0.0.1:5173/`回200、HTML content type且body含`id="root"` |
| React proxy | 經`http://127.0.0.1:5173/api/...`取得backend預期response；browser不得直連8000 |

任一服務失敗只回報該服務，不能用API healthy推定整體online，也不能以TCP open／build成功冒充React ready。

### 2.3 Relative API boundary

React production dependency closure只能使用relative `/api`。`ui_react/src/api/client.ts`中的absolute
`http://localhost:8000`／`127.0.0.1:8000` fallback必須移除；不得藉機復活generic import endpoint、修改
Vite config或增加CORS wildcard。

## 3. Data and side-effect boundary

此foundation的smoke是GET-only runtime驗證：

- 可連開發者既有DB，只能透過既有authenticated/read-only GET頁面觀察；不建立fixture、不seed、不repair、
  不migration、不reset、不執行POST／PUT／PATCH／DELETE。
- 不要求`LABOR_UNION_TEST_MODE=1`、`DB_DATABASE=lu_test_*`或
  `LABOR_UNION_TEST_MYSQL_DATABASE`；不得因缺少disposable DB阻擋三服務啟動。
- smoke固定不啟動`run_service_monitor.py`，因此不寫runtime observation、不建立LINE alert intent。
- LINE delivery、durable job、incident、knowledge、outbox、consumer、provider及所有optional workers在smoke
  固定disabled；不得連真provider。
- dry-run固定0 process、0 Docker、0 DB/API call，只輸出三個planned commands、ports、health predicates與
  disabled workers/monitor清單。

Normal developer launcher既有monitor／worker政策不由本包擴張；Phase5B acceptance只使用受控三服務profile。

## 4. Failure and cleanup behavior

1. Preflight先驗Python、uvicorn、streamlit、npm、`ui_react/package.json`、React entry files與三ports。
2. 依API→Streamlit→React順序啟動；每步ready後才進下一步。
3. 任一步spawn／health／proxy失敗，立即清理由本次run已建立的children，保存最小log並非零退出。
4. 每次smoke使用唯一`scratch/phase5b-dual-run/<run-id>/`，不得覆蓋或刪除使用者既有log。
5. 正常完成同樣清理owned children；不得讓monitor／worker殘留。

## 5. Exact implementation boundary

允許修改：

- `scripts/launcher_preflight.py`
- `scripts/launchers/start_local_development.bat`
- `scripts/launchers/start_local_development.sh`
- `scripts/smoke_local_development_launcher.py`
- `ui_react/src/api/client.ts`（只移除absolute origin fallback）
- `scripts/launchers/README.md`
- 對應focused tests與Phase5B evidence

只讀／禁止修改：

- `scripts/run_service_monitor.py`、Private Operations、LINE alerts、worker/provider modules。
- `api/main.py`、Vite config、shared transport/Auth、package/lock、business pages、entry registry／queue。
- DB/schema/migration/seed/backfill、production hosting與Phase6 files。

## 6. Acceptance gates

| Gate | PASS condition |
|---|---|
| G0 Scope | exact approval、dirty preservation、0 DB/monitor/provider write |
| G1 Dry-run | 三服務exact commands/ports/health＋disabled monitor/workers；0 process/DB/Docker |
| G2 Preflight | artifacts與ports在spawn前fail closed；不要求`lu_test_*` |
| G3 Runtime | 8000/8501/5173依序ready；partial failure只清owned PID/group |
| G4 React | HTTP HTML/root marker＋relative `/api` proxy；0 absolute8000 browser fallback |
| G5 GET-only smoke | existing DB只GET；0 non-GET、0 monitor observation、0 provider/worker |
| G6 Cross-platform | Windows/Unix service matrix一致；缺真Unix runtime時明列evidence blocker |
| G7 Static | focused tests、build/lint、UTF-8/header/diff/secret/write-set全PASS |

## 7. DB gate

| Gate | Status | Reason |
|---|---|---|
| Scope／Change inventory | PASS after exact approval | 0 schema/seed/backfill/destructive；smoke GET-only |
| Static release／Descriptor／Read-only plan／Engine／Developer acceptance | NOT_RUN | 無DB change或DB fixture |

結論：`DB_CHANGE_NOT_READY`。這不阻擋三服務GET-only foundation，也不授權任何DB／monitor mutation。

