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
  commandType: string;
  status: string;
  attemptCount: number;
  maxAttempts: number;
}

const JOB_COMMAND_LABELS: Record<JobObservation['command_type'], string> = {
  assignment_plan_apply: '正式排班建立',
  finance_import_historical_reprocess_apply: '歷史銀行流水重處理',
  finance_import_batch_apply: '銀行流水正式匯入',
  finance_import_correction_apply: '銀行流水更正',
  orders_auto_completion_apply: '訂單服務完成',
  government_subsidy_apply: '政府補助核銷',
  payroll_rebuild_apply: '薪資重新計算',
  staff_payout_apply: '月嫂付款',
};

const JOB_STATUS_LABELS: Record<JobObservation['status'], string> = {
  queued: '等待處理', running: '處理中', succeeded: '已完成', failed: '處理失敗', cancelled: '已取消',
};

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
    commandType: JOB_COMMAND_LABELS[job.command_type],
    status: JOB_STATUS_LABELS[job.status],
    attemptCount: job.attempt_count,
    maxAttempts: job.max_attempts,
  };
}
