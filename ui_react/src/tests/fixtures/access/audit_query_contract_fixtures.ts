/**
 * File: audit_query_contract_fixtures.ts
 * Description: Access Audit React list/detail 的最小去敏契約 fixture。
 */
import type { AdminAuditDetail } from '../../../api/access/audit_query_schemas';
import { AUDIT_PAGE_FIXTURE } from './account_query_contract_fixtures';

export { AUDIT_PAGE_FIXTURE };

export const AUDIT_DETAIL_FIXTURE: AdminAuditDetail = {
  ...AUDIT_PAGE_FIXTURE.items[0],
  details: [
    { key: 'reason', value: 'provided' },
    { key: 'mfa_method', value: 'totp' },
  ],
};
