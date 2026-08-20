# Phase 2C Candidate Change Inventory（重審）

Candidate root: `D:\project\Labor_union`。以下 SHA256 只作本次候選完整性證據，不作任務身分。

| Path | Bytes | SHA256 |
|---|---:|---|
| `ui_react/src/api/auth/session_client.ts` | 6812 | `8528c52673bbaba93a8178a2d22dfe8128e8f76192436935dbc855fe4f796ec3` |
| `ui_react/src/api/auth/two_step_auth_schemas.ts` | 2137 | `d057653ee44b6246ca3517d0db9b4c318f1712ca84fe294cff2d8c14b263766e` |
| `ui_react/src/api/auth/two_step_auth_errors.ts` | 1694 | `c4b2c753612240e7db8088656c9afc33801c6db057538f4a8b0ddc17c53d0df2` |
| `ui_react/src/pages/LoginPage.tsx` | 13995 | `27afc28ed86fb0f05910b041fef0d8fb5ddcd902d10c2da2ea5dcef4f014c140` |
| `ui_react/src/tests/session_client_two_step_auth.test.ts` | 23367 | `ec860cdb27cef99fa054ea27daef6cf4a3de1608158e7ee1dae9618362a80731` |
| `ui_react/src/tests/fixtures/auth/two_step_auth_contract_fixtures.ts` | 3166 | `2ff23ba9f3c7d9f55ed91edc0c5ab4b9a05115219e29c9fedaadf993c4674fea` |
| `ui_react/src/tests/LoginPage.test.tsx` | 29724 | `6c5eb3b55dd7e9da1fae8dedb528fd36ea34aeb782ae37306483da17d6d8dbdc` |
| `ui_react/src/tests/route_guard.test.tsx` | 7749 | `650b3bd16b435a89cc797fe8f4243c541b8b008216866f88030af6ab182c10e2` |
| `ui_react/src/tests/challenger_auth_navigation.test.tsx` | 16111 | `a5a1b255774b23092afd48bd5acdb8f6b818ff9afc6ef05a2fa43d9a2f871197` |

Integration re-audit also made two minimal build-compatibility corrections outside the Phase 2C Auth lane:

- `ui_react/src/api/orders/order_query_client.ts`: replaced a TypeScript parameter property rejected by `erasableSyntaxOnly`; no runtime contract change.
- `ui_react/src/tests/orders_mutation_client.test.ts`: aligned AdminPublic fixtures to the live schema.

No backend, DB, schema, migration, dependency or lockfile was changed in this re-audit.
