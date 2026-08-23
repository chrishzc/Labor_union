/**
 * File: account_query_adapter.ts
 * Description: 將帳號與背景工作 typed GET 投影為安全頁面資料。
 */
import type { AccountDirectoryItem } from '../../api/access/account_directory_schemas';
import type { JobObservation } from '../../api/jobs/job_observation_schemas';

export const ACCOUNT_UNAVAILABLE = '後端尚未提供 typed 顯示資料';

export interface AccountDirectoryRow {
  id: number;
  username: string;
  displayName: string;
  enabled: boolean;
  isRoot: boolean;
  accessControlVersion: number;
}

export interface JobObservationView {
  jobId: string;
  commandType: JobObservation['command_type'];
  status: JobObservation['status'];
  attemptCount: number;
  maxAttempts: number;
}

export function adaptAccountDirectory(items: AccountDirectoryItem[]): AccountDirectoryRow[] {
  return items.map((item) => ({
    id: item.id,
    username: item.username,
    displayName: item.display_name,
    enabled: item.enabled,
    isRoot: item.is_root,
    accessControlVersion: item.access_control_version,
  }));
}

export function adaptJobObservation(job: JobObservation): JobObservationView {
  return {
    jobId: job.job_id,
    commandType: job.command_type,
    status: job.status,
    attemptCount: job.attempt_count,
    maxAttempts: job.max_attempts,
  };
}
