# Module: profile-change

## Parent
- domain: `clients`
- subsystem: `client-profile`

## Implementation
- `domains/clients/profile.py`
- `subsystems/client_profile/`
- `infrastructure/mysql/client_profile_repository.py`
- `infrastructure/mysql/client_profile_binding_port.py`
- `api/dependencies/client_profile.py`
- `api/routes/client_profile.py`
- `api/schemas/client_profile.py`
- `subsystems/client_profile/registry_query.py`
- `infrastructure/mysql/client_registry_query_repository.py`
- `api/dependencies/client_registry.py`
- `api/routes/client_registry.py`
- `api/schemas/client_registry.py`
- `api/main.py` — bounded router composition only
- `line/static/profile_update.html`
- `ui_react/src/api/client_registry/`
- `ui_react/src/pages/ClientRegistryPage.tsx`

## Entrypoints
- `GET /api/v1/admin/registries/clients`
- `GET /api/v1/admin/registries/clients/{case_no}`
- `POST /api/v1/admin/registries/clients/{case_no}/profile/{preview|apply}`
- Client registry case mapping enters through canonical `orders.case_no -> clients.id`; Client Profile remains the only writer.

## Verification
- layout_status: `custom_current`
- layout_basis: Backend contract tests own Client Profile and BeClass query/mutation boundaries; the mirrored React root owns the case-centered registry interaction.
- test_root: `tests/domains/clients/subsystems/client-profile/modules/profile-change/`
- test_root: `ui_react/src/tests/domains/clients/subsystems/client-profile/modules/profile-change/`

## Change triggers
- Reconcile when allowlist、binding evidence、profile/request version、event／receipt／outbox、public route or LIFF readback changes.
