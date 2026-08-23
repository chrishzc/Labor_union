/**
 * File: line_order_group_query_adapter.ts
 * Description: 將 LINE 訂單群組 query 轉成安全顯示模型，遮蔽群組與操作者識別資訊。
 */
import type {
  LineOrderGroupEvent, LineOrderGroupRecord, LineOrderGroupStatus,
} from '../../api/line_order_groups/line_order_group_query_schemas';

const STATUS_LABELS: Record<LineOrderGroupStatus, string> = {
  unbound: '尚未綁定', bound: '已綁定', inviting: '邀請中', active: '運作中',
  attention: '需要處理', replaced: '已替換', released: '已解除',
};

function maskIdentity(value: string | null, emptyLabel: string): string {
  if (value === null) return emptyLabel;
  if (value.length <= 4) return `${value.slice(0, 1)}••${value.slice(-1)}`;
  if (value.length <= 8) return `${value.slice(0, 2)}••${value.slice(-2)}`;
  return `${value.slice(0, 4)}••••${value.slice(-4)}`;
}

export interface LineOrderGroupRecordView {
  caseNo: string;
  groupIdentity: string;
  status: LineOrderGroupStatus;
  statusLabel: string;
  version: number;
}

export interface LineOrderGroupEventView {
  eventId: number;
  caseNo: string;
  eventType: string;
  actorIdentity: string;
  occurredAt: string;
  invitationFingerprint: string;
}

export function adaptLineOrderGroupRecord(value: LineOrderGroupRecord): LineOrderGroupRecordView {
  return {
    caseNo: value.case_no,
    groupIdentity: maskIdentity(value.group_id, '尚未綁定'),
    status: value.status,
    statusLabel: STATUS_LABELS[value.status],
    version: value.version,
  };
}

export function adaptLineOrderGroupEvent(value: LineOrderGroupEvent): LineOrderGroupEventView {
  return {
    eventId: value.event_id,
    caseNo: value.case_no,
    eventType: value.event_type,
    actorIdentity: maskIdentity(value.actor_id, '系統'),
    occurredAt: value.occurred_at,
    invitationFingerprint: value.invitation_fingerprint === null
      ? '無'
      : `${value.invitation_fingerprint.slice(0, 8)}…`,
  };
}
