import { useEffect, useState } from 'react';
import { z } from 'zod';
import { notificationOptions } from '../api/line_notifications/notification_tasks_client';
import { transport } from '../api/shared/transport';

const values = z.record(z.string(), z.unknown());
const reviewSchema = z.object({
  id: z.number().int().positive(),
  staff_id: z.number().int().positive(),
  version: z.number().int().positive(),
  status: z.enum(['pending', 'approving', 'approved', 'rejected', 'conflict']),
  changes: z.record(z.string(), z.object({ before: values.nullable(), after: values.nullable() })).nullable(),
});
type Review = z.infer<typeof reviewSchema>;
const labels: Record<string, string> = {
  phone: '手機', tel: '市話', tel_ext: '分機', email: 'Email', city: '縣市', zip_code: '郵遞區號',
  address: '詳細地址', emergency_contact_name: '緊急聯絡人', emergency_contact_phone: '緊急聯絡電話',
  bank_code: '銀行代碼', branch_code: '分行代碼', account_last4: '帳號末四碼',
  service_regions: '服務地區', service_periods: '服務時段', rest_schedule: '排休方式',
  baby_types: '接案胎數', holiday_availability: '特殊節日可接案', transportation: '交通方式',
  preferred_service_days: '可承接天數', daily_service_hours: '每日可服務時數',
};
const sectionTitles: Record<string, string> = {
  profile: '聯絡與地址資料', bank: '收款帳戶', relations: '接案偏好',
  transportation: '交通方式', matching: '接案時數與天數',
};
const statusLabels: Record<Review['status'], string> = {
  pending: '待審核', approving: '核准處理中', approved: '整張申請已核准',
  rejected: '整張申請已退回', conflict: '正式資料已變更，請月嫂重新送件',
};

function formatValue(value: unknown): string {
  if (value == null || value === '') return '未設定';
  if (Array.isArray(value)) return value.map(formatValue).join('、') || '未設定';
  if (typeof value === 'object') {
    if ('value' in value) return [value.value, 'detail' in value ? value.detail : null].filter(Boolean).join('：');
    if ('minimum' in value && 'maximum' in value) return `${value.minimum}–${value.maximum} 天`;
    if ('values' in value) return formatValue(value.values);
  }
  return String(value);
}

export function StaffProfileChangeReview({ requestId }: { requestId: number }) {
  const [review, setReview] = useState<Review | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reload, setReload] = useState(0);
  const path = `/api/v1/admin/staff-profile-change-requests/${requestId}`;

  useEffect(() => {
    const controller = new AbortController();
    setReview(null);
    setError('');
    void (async () => {
      try {
        const response = await transport.get<{ data: unknown }>(path, notificationOptions(controller.signal));
        if (!controller.signal.aborted) setReview(reviewSchema.parse(response.data));
      } catch (caught) {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : '無法載入申請。');
      }
    })();
    return () => controller.abort();
  }, [path, reload]);

  async function decide(action: 'approve' | 'reject') {
    if (!review || busy || error) return;
    setBusy(true);
    setError('');
    try {
      const response = await transport.post<{ data: unknown }>(
        `${path}/decision`, { action, version: review.version }, notificationOptions(),
      );
      setReview(reviewSchema.parse(response.data));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '審核未完成，請重新讀取結果。');
    } finally {
      setBusy(false);
    }
  }

  return <section className="staff-holiday-op-card" aria-labelledby="staff-change-review">
    <h2 id="staff-change-review">月嫂資料異動申請 #{requestId}</h2>
    <p><a href="#notifications">返回通知事項</a></p>
    {!review && !error && <p role="status">正在讀取申請…</p>}
    {review && <>
      <p role="status">月嫂 #{review.staff_id} · {statusLabels[review.status]}</p>
      {Object.entries(review.changes ?? {}).map(([section, change]) => {
        const keys = [...new Set([...Object.keys(change.before ?? {}), ...Object.keys(change.after ?? {})])]
          .filter(key => labels[key]);
        return <section key={section}>
          <h3>{sectionTitles[section]}</h3>
          <table>
            <thead><tr><th scope="col">欄位</th><th scope="col">目前資料</th><th scope="col">申請變更</th></tr></thead>
            <tbody>{keys.map(key => <tr key={key}><th scope="row">{labels[key]}</th>
              <td>{formatValue(change.before?.[key])}</td><td>{formatValue(change.after?.[key])}</td></tr>)}</tbody>
          </table>
        </section>;
      })}
      {(review.status === 'pending' || review.status === 'approving') && <div className="staff-op-actions">
        <button type="button" className="staff-primary-btn" disabled={busy || !!error} onClick={() => void decide('approve')}>
          {review.status === 'approving' ? '確認原核准結果' : '核准整張申請'}
        </button>
        {review.status === 'pending' && <button type="button" className="staff-secondary-btn" disabled={busy || !!error}
          onClick={() => void decide('reject')}>退回整張申請</button>}
      </div>}
    </>}
    {error && <><p role="alert">{error}</p><button type="button" onClick={() => setReload(count => count + 1)}>重新讀取</button></>}
  </section>;
}
