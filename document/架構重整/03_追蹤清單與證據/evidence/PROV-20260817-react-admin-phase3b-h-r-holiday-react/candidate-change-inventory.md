# Phase 3B-H-R candidate change inventory

日期：2026-08-22

| Layer | Paths | Disposition |
|---|---|---|
| Typed API | `holiday_schemas.ts`、`holiday_errors.ts`、`holiday_client.ts` | strict Zod Query／Preview／Receipt與typed transport errors |
| Flow adapter | `holiday_flow_adapter.ts` | Query／Preview／Apply／receipt／re-query、stable retry identity與fail-closed states |
| Presentation | `SchedulingPage.tsx`、`SchedulingPage.css` | 既有Holiday tab接線；其他四個未核准controls維持native disabled |
| Tests | fixture、client、adapter、flow、no-fake-mutation五個test paths | 14 focused assertions |

0 API/Python/schema/migration/seed/backfill變更；既有DB只有GET與Preview。owned disposable DB僅本次scenario
Apply與精準cleanup。
