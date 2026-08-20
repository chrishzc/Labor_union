# Scheduling Query Page-Slice Contract Matrix

Status: frozen-for-local-candidate（2026-08-17）

| Boundary | Required public shape | UI disposition |
|---|---|---|
| `GET /api/v1/staff/summaries?page_size=20` | strict `id/name nullable/phone nullable/next_cursor nullable` | 只使用 id/name；phone 不 render |
| `GET /api/v1/scheduling/staff/{staff_id}/current-calendar` | strict staff/range/evaluated-at/assignments/days/case-versions/64-hex token | calendar `wired` |
| assignment | server lifecycle、assigned dates、service instants、counts、versions | 唯讀顯示；不推導日期／狀態 |
| day entry | closed occupancy kind、nullable case/assignment/lock/segment/unavailability identities | server enum → visual tone |
| auth | fresh memory bearer；enabled principal `require_admin` | 無 token 零 fetch |
| errors | Global typed envelope、public code、retryable、correlation | explicit error/retry；不降級成 empty |
| matching／precision | 無本包 typed projection／mutation | unavailable、native disabled |
| leave／substitution／holiday／inbox | 不屬本包 | tab 保留，全部 unavailable、native disabled |

Strict decoder 同時拒絕 missing required、wrong primitive、extra、invalid enum、duplicate day／identity、staff/range mismatch、invalid token 與 inconsistent `available`。

