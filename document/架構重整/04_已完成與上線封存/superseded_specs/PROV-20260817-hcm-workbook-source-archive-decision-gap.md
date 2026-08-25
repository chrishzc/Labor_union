---
doc_type: gap-package
declared_status: superseded
identity: PROV-20260817-hcm-workbook-source-archive-decision-gap
date: 2026-08-17
owner: Case Import / Privacy / Operations
domain: Case Import
source_gap: PROV-20260816-react-admin-phase4a-hcm-backend-transaction-receipt-gap
successor: PROV-20260817-case-import-workbook-policy-decision
---

# HCM workbook source archive 決策缺口

## Resolution（2026-08-23）

人工已在combined successor exact採用Option A：HCM Current原始workbook為Apply必要archive，採content digest
immutable identity、受控operator讀取、archive-first／0-write failure、DB rollback compensating delete與
delete-failure operational anomaly。retention期間、encryption及production provider仍是deployment target
configuration gate，不由developer-local adapter決定。

本gap因此`superseded`；此resolution不授權backend、storage provider、schema／DB或React Apply。

## 0. 需要人工決定的原因

正式 Case Import 架構包含 SourceArchive port，但目前沒有對 HCM `.xlsx` 原始檔的保存位置、retention、
加密、讀取權限、刪除與DB rollback補償政策。這是隱私與external-storage裁決，不能由實作者沿用temp file、
合約archive或任意local folder。

## 1. Option A（推薦）

原始 workbook archive 是 Apply 必要前置：

1. archive以content digest為immutable identity；只允許Case Import受控operator讀取。
2. archive寫入/完整性失敗時Apply為unavailable且0 DB write。
3. archive成功後若DB outer transaction rollback，執行compensating delete；delete failure產生operational anomaly，
   不得偽造Domain commit。
4. receipt只保存digest／archive reference的去敏identity，不回原始檔內容或本機path。
5. retention、encryption與production storage provider在deployment前另行配置；developer-local adapter不能成為
   production唯一實作。

## 2. Option B

本期明確不保存原始workbook，只保存digest與去敏review evidence。採用此選項前必須同步修正正式
Case Import規格對SourceArchive port的requirement，不能只在implementation跳過。

## 3. Activation gate

Phase 4A-H backend Apply工作包須在exact approval中同時寫明採用A或B。未裁決前HCM Apply維持
native disabled；local temp file、browser File object或測試fixture都不是archive evidence。

## 4. DB gate

本文件無DB變更。所有DB gates除Scope `PASS`外為`NOT_RUN`；結論`DB_CHANGE_NOT_READY`。
