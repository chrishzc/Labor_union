# Contract Signing — 獨立提醒與管理端版面

狀態：completed。CS-R1～CS-R7 均 passed；99 項後端及 55 項前端 focused tests、build、桌面／手機實際元件 Browser 驗證、diff check 與 architecture closure 通過。Browser 使用合成 API 回覆，provider delivery／production 操作 not_run，且不屬本次驗收範圍。

Authority：2026-10-15 使用者確認 UI 預覽並要求實作；語意以 `../01_規格基線/21_Contract_Signing_Commitment與正常驗收資料鏈正式規格.md` 的「2026-10-15 管理端獨立簽署提醒與歷史修復區塊移除」為準。

Owner：Contract Signing subsystem。用途：串接已授權的 API、交易、受控通知與 UI 驗收；完成本 slice 的必要驗收即關閉，不衍生後續改善。

## 範圍

- 修改既有 external-signing workflow、composition／route、repository／notification port、typed client、per-case mutation store、管理端元件與其樣式。
- 沿用既有 Subsystem integration tests、external-signing-presentation UI tests 及對應 map leaf。
- 保留既有 dirty 成果與測試跳過功能；不新增 migration，不操作目前案件、LINE provider、外部簽署平台或部署，不刪除歷史資料／compatibility API。訊息文字與外部郵件時序交後續需求。

## 必要驗收

| ID | Observable claim | Verification |
|---|---|---|
| CS-R1 | 新交接完整檢查文件但零 reminder task；無 LINE 綁定亦可交接 | focused workflow／API／UI |
| CS-R2 | 獨立確認後一次涵蓋客戶與所有月嫂，未綁定對象提示人工通知 | workflow adapter／API／UI／Browser |
| CS-R3 | fresh-lock／typed stale、closed state、persisted actor；提醒 receipt 與 tasks 同一 commit，重播零重送 | workflow／API |
| CS-R4 | 提醒不推進簽約版本、不清除文件 Preview；逾時與 remount 保留原 identity | workflow／UI |
| CS-R5 | 歷史修復區塊與其背景查詢不存在，舊交接及最後提醒結果可回讀 | parser／API／UI |
| CS-R6 | 測試跳過、分開回收及 final completion regression 維持 | final-document／API／UI／Browser |
| CS-R7 | 已核准版面、確認視窗及手機版無溢出；build／diff／architecture closure 通過 | Browser／build／validators |

停止條件：上述驗收通過；無 production 或 provider effect 驗收需求。最終結果於交付訊息記錄，不建立重複 receipt。
