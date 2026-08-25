/**
 * File: line_delivery_query_adapter.ts
 * Description: 將 LINE Delivery masked query 映射為管理頁唯讀摘要、列表與嘗試紀錄顯示模型。
 */
import type { LineDeliveryDetail, LineDeliveryItem, LineDeliverySourceType, LineDeliverySummary } from '../../api/line_delivery/line_delivery_query_schemas';

const STATUS_LABELS = { pending: '待執行', processing: '處理中', sent: '已送出', retryable_failed: '等待重試', failed: '失敗', cancelled: '已取消' } as const;

const SOURCE_LABELS: Record<LineDeliverySourceType, string> = {
  general_push: '一般通知',
  customer_service: '客服通知',
  contract: '契約通知',
  follow_schedule: '追蹤排程通知',
  identity: '身分綁定通知',
  identity_review: '身分審核通知',
  rich_menu: '圖文選單通知',
  rich_menu_link: '圖文選單啟用',
  rich_menu_unlink: '圖文選單停用',
  webhook: 'LINE 事件通知',
  group_invitation: '群組邀請',
  runtime: '系統異常通知',
  matching: '媒合通知',
  order: '案件通知',
  finance: '帳務通知',
  assignment: '排班通知',
};

const WORKER_STATUS_LABELS: Record<LineDeliverySummary['worker_status'], string> = {
  healthy: '正常',
  degraded: '部分異常',
  stale: '資料逾時',
  stopped: '已停止',
  missing: '尚未連線',
  unknown: '待確認',
};

const ATTEMPT_OUTCOME_LABELS: Record<LineDeliveryDetail['attempts'][number]['outcome'], string> = {
  success: '已完成',
  retryable_failure: '等待重試',
  terminal_failure: '無法繼續',
};

export function adaptLineDeliverySummary(source: LineDeliverySummary) {
  return { ...source, nextRunAt: source.next_run_at ?? '—', workerLabel: source.worker_running ? `運作中（${WORKER_STATUS_LABELS[source.worker_status]}）` : `未運作（${WORKER_STATUS_LABELS[source.worker_status]}）` };
}

export function adaptLineDeliveryItem(source: LineDeliveryItem) {
  return { taskId: source.task_id, sourceType: source.source_type, sourceLabel: SOURCE_LABELS[source.source_type], taskType: source.task_type, status: source.status, statusLabel: STATUS_LABELS[source.status], scheduledAt: source.scheduled_at, attempts: `${source.completed_attempts}/${source.max_attempts}`, nextRetryAt: source.next_retry_at ?? '—', updatedAt: source.updated_at };
}

export function adaptLineDeliveryDetail(source: LineDeliveryDetail) {
  return { task: adaptLineDeliveryItem(source.task), attempts: source.attempts.map((attempt) => ({ number: attempt.attempt_number, outcome: ATTEMPT_OUTCOME_LABELS[attempt.outcome], retryAfterSeconds: attempt.retry_after_seconds, startedAt: attempt.started_at, completedAt: attempt.completed_at })) };
}
