# Module: staff-matching-preferences

## Parent
- domain: `scheduling`
- subsystem: `scheduling`

## Responsibility
維護既有 typed Staff matching preference definitions／profile 及比對；不將顯示標籤視為規則。NAS profile 縮減透過 fixed-purpose 程序，保留原本 owner version 與 outer transaction。

## Implementation
- model: `domains/scheduling/staff_matching_preferences.py`
- workflow: `subsystems/scheduling/staff_matching_preference_workflow.py`
- adapter: `infrastructure/mysql/staff_matching_preference_repository.py`
- transport: `api/schemas/staff_matching_preferences.py`

## Contracts
- 同一人員穩定 identity lock、profile version、typed values 與 exact replay；不是 Staff 六種靜態 relation 編輯 owner。
- NAS 刪除只移除該人員、該 profile version 未保留的 values；定義型別、preview 與 fingerprint 沿用原 workflow。

## Verification
- layout_status: `custom_current`
- layout_basis: 既有 focused owner regression 檔直接驗證 typed values、preview/apply、replay 與 stale；本次不搬移既有測試。
- test_root: `tests/test_staff_matching_preferences.py`

## Provenance
- source_observed: 上述 model／workflow／adapter 及既有 focused tests。
- architecture_declared: 使用者核准 P04 保留既有偏好縮減功能並限制 DB DELETE。

## Change triggers
Reconcile when value kinds、profile version、persistence delegation 或 test root changes。
