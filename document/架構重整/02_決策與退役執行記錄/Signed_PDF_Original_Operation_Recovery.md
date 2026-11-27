# 已簽 PDF 原操作結果恢復

狀態：`in-progress`。Owner 為 Contract Signing Integration。完成條件為固定候選的正式 CI 證據與原操作成功／未明兩條路徑交付；未驗項目保留明確限制，不宣稱正式環境可用。

## Authority 與範圍

使用者要求人員人工確認簽署內容後歸檔 PDF，畫面逾時或斷線後重開案件能查明原操作，避免再歸檔一次。允許一張獨立 Draft PR，禁止正式資料、部署、合併及既有 #439 分支。本案從 `e3779d98a94c40693c11a8d40906d3dd14a85080` 起，唯一工作區為 `/tmp/lu-signed-pdf-pstack-cQsvmR/repo`，初始 detached HEAD 且 status 為空。

依 [任務治理](../00_Agent任務分級與交付規範.md) 列 T3，因新增 public Query 契約。此任務不改 owner、SSOT、schema、交易或外部效果。正式責任與驗收由 [Contract Signing §3.4、§3.5、§4](../../../.arch-map/requirements/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md) 擁有；未知結果的規則沿用 [Global §2.4](../../../.arch-map/requirements/00_Global_共同契約.md#24-管理端一次點擊送出與選填原因)。

## ADDED

同案與原 key 的唯讀結果查核。命中 committed 歸檔回執才表示原操作成功；miss 維持 unresolved。送出前保留同一分頁可恢復的操作定位資訊，不保存 PDF bytes 或檔名。未知結果只查詢，不自動重送。

## MODIFIED

原地同步 #21 的公開契約與 STAR 驗收。同步原有架構與測試導航。修正導覽誤述，固定版程式原已在同頁未知時先 GET，但 GET 回案件最新檔案，且 miss 後會重送，不能辨認原操作。

## REMOVED

移除管理端未知結果自動重送 POST 的接線。既有 POST 同鍵重播契約保留，不新增替代 writer。

## 設計與交接

Feature 採預設 Balanced，直接 how High，architect Low。How 已由獨立 explainer核對 existing source，不重跑其適用結論。Low 直接採現有資料結構，不啟多方案 arena。

使用者入口為案件「回收簽署文件」。正常送出一次 POST；逾時或卸載後重開，呼叫 client 的 `querySignedArchiveResult(caseNo, identity)`，其底層 GET 要求原 `Idempotency-Key`。正式命中顯示回執檔名；未命中或查詢中斷維持未明並鎖住新歸檔。案件最新檔案清單只表示案件層級事實，不能替代這次查核。

資料 shape 為 `committed + exact files` 或 `unresolved` 的 closed union，均綁定案件及原 key。持久瀏覽器資訊只含案件、操作人及命令識別。API 驗身分與 header，client 驗 response schema 及 case/key binding。Contract Signing 復用既有 repository 的 `signed_archive(case_no, key)`，不建立新 SQL／儲存表。查詢不 stage、不 Apply、不 commit。原 POST 的 actor／內容 fingerprint 相等規則保留。

原操作回執的三類正式紀錄仍由原 outer UoW 提交。這次沒有更動持久寫入契約，fake port 的唯讀測試不宣稱證明 MySQL 回滾。

四項 throughput checkpoint：
- Blocking first steps。先固定版本、讀 owner／global 契約與確認 API readback 的缺口。
- Independent workstreams。單一 implementation owner 寫相關程式與 focused tests；coordinator 只寫 owner 文件、導航及 CI，避免共享寫入。
- Shared mutable state。原操作按案件與操作人保存，未知時鎖定新歸檔。交易 writer 維持原 owner，不新增序列化框架。
- Smallest safe decomposition。一個 coupled feature 由一位實作者負責，不為 PM、前端、後端、DB 各造文件或代理。

## 適用驗收與證據

- 原操作 committed 後丟失回應，重開／重新整理以原 key GET 顯示原檔名，POST 總數一筆。
- 原回執 miss、查詢失敗、另一操作已有案件歸檔，均維持原操作未明且不新增 POST。
- 跨案件晚回應不能污染新案件；無法保存定位資訊時不先送出。
- API 沿用 persisted admin；缺原 key、錯案件、錯回應綁定不得被當成功。
- 沿既有 Vitest 與 pytest 入口在 GitHub CI 執行。既有測試根由 Archmap leaf 與測試 routing 指定，不新建測試目錄。

當次 CI 的 head、base、checkout SHA、run／attempt、job 與報告連結置於 Draft PR。實作前沒有執行專案測試檔。CI 綠勾不取代案例清單；受影響的 Python／前端案例報告另存 artifact。

## 精確限制與 owner 待決

- 原請求查無回執可能仍在執行。維持未明是既有規則，不用逾時秒數推定失敗。若要提供「放棄原操作並開始另一筆」，Contract Signing owner 須定義可證明原操作不會提交的解除條件；本案不猜等待時間或自動過期值。
- 本案恢復只涵蓋同一分頁持有原操作識別的案件重開與重新整理。跨裝置、關閉分頁後失去定位資訊與歷史沒有原 key 的操作，需要 owner 另定產品保證；既有案件文件清單仍可查閱，但不能宣稱精確歸因。
- 不修改生產、部署、正式資料、通知或 provider。未做正式瀏覽器／MySQL 驗收，不把 fake port 或 Vitest 寫成正式環境 E2E。

## 實際技能來源與宿主限制

固定 pstack 來源為 `chrishzc/personal_tips@03fffdb6b6f3ff595959f027e0511acbd95123f3`，根 `marketplaces/personal/plugins/pstack`。匿名 clone 失敗，改用 connected GitHub 按該 commit 讀原文，手動輸入副本在專用 /tmp 的 `pstack-inputs`。未安裝候選版、未改全域設定，未把 Markdown 讀取當原生 agent 註冊。

宿主原生提供的 pstack metadata 清單只有 `pstack:precise-query`、`pstack:setup-pstack`、`pstack:unslop`，無固定 commit provenance。當次最初以 skills.read 手動讀了原生套件 `c0/precise-query` 的正文；此讀取不算固定候選版驗收。後續所有 pstack 規範均為手動讀取固定來源，沒有證明宿主隱式選用 poteto-mode 或跨角色 playbook。

已手動讀取的固定文件，PERSONALIZATION 與宿主對照只採本案適用段落：
- `README.md`、`PERSONALIZATION.md`、`docs/harness/codex.md`。
- `skills/poteto-mode/SKILL.md`。
- `skills/poteto-mode/playbooks/feature.md`、`cross-role-handoff.md`、`opening-a-pr.md`。
- `skills/how/SKILL.md`、`skills/how/references/explainer-prompt.md`、`skills/precise-query/SKILL.md`。
- `skills/architect/SKILL.md` 及 `references/runner-prompt.md`、`design-red-flags.md`、`rationale-template.md`。
- `skills/principle-model-the-domain/SKILL.md`、`skills/principle-type-system-discipline/SKILL.md`、`skills/typescript-best-practices/SKILL.md`、`skills/principle-prove-it-works/SKILL.md`。
- `skills/technical-writing/SKILL.md`、`skills/unslop/SKILL.md`、`skills/no-comments/SKILL.md`。
- CI lint 訊號後讀 `skills/correct/SKILL.md` 及 `skills/correct/references/lint-capture.md`。
- 實作者另讀 `agents/poteto-agent.md`；註解審閱讀 `agents/comment-sicko.md`。
- `skills/principle-prove-it-works/references/architecture-closure.md`。
- 同一來源 repository 根的 `governance/pstack-models.md`。宿主 `<CODEX_HOME>/pstack-models.md` 不存在，未複製該設定；當次派工依已讀 owner profile 明示指定。

實際環境 Linux 6.18.57 x86_64，Node v24.22.3，CLI 顯示 codex-cli 0.172.0-alpha.2。本任務為 hosted Codex，CLI 版本不冒充 hosted runtime 版本。Windows、macOS 與候選原生安裝均未驗。所有原生 delegates 共用 root speed。

既有 Antigravity executable 與 Origin 未找到。GitHub CLI 未登入，外部 PR 操作使用已連線 GitHub tools，不啟新登入。不把缺少跨家族服務或 `cursor-team-kit/deslop` 當通過。正式固定測試由使用者要求的 GitHub CI 執行，不在本機改走另一個代理跑測試。

## 專案文件來源

以下均從 Labor_union 固定基準 `e3779d98a94c40693c11a8d40906d3dd14a85080` 手動讀取，本 PR 的原地同步另由 diff 辨認。未從其他任務分支取得契約。

- `README.md`、`AGENTS.md`。
- `document/架構重整/00_Agent任務分級與交付規範.md`、`00_規格書撰寫與生命週期規範.md`。
- `.arch-map/domains/contract-signing/subsystems/contract-signing/modules/external-signing-presentation.md` 與相同相對路徑的 `.arch-map/tests/` routing。
- `.arch-map/requirements/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md`、`00_Global_共同契約.md` 的人工操作與 concurrency 段落、`30_Controlled_File_Storage正式規格.md` 的正式 metadata／Apply／readback 段落。
- `scripts/scripts_map.md` 與 `.github/workflows/candidate-pool-frontend.yml`、`python-app.yml` 的適用 CI 段落。
- `document/架構重整/02_決策與退役執行記錄/README.md` 的工作包治理與索引，未開啟其列出的其他任務。

## 審閱與驗證限制

註解審閱由非作者 Terra 6.1 medium 完成，針對本次新增／實質修改行，建議刪除 0，無新增抑制設定。這只表示註解範圍結果，不代替語意與 runtime 驗證。

Antigravity executable 缺少且未開始任何遠端工作，依 owner profile 採單次 native Sol 6.1 high fallback 做獨立語意審閱。不同 GPT 型號仍屬同家族，cross-family 為 `not_run`。沒有更換 provider、安裝工具或改權限。

Archmap entry 未列於宿主技能清單，按專案允許的 filename-only fallback 讀到既有 leaf 與明定 test roots。原生 Archmap 查詢為 `not_run`。專案未找到相容的架構 closure validator，固定 pstack 的 closure 原文已讀；沒有把手動路徑同步稱為 structural validator 通過。

專案未配置 Pyright／Ruff 等 Python strict type／lint 入口。沿原 CI 做 Python 語法與 pytest，這不等於 Python strict type／lint 通過。前端沿既有 `npm run lint` 與 `npm run build` 的 TypeScript 檢查，結果以正式 CI 為準。

非作者獨立語意審閱為 no findings，檢視的 tracked diff SHA-256 為 `0f3ba0f9ca5655ff92576b0b58077b1a9800e5eb2a96f1071370210ee5fc4801`，未追蹤 adapter SHA-256 為 `b3de1794cb6130d0ee7751e846621a43d6869d34002a2253e36420672ef3240a`。後續只補上傳尚 pending 就離頁的 UI regression，由 coordinator 讀回該新增案例；production source 沒有改動。CI 預設檢查 PR merge checkout，報告保留實際 head、event base 與 checkout，不能將 merge SHA 寫成 head SHA。

Lint capture 沿既有 `ui_react/.oxlintrc.json` 與 `npm run lint`，沒有另造 Markdown 規則清單或調低 severities。第一輪 CI 發現元件初始 effect 讀取 `revision` 而 dependency 未列出的既有 warning；固定基準已有相同 effect。該規則已由 ordinary lint 入口報告，無需新增設定。本案保留既有 revision／受保護操作的重讀契約，未擴張為相鄰 effect 重構；不把 exit 0 寫成零 warning，也未宣稱額外負向 lint mutation 驗證通過。

## 範圍例外

修測試代理首次 shell 盤點忘記設定 workdir，在初始 `/workspace/scratch/7f3a2434cb56` 執行 AGENTS 檔名 inventory，輸出其他路徑名稱。沒有開啟那些檔案內容或取得其他任務契約；該盤點沒有延續，後續來源讀寫均限定專用 /tmp。此項不算完整隔離執行通過，亦不影響本案未存取 #439 分支、未改正式資料與未部署／合併的事實。
