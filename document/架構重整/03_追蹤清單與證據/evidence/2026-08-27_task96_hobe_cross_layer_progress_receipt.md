# Task 96 WP-HOB-E 跨層進度 receipt

- `date`: `2026-08-27`
- `scope`: `WP-HOB-E / SP2-Q owner-terminal fresh Query → projector → API → React → Browser`
- `status`: `passed`（cross-layer candidate）；WP-HOB-E整包仍`in-progress`
- `authority`: `SP2-Q_APPROVED / NO_DB_CHANGE`
- `runtime_profile`: `APP_ENV=development`、`ACCESS_CONTROL_PROFILE=local_bypass`、
  `ENABLE_ADMIN_AUTH=false`、`VITE_ACCESS_CONTROL_PROFILE=local_bypass`
- `database_target`: `lu_test_task96_fin_browser_human_20260827`；零DB寫入

## 1. 交付結果

1. 新增fresh HOB-E projector；Step 11與歷史警示只在三owner terminal roots全部成立時一起完成。
2. 新增`GET /api/v1/orders/{case_no}/historical-completion`、typed Pydantic view與單connection依賴組裝；
   route沿用既有歷史案件補正權限dependency，local bypass僅用於本次開發驗收。
3. 新增strict Zod client與React Step 11 panel；raw owner payload不穿透render，缺根事實顯示精確
   owner、field與referral。
4. Orders與Staff MySQL UNION修正為一致欄數；Staff payout identity cast明確統一utf8mb4 collation。
5. 已知Scheduling integrity gap保持`BLOCKED`且指向`scheduling.official_service_facts`；只有真正
   read/query failure才是`UNAVAILABLE`。
6. API把owner／source versions輸出為canonical decimal string，避免signed BIGINT經JSON.parse落入
   JavaScript number後超過`2^53`失真。

## 2. DDH independent verification

- r15 fresh Luna High：SP2-Q source candidate `valid=true`，`128 passed`。
- r16 fresh Luna High：跨層candidate `valid=false`；發現Scheduling referral被generic unavailable壓掉，
  以及BIGINT version使用JavaScript number兩項material defect。
- 主代理依finding修正並新增反例測試。
- r17 fresh Luna High evidence：Python `137 passed`、React `4 passed`。
- r17 fresh Luna High verifier：`valid=true`，無finding；確認精確Scheduling referral、lossless version、
  typed route、projector同步、no false completion、raw dict guard與headers。
- DDH native terminal：`status=passed`、`ready_for_integration=true`；plan digest
  `acee73baffe2f9830e6e3d4e48671dff51b42234c06c91935a7a7feb249bc9c8`，receipt digest
  `8eff18fa3148eda75ae3088fc207ca0549016e10e60976fcaeecdc382e25866b`。

## 3. Browser與runtime evidence

- in-app Browser以no-auth development local bypass載入`http://127.0.0.1:5173/admin/`。
- `AP-DURABLE-1` Step 11顯示未完成；known Scheduling gap顯示「排班管理」與
  `scheduling.official_service_facts`；Client Finance與Staff Payables各自維持owner referral。
- Staff readback不完整時aggregate為`UNAVAILABLE`，沒有誤標完成；Browser console error／warning為`0`。
- 這是no-auth development負向／unavailable驗收，不是enabled persisted-human authentication PASS。

## 4. Formal command runtime blocker

唯讀掃描既有`lu_test_*`未找到同一case三owner均terminal的F-04正向案例。最接近的
`AP-DURABLE-1`仍缺Orders actual start／completion lineage、有效Scheduling service-time facts、Client
Finance結清與Staff Payables完整bank／allocation／projection roots。現有E2E測試會直接植入多個derived
roots，不能取代正式decision→commitment→waiting lock、deposit及owner commands的可重播證據。

因此：

- 正式command建立F-04正向runtime：`blocked`
- F-04正向Browser：`blocked`
- WP-HOB-E package completion：`in-progress`

本輪沒有為了湊正向案例寫DB、重設資料庫、操作`union_db`、執行migration／DDL或使用Graphify。

## 5. 驗證摘要

| Gate | 結果 | 證據 |
|---|---|---|
| Focused Python | `passed` | 7 files，`137 passed` |
| Focused React | `passed` | HOB-E＋OrderTracker 4 files，`23 passed` |
| React build | `passed` | `tsc -b && vite build`；僅既有chunk-size warning |
| Python compile | `passed` | HOB-E source／API／adapters |
| Real MySQL read-only | `passed` | Orders／Staff SQL均由真`lu_test_*` engine解析；零寫入 |
| DDH fresh verifier | `passed` | r17 Luna/high，`valid=true` |
| Browser no-auth negative | `passed` | 精確owner referral、no false completion、console 0 |
| Formal command F-04 positive | `blocked` | 缺可重播同案正式根事實 |

