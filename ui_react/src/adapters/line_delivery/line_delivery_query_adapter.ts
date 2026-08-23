/**
 * File: line_delivery_query_adapter.ts
 * Description: 將 LINE Delivery masked query 映射為管理頁唯讀摘要、列表與嘗試紀錄顯示模型。
 */
import type { LineDeliveryDetail, LineDeliveryItem, LineDeliverySummary } from '../../api/line_delivery/line_delivery_query_schemas';

const STATUS_LABELS = { pending: '待執行', processing: '處理中', sent: '已送達', retryable_failed: '等待重試', failed: '失敗', cancelled: '已取消' } as const;

export function adaptLineDeliverySummary(source: LineDeliverySummary) {
  return { ...source, nextRunAt: source.next_run_at ?? '—', workerLabel: source.worker_running ? `運作中（${source.worker_status}）` : `未運作（${source.worker_status}）` };
}

export function adaptLineDeliveryItem(source: LineDeliveryItem) {
  return { taskId: source.task_id, sourceType: source.source_type, taskType: source.task_type, status: source.status, statusLabel: STATUS_LABELS[source.status], scheduledAt: source.scheduled_at, attempts: `${source.completed_attempts}/${source.max_attempts}`, nextRetryAt: source.next_retry_at ?? '—', updatedAt: source.updated_at };
}

export function adaptLineDeliveryDetail(source: LineDeliveryDetail) {
  return { task: adaptLineDeliveryItem(source.task), attempts: source.attempts.map((attempt) => ({ number: attempt.attempt_number, outcome: attempt.outcome, retryAfterSeconds: attempt.retry_after_seconds, startedAt: attempt.started_at, completedAt: attempt.completed_at })) };
}
