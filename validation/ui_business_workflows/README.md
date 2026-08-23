# UI Business Workflow Validation

此目錄是 Part 00 指定的可重跑 UI 業務清單入口。清單只描述操作者可理解的業務步驟與可觀察 oracle；不建立業務規則、fixture root fact 或 runtime receipt。所有本階段結果初始為 `NOT_RUN`，真實登入、瀏覽器、API 與 DB 證據須由後續 bounded work package 產生。

目前建立 Part 04、Part 09、Part 14與Option A核准的Part 17 Data Browser。Part 17只驗收allowlisted、
server-masked Query／typed detail；source correction與entry cutover不在其owner boundary。
