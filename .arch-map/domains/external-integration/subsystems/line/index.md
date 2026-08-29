# Subsystem: line

## Parent
- domain: `external-integration`

## Responsibility
處理 LINE webhook、identity binding/review、LIFF/self-service transport、rich menu／message delivery 與 committed delivery worker composition；business mutation 回 owning Subsystem。

## Dependencies
- outbound: `scheduling | case-import | orders | other owning domains` — typed commands only。
- outbound: external LINE provider — only after committed durable intent/outbox when side effect is required。

## Contracts
- `subsystems/line/` — LINE application workflows
- `line/` — LINE transport/provider adapter root
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — self-service contract
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` — identity contract

## Verification routing
- default_boundary: Subsystem
- test_root: `tests/line/` (`layout_gap`: not yet under architecture-owned external-integration path)
- integration_root: unknown.
