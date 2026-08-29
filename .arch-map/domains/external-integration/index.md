# Domain: external-integration

## Responsibility
擁有內部 Access identity/security boundary 與 LINE webhook／identity／delivery transport composition；不擁有 Orders、Scheduling 或 Finance 的業務根事實。

## Subsystems
- `access` — admin authentication/session/actor/audit/security-alert boundary; path: `subsystems/access/index.md`
- `line` — LINE webhook、binding、LIFF/self-service transport 與 committed delivery; path: `subsystems/line/index.md`

## External relationships
- depends_on: owning business Domains — self-service/webhook action only invokes typed owner commands。
- outbound: committed provider delivery — external failure cannot rollback committed Domain transaction。

## Contracts
- `document/架構重整/01_規格基線/17_External_Integration_LINE_Access正式規格.md` — Access/LINE external integration contract
- `document/架構重整/01_規格基線/20_LINE客服與月嫂自助服務正式規格.md` — LINE customer/staff self-service contract
- `document/架構重整/01_規格基線/23_LINE身分管理與解除正式規格.md` — LINE identity lifecycle
- `document/架構重整/01_規格基線/25_Access_Control_Production_Cutover與External_Security_Alert正式規格.md` — Access production cutover boundary
- `document/架構重整/01_規格基線/26_LINE四大模組Eraser流程圖轉錄與驗收基線.md` — LINE module acceptance baseline
- `document/架構重整/01_規格基線/00_Global_共同契約.md` — Global actor/outbox contract

## Verification routing
- default_boundary: Domain
- test_root: `tests/domains/external-integration/`
- integration_root: subsystem-owned integration roots; see `.arch-map/tests/domains/external-integration/index.md`.
- remaining_layout_gap: selected flat Access/legacy Streamlit rollback tests only.
