/**
 * File: line_flex_design_adapter.ts
 * Description: 將 closed Flex 設計來源轉為去敏預覽模型，並呈現正式資料接通狀態。
 */
import { z } from 'zod';

const FlexDesignSourceSchema = z.discriminatedUnion('id', [
  z.object({
    id: z.literal('flex_dispatch'),
    design_revision: z.literal(1),
    owner_fact_status: z.literal('missing'),
  }).strict(),
  z.object({
    id: z.literal('flex_leave_confirm'),
    design_revision: z.literal(1),
    owner_fact_status: z.literal('missing'),
  }).strict(),
  z.object({
    id: z.literal('flex_alert_critical'),
    design_revision: z.literal(1),
    owner_fact_status: z.literal('missing'),
  }).strict(),
  z.object({
    id: z.literal('flex_negotiation'),
    design_revision: z.literal(2),
    owner_fact_status: z.literal('connected'),
  }).strict(),
]);

export type LineFlexDesignSource = z.infer<typeof FlexDesignSourceSchema>;

export const LINE_FLEX_DESIGN_SOURCES = {
  flex_dispatch: { id: 'flex_dispatch', design_revision: 1, owner_fact_status: 'missing' },
  flex_leave_confirm: { id: 'flex_leave_confirm', design_revision: 1, owner_fact_status: 'missing' },
  flex_alert_critical: { id: 'flex_alert_critical', design_revision: 1, owner_fact_status: 'missing' },
  flex_negotiation: { id: 'flex_negotiation', design_revision: 2, owner_fact_status: 'connected' },
} as const satisfies Record<string, LineFlexDesignSource>;

export type LineFlexDesignActionTone = 'primary' | 'agree' | 'secondary' | 'alert';

export interface LineFlexDesignPreviewModel {
  id: LineFlexDesignSource['id'];
  header: string;
  emphasis?: string;
  bodyLines: readonly string[];
  actions: readonly { label: string; tone: LineFlexDesignActionTone }[];
  alertStyle: boolean;
  ownerFactStatus: 'missing' | 'connected';
  ownerFactNote: string;
  lifecycleNote: string;
}

const PREVIEW_BY_ID: Record<LineFlexDesignSource['id'], LineFlexDesignPreviewModel> = {
  flex_dispatch: {
    id: 'flex_dispatch',
    header: '🌸 新竹市月子工會 ｜ 派案通知',
    emphasis: '案件編號：【寄送前依正式案件資料帶入】',
    bodyLines: ['服務期間、時段與區域會以去敏方式呈現。', '詳細地址不留在 LINE 對話內容。'],
    actions: [{ label: '🔒 安全查閱訂單明細', tone: 'primary' }],
    alertStyle: false,
    ownerFactStatus: 'missing',
    ownerFactNote: '正式案件摘要與安全查閱入口尚未接上案件與排班資料。',
    lifecycleNote: '視覺排版範本已完成去敏核可；動態推播仍待正式業務來源。',
  },
  flex_leave_confirm: {
    id: 'flex_leave_confirm',
    header: '🌸 服務調休與順延確認通知',
    bodyLines: [
      '正式請假日期與順延後結束日會在寄送前核對。',
      '產婦選擇只建立確認命令，不由卡片文字直接改排班。',
    ],
    actions: [
      { label: '🟢 我同意順延一日', tone: 'agree' },
      { label: '🔴 不同意順延', tone: 'secondary' },
    ],
    alertStyle: false,
    ownerFactStatus: 'missing',
    ownerFactNote: '正式服務日期、確認憑證與目前案件版本尚未接上排班資料。',
    lifecycleNote: '視覺排版範本已完成去敏核可；動態推播仍待正式業務來源。',
  },
  flex_alert_critical: {
    id: 'flex_alert_critical',
    header: '🚨【工會急件告警 ｜ 待人工處理】',
    emphasis: '案件與告警摘要會以去敏方式提供',
    bodyLines: ['本設計稿不代表通知群組已配對或訊息已送達。'],
    actions: [{ label: '開啟手機管理中心', tone: 'alert' }],
    alertStyle: true,
    ownerFactStatus: 'missing',
    ownerFactNote: '正式告警摘要與通知對象尚未接上客服與通知資料。',
    lifecycleNote: '視覺排版範本已完成去敏核可；動態推播仍待正式業務來源。',
  },
  flex_negotiation: {
    id: 'flex_negotiation',
    header: '目前原條件尚無月嫂願意承接',
    bodyLines: [
      '由正式候選聯繫結果彙整可調整條件與可重新詢問人數。',
      '修改後仍需重新確認月嫂最新意願。',
    ],
    actions: [{ label: '回覆是否可調整', tone: 'primary' }],
    alertStyle: false,
    ownerFactStatus: 'connected',
    ownerFactNote: '候選最新回覆彙整、客戶耐久投遞及案件專屬回覆頁均已接通。',
    lifecycleNote: '實際送達仍依正式案件、綁定收件人與投遞任務狀態逐筆驗證。',
  },
};

export class LineFlexDesignPreviewError extends Error {
  constructor() {
    super('Flex 設計資料格式不符，已停止顯示。');
    this.name = 'LineFlexDesignPreviewError';
  }
}

export function adaptLineFlexDesignPreview(raw: unknown): LineFlexDesignPreviewModel {
  const parsed = FlexDesignSourceSchema.safeParse(raw);
  if (!parsed.success) throw new LineFlexDesignPreviewError();
  return PREVIEW_BY_ID[parsed.data.id];
}
