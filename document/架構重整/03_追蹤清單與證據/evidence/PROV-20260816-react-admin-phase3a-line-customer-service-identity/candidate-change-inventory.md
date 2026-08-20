# Phase 3A Candidate Change Inventory

- Branch/HEAD: `main@8615225481c8f72a9629289285516189b270cb36`
- Approval: `核准此 exact Phase 3A Work Package`
- DB/schema/migration: none
- Shared hotspots: forbidden and preserved

| Existing path | Baseline bytes | SHA256 | Collision status |
|---|---:|---|---|
| `api/schemas/customer_service.py` | 1905 | `A08394AA2410A27C496F6778AFB2EB880594D8B188B31D9C8B10B4CF5FC781A7` | clean tracked |
| `api/routes/customer_service.py` | 4684 | `A067AFE2FCFCB8C811C43DEA7109F6571917FD7805096983CB01B5B2ED4A1EB7` | clean tracked |
| `subsystems/customer_service/contracts.py` | 1493 | `95F80532F45EF6C3655FA7F1C793424AE017CDFB5033047560DCE507AAAD74F5` | clean tracked |
| `subsystems/customer_service/application.py` | 5387 | `9D902CF409761C1FB871CDB3A9737C59027C4416BE718EEFD007549CE1B696A2` | clean tracked |
| `tests/test_line_customer_service_first_release.py` | 12929 | `D7EA3BF31AC568B7BD5340B2E1E3FEA465A96754B595AB132E2ECCE0FB871E3A` | clean tracked |
| `tests/test_line_identity_management_first_release.py` | 13373 | `374D4F23C80AD3FEF629A9169506077DD4CEB0704264420513E6AE4ACC9B0EAC` | read-only regression |
| `ui_react/src/pages/LineManagementPage.tsx` | 44219 | `45932AF84D324B76CE364D195F85265435AEA884B3165ABFE8F8A8F1A043E6FF` | untracked user baseline; semantic merge only |
| `ui_react/src/pages/LineManagementPage.css` | 1375 | `9215CCED273846D008D35CA31CAE7DE8AB5F3476F4E6954844A9183AB966B6AE` | untracked user baseline; semantic merge only |

The byte counts, digests and `clean tracked` labels in this table describe the preserved pre-execution baseline, not
the current candidate bytes after approved edits. All other approved client/adapter/test paths were new at that
baseline. No existing exact-path SHA collision was found. Existing dirty
shared transport/Auth/App/package/Vite/components remain outside the write set and byte-preserved by this lane.
