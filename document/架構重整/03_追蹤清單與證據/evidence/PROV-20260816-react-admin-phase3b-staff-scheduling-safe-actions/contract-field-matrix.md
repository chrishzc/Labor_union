# Phase 3B Contract Readiness Matrix

Status: `CONTRACT_MATRIX_FROZEN_WITH_BLOCKERS`  
Base: `main@8615225481c8f72a9629289285516189b270cb36`  
Date: 2026-08-16

| Flow | Query/Preview/Apply source | Typed contract | UoW/replay evidence | Frozen disposition |
|---|---|---|---|---|
| Staff selector | `GET /api/v1/staff/summaries`; `api/routes/staff.py` | `StaffSummaryPageView` exists | query only | `BACKEND/WRITE_SET_GAP`: Phase3B lacks a Staff bounded React client; MOCK_STAFF forbidden |
| Preferences | `api/routes/staff_matching_preferences.py:43-129`; schema `api/schemas/staff_matching_preferences.py:88-124` | success typed; errors raw `detail` | workflow fresh version/fingerprint/UoW/replay exists | `BACKEND_GAP`: typed error envelope + route tests absent |
| Availability | `api/routes/staff_availability.py:47-124`; schema `api/schemas/staff_availability.py:14-66` | typed success/error | fresh lock/replay/cancel event exists | `READY_TO_WIRE_WITH_G2_BLOCKER`: occupancy mutex equivalence and route evidence missing |
| Lifecycle | `api/routes/staff_retirement.py:24-50`; schema `api/schemas/staff_retirement.py:12-33` | error raw; view not extra-forbid; fingerprint not 64-hex constrained | workflow/repository replay/lock exists | `BACKEND_GAP`: public contract hardening + route tests required |
| Leave/Substitution | `api/routes/leave_substitution.py:63-195`; schema `api/schemas/leave_substitution.py:73-105` | impacts are `dict[str,Any]` | main transaction exists; linked leave request/outbox is second UoW | `BACKEND_GAP`: typed impacts and outer-UoW decision required |
| Substitute selector | no approved React Staff selector client | n/a | n/a | `WRITE_SET_GAP`; cannot use MOCK_STAFF |

## Frozen safety facts

- Availability actions: `create_long_leave|create_pause|end_pause|cancel`; cancellation is append-only, never DELETE.
- Preference Apply has no outbox and must not write assignments.
- Lifecycle React state must come from server; reactivation does not restore old facts.
- Leave Apply requires four expected versions, 64-hex fingerprint, reason, idempotency and correlation headers.
- `client_finance_impact`, `payroll_impact`, `orders_impact` cannot cross the client boundary as raw dict.
- Current Phase3B exact write set prohibits backend production and omits a Staff summaries client. Therefore no
  production writer is authorized until a revised exact Work Package is approved.

## UI collisions

| Path | Baseline bytes | SHA256 | Status |
|---|---:|---|---|
| `ui_react/src/pages/StaffPage.tsx` | 39462 | `4FDB7BD9A5C2AF60E74104771690AF1D446ED964DCA1F858FC04D369B9E738DE` | untracked user baseline |
| `ui_react/src/pages/StaffPage.css` | 1996 | `2A2D87339D01E434FC2EAA4617B815C5FD7A635C7F4BEA1B644CB61740B87872` | untracked user baseline |
| `ui_react/src/pages/SchedulingPage.tsx` | 66173 | `B77079FA68F826D5EB55E6240C93A9CEABDA224D730581332C9D279359254F69` | untracked user baseline |
| `ui_react/src/pages/SchedulingPage.css` | 7880 | `6CA7C7C40FB6E999C7DD50FD6761F27B484065BD3A707EFD905BB0EFAD60F1CB` | untracked user baseline |

