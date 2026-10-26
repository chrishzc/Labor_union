/**
 * File: line_order_group_query_adapter.ts
 * Description: 將 LINE 訂單群組 query 轉成安全顯示模型，遮蔽群組與操作者識別資訊。
 */
import { staffDisplayLabel } from '../staff/staff_directory_adapter';
import type {
  LineOrderGroupEvent, LineOrderGroupRecord, LineOrderGroupStatus,
  LineOrderGroupWorkspaceEvent, LineOrderGroupWorkspaceRecord,
} from '../../api/line_order_groups/line_order_group_query_schemas';

const STATUS_LABELS: Record<LineOrderGroupStatus, string> = {
  unbound: '尚未綁定', bound: '已綁定', inviting: '邀請中', active: '運作中',
  attention: '需要處理', replaced: '已替換', released: '已解除',
};

export function lineOrderGroupStatusLabel(status: LineOrderGroupStatus): string {
  return STATUS_LABELS[status];
}

export function lineOrderGroupEventLabel(event: LineOrderGroupWorkspaceEvent): string {
  const person = event.participant_role === 'staff' && event.participant_name ? staffDisplayLabel(event.participant_union_no, event.participant_name) : event.participant_name || (event.participant_role === 'customer' ? '客戶' : event.participant_role === 'staff' ? '月嫂' : '成員');
  const labels: Record<string, string> = {
    bound: '已綁定案件群組', replaced: '已更換綁定群組', released: '已解除群組綁定',
    invitation_relayed: '邀請已排入發送', member_joined: `${person}已加入群組`,
    member_left: `${person}已離開群組`, group_activated: '群組開始運作',
  };
  return labels[event.event_type] ?? '群組紀錄已更新';
}

export function lineOrderGroupReason(record: LineOrderGroupWorkspaceRecord): string {
  if (record.status === 'released') return '綁定已解除';
  if (record.status === 'unbound') return '尚無群組綁定';
  const affected = (state: 'left' | 'pending') => {
    const roles = new Set(record.members.filter(member => member.membership_status === state).map(member => member.role));
    return [roles.has('customer') ? '客戶' : '', roles.has('staff') ? '月嫂' : ''].filter(Boolean).join('與');
  };
  if (affected('left')) return `${affected('left')}已離開群組`;
  if (record.members.length === 0 || record.members.some(member => member.membership_status === 'unknown')) return '加入狀況待確認';
  if (record.status === 'bound' && !record.last_invitation_at) return '尚無邀請紀錄';
  if (affected('pending')) return `${affected('pending')}尚未確認加入`;
  const roles = new Set(record.members.map(member => member.role));
  return roles.has('customer') && roles.has('staff') ? '客戶與月嫂皆已加入' : '已收到成員加入紀錄';
}

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