## 6. DB change gate

| Gate | Status | Evidence |
|---|---|---|
| Scope gate | `PASS` | SP2-Q人工已核准且WP-HOB-E write set涵蓋API／React；不含DDL |
| Change inventory | `PASS` | schema-only／system-seed／business-row-backfill／destructive均N/A |
| Static release gate | `PASS` | N/A；沒有schema／release變更 |
| Descriptor gate | `PASS` | N/A；沒有owned DB object變更 |
| Read-only plan gate | `PASS` | N/A；沒有migration plan |
| Engine verification gate | `PASS` | N/A for DB change；另有真MySQL唯讀功能證據 |
| Developer acceptance gate | `PASS` | N/A；沒有本機DB upgrade |

總結：`SP2-Q_APPROVED / NO_DB_CHANGE`。

## 7. 2026-08-27 F-04 formal runtime與Browser final addendum

本節以較新的final evidence覆寫本receipt §4～§5所記錄的F-04 blocker；保留舊段落作為當時事實。

- canonical acceptance DB：`lu_test_task96_scenarios_20260827`
- runtime profile：`APP_ENV=development`、`ACCESS_CONTROL_PROFILE=local_bypass`、
  `ENABLE_ADMIN_AUTH=false`、`VITE_ACCESS_CONTROL_PROFILE=local_bypass`
- scenario：`HOB-F04-ROUTE-A-001`／case `115960401`
- data policy：root fixture只含synthetic source／external facts；derived status、alert、receipt、outbox皆由正式
  Query／Preview／Apply與durable worker建立；scenario rows明確保留供Task 96後續重播與跨頁驗收。

### Final runtime readback

正式runner已可重播至stage-07-settled。HOB-E API回讀：`state=completed`、
`step_11_status=completed`、`step_11_completed=true`、
`historical_alerts_completed=true`、`active_alerts=[]`；Orders version 5、Client Finance version 5，
Staff Payables source vector保留immutable Payroll obligation、payout event／allocation／bank fact與terminal
payable projection lineage。source fingerprint為
`af3756e3f4f703868b01242244681f6f21bbac5c160a3bfe62fb39add3f0cb19`，projection fingerprint為
`d0ccebebffa0fe91ec3b0beec2ded62408548b6529e9069474bbc201c1c552f2`。

Browser先發現HOB-E panel掛在只查`unfinished`的OrderTracker，導致terminal completed case不可達；該candidate
因此失效。最小修正保留預設`unfinished`，新增明確「包含已完成案件」控制；只有勾選後，Orders summary與
stage projection才一起切換`all`。canonical Browser驗收顯示case `115960401`位於第7階段、訂單完成、
Step 11完成，三個獨立結清投影（服務履約、客戶款項、月嫂薪資）均完成；console error／warning為0。

### Final verification

| Gate | 結果 | 證據 |
|---|---|---|
| Formal Route A replay | `passed` | `scripts/run_task96_hob_route_a.py`同scenario重播並回傳terminal HOB-E |
| Focused Python | `passed` | final candidate `141 passed` |
| Focused React | `passed` | HOB-E＋OrderTracker三檔`20 passed` |
| React build | `passed` | production build成功；僅既有large-chunk warning |
| Canonical MySQL/API | `passed` | case `115960401` completed、active alerts 0 |
| Browser no-auth positive | `passed` | completed opt-in→第7階段→Step 11／三owner terminal；console 0 |
| DDH fresh Luna High | `passed` | r4 evidence＋independent verifier皆零workspace effect，`valid=true` |
| DDH reconciliation | `passed` | plan `8dd43b5812da2c7e38a58c42d39533aa2097ab6d40f7e8521d876ee39c9832e6`；receipt `8b3aa2482d1eabb5eabdc89a7d6080777db15d66886722c66262caa81dcad860` |

WP-HOB-E更新為`completed`。WP-HOB-F只完成F-04 slice，其他H／R／C／A scenario仍各自保留
`in-progress`；不以本案例代替其acceptance。沒有schema／migration變更，DB change gates維持N/A；未操作
`union_db`、production、provider、reset／replacement／`--switch`或Graphify。
