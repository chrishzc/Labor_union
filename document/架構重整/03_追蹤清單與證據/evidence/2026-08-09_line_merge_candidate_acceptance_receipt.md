# LINE Merge and Candidate Schema Acceptance Receipt

## Merge boundary

- Local architecture and retirement governance remain authoritative.
- Remote LINE identity, review, configuration, Rich Menu, delivery task,
  order-group, monitoring, matching and Knowledge runtime functions remain
  mounted through typed API or worker boundaries.
- BreezySign remains retired. Orders expose provider-neutral
  `contract_identity` and contract context only.
- Static LINE role mapping is not authorization authority; effective access is
  resolved from database capability grants.

## Entry-point adjudication

The regenerated queue contains 348 adjudicated entries:

| Kind | Count |
|---|---:|
| API | 297 |
| CLI | 44 |
| UI | 7 |

Final statuses are 303 `active`, 44 `operator_only`, one `retired_410`, and zero
`review_required`. The retired HTTP entry is retained only as a typed legacy
boundary with a documented replacement.

The remote merge added 41 entries and removed 10 superseded entries. All 41 new
entries were reviewed against their concrete source boundary: 12 Knowledge API,
11 LINE identity API, three LINE configuration API, three LINE order-group API,
six runtime-health API, one matching-decision API, and five controlled operator
CLI entries. Each remains required by a mounted route, canonical worker or
release/monitoring operation, so the decision is 36 `active` API entries and five
`operator_only` CLI entries.

The 10 removed entries are replacements, not lost functions:

- the old Knowledge `answer`, `sources` and `{item_id}` paths are represented by
  the governed `questions`, `items` and `items/{item_id}` contracts;
- the old generic LINE `review-requests` paths are represented by canonical
  `line/identity/reviews` list, detail, summary and decision contracts.

The queue generator no longer promotes newly discovered entries automatically.
Future discoveries remain `review_required` until an explicit decision is stored,
and the release test rejects any queue containing an unreviewed entry.

## Isolated candidate acceptance

Acceptance used disposable database `lu_test_merge_candidate_20260809` on an
isolated local MySQL container. It did not read or modify the operational
`mysql_db` container or any other deployment environment.

- Bootstrap applied the base schema and ordered schema parts through
  `164_line_rich_menu_preview_bridge.sql`.
- Replaying the complete bootstrap succeeded without duplicate or drift errors.
- Restart followed by read-smoke confirmed the candidate database remained
  readable.
- Canonical LINE inbox, delivery, identity, Knowledge runtime, Rich Menu preview
  bridge and append-only Knowledge triggers exist.
- Retired `faq`, `crawler_logs`, `staff_availability`, generic data-browser audit,
  BreezySign/provider tables, `orders.contract_id` and
  `order_before_snapshot` were absent after both bootstrap runs and restart.
- `orders.contract_identity` is present.

This is a local dry-run acceptance only. Applying the release to another
environment requires separate authorization.

## Verification

- Full suite: `1473 passed, 61 skipped`.
- OpenAPI smoke: 274 paths; the remote LINE and Knowledge capability groups all
  remain represented.
- Entry queue generator: 348 entries, zero `review_required`.
- Release manifests and schema gates cover the ordered local history through
  schema part 164.
