/**
 * File: account_query_contract_fixtures.ts
 * Description: 帳號查詢頁面使用的最小去敏 typed contract fixture。
 */
import type { AccountDirectoryItem } from '../../../api/access/account_directory_schemas';
import type { AdminAuditPage } from '../../../api/access/audit_query_schemas';
import type { JobObservation } from '../../../api/jobs/job_observation_schemas';

export const ACCOUNT_DIRECTORY_FIXTURE: AccountDirectoryItem[] = [
  {
    id: 1,
    username: 'root-user',
    display_name: '根帳號',
    enabled: true,
    is_root: true,
    access_control_version: 2,
  },
];

export const AUDIT_PAGE_FIXTURE: AdminAuditPage = {
  items: [
    {
      audit_id: 10,
      occurred_at: '2026-08-20T10:00:00',
      actor_label: '根***',
      action_family: 'authentication',
      target_label: null,
      ip_address: '127.0.0.***',
      outcome: 'success',
      reason_code: 'admin.login.success',
    },
  ],
  page: 1,
  page_size: 25,
  total: 1,
  total_pages: 1,
};

export const JOB_OBSERVATION_FIXTURE: JobObservation = {
  job_id: 'job-observation-1',
  command_type: 'assignment_plan_apply',
  status: 'running',
  attempt_count: 1,
  max_attempts: 3,
};
