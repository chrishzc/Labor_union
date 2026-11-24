import { useEffect, useRef, useState } from 'react';
import { notifyNotificationTasksChanged } from '../api/line_notifications/notification_tasks_client';
import {
  publishedStaffWebProfilePath, staffWebError, staffWebProfileClient,
  type CropBox, type PendingWebPhoto, type StaffProfileReview, type WebProfileTemplate,
} from '../api/staff/staff_web_profile_client';
import { StaffWebPhotoReview } from './StaffWebPhotoReview';
import { StaffWebProfilePreview } from './StaffWebProfilePreview';

type Review = StaffProfileReview;
const labels: Record<string, string> = {
  phone: '手機', tel: '市話', tel_ext: '分機', email: 'Email', city: '縣市', zip_code: '郵遞區號',
  address: '詳細地址', emergency_contact_name: '緊急聯絡人', emergency_contact_phone: '緊急聯絡電話',
  bank_code: '銀行代碼', branch_code: '分行代碼', account_last4: '帳號末四碼',
  service_regions: '服務地區', service_periods: '服務時段', rest_schedule: '排休方式',
  baby_types: '接案胎數', holiday_availability: '特殊節日可接案', transportation: '交通方式',
  preferred_service_days: '可承接天數', daily_service_hours: '每日可服務時數',
};
const fieldSections = [
  { key: 'profile', title: '聯絡與地址資料' }, { key: 'bank', title: '收款帳戶' },
  { key: 'relations', title: '接案偏好' }, { key: 'transportation', title: '交通方式' },
  { key: 'matching', title: '接案時數與天數' },
] as const;
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

function publicationConfirmed(photos: PendingWebPhoto[], review: Review): boolean {
  if (review.status !== 'approved' || review.publications?.length !== photos.length) return false;
  return photos.every(photo => review.publications?.some(item => item.template_item_id === photo.template_item_id
    && item.file_id === (photo.crop_file_id ?? photo.original_file_id)
    && (photo.entry_id === null || (item.entry_id === photo.entry_id && item.version > (photo.entry_version ?? 0)))));
}

export function StaffProfileChangeReview({ requestId, returnToWeb = false }: { requestId: number; returnToWeb?: boolean }) {
  const [review, setReview] = useState<Review | null>(null);
  const [templates, setTemplates] = useState<WebProfileTemplate[]>([]);
  const [showPublished, setShowPublished] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const operation = useRef(false);
  const [reload, setReload] = useState(0);
  const hasWebPhotos = !!review?.changes?.web_contents?.length;
  const hasPublications = review?.status === 'approved' && !!review.publications?.length;

  useEffect(() => {
    const controller = new AbortController();
    setReview(null);
    setError('');
    void (async () => {
      try {
        const result = await staffWebProfileClient.review(requestId, controller.signal);
        if (controller.signal.aborted) return;
        setReview(result);
      } catch (caught) {
        if (!controller.signal.aborted) setError(staffWebError(caught, '無法載入申請。'));
      }
    })();
    return () => controller.abort();
  }, [requestId, reload]);

  useEffect(() => {
    if (!hasWebPhotos) return;
    const controller = new AbortController();
    void staffWebProfileClient.templates(controller.signal).then(result => {
      if (!controller.signal.aborted) setTemplates(result);
    }).catch(caught => {
      if (!controller.signal.aborted) setError(staffWebError(caught, '無法讀取照片對應的模板項目。'));
    });
    return () => controller.abort();
  }, [hasWebPhotos, reload]);

  async function perform(update: (current: Review) => Promise<Review>, failure: string): Promise<boolean> {
    if (!review || operation.current || error) return false;
    operation.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await update(review);
      if (result.id !== review.id || result.staff_id !== review.staff_id || result.version < review.version) {
        throw new Error('review_identity_mismatch');
      }
      setReview(result);
      return true;
    } catch (caught) {
      setError(staffWebError(caught, failure));
      return false;
    } finally {
      operation.current = false;
      setBusy(false);
    }
  }

  function decide(action: 'approve' | 'reject') {
    void perform(async current => {
      const result = await staffWebProfileClient.decide(requestId, current.version, action);
      const photos = current.changes?.web_contents;
      if (action === 'approve' && photos?.length) {
        const observed = await staffWebProfileClient.review(requestId);
        if (!publicationConfirmed(photos, observed)) throw new Error('publication_unconfirmed');
        return observed;
      }
      return result;
    }, '審核結果尚未確認，請重新讀取。').then(done => {
      if (done) notifyNotificationTasksChanged();
    });
  }

  function crop(index: number, box: CropBox | null) {
    return perform(async current => {
      const result = await staffWebProfileClient.changeCrop(requestId, index, current.version, box);
      if (result.status !== 'pending' || result.version <= current.version) throw new Error('crop_unconfirmed');
      return result;
    }, '裁切結果尚未確認，請重新讀取。');
  }

  const status = hasPublications ? '整張申請已核准，照片已發布' : review && statusLabels[review.status];
  return <section className="staff-holiday-op-card" aria-labelledby="staff-change-review">
    <h2 id="staff-change-review">月嫂資料異動申請 #{requestId}</h2>
    <p>{returnToWeb ? <a href="#staff?tab=web&view=review">返回照片審核</a> : <a href="#notifications">返回通知事項</a>}</p>
    {!review && !error && <p role="status">正在讀取申請…</p>}
    {review && <>
      <p role="status">月嫂 #{review.staff_id} · {status}</p>
      {fieldSections.map(({ key: section, title }) => {
        const change = review.changes?.[section];
        if (!change) return null;
        const keys = [...new Set([...Object.keys(change.before ?? {}), ...Object.keys(change.after ?? {})])]
          .filter(key => labels[key]);
        return <section key={section}>
          <h3>{title}</h3>
          <table>
            <thead><tr><th scope="col">欄位</th><th scope="col">目前資料</th><th scope="col">申請變更</th></tr></thead>
            <tbody>{keys.map(key => <tr key={key}><th scope="row">{labels[key]}</th>
              <td>{formatValue(change.before?.[key])}</td><td>{formatValue(change.after?.[key])}</td></tr>)}</tbody>
          </table>
        </section>;
      })}
      {(hasWebPhotos || hasPublications) && <section aria-label="履歷網頁照片">
        <h3>履歷網頁照片</h3>
        <button type="button" className="staff-secondary-btn" aria-expanded={showPublished}
          onClick={() => setShowPublished(value => !value)}>{showPublished ? '收起已發布網頁' : '查看已發布網頁'}</button>
        {showPublished && <StaffWebProfilePreview key={review.version} path={publishedStaffWebProfilePath(review.staff_id)} headingLevel="h4" />}
        {review.changes?.web_contents?.map((photo, index) => <StaffWebPhotoReview
          key={photo.original_file_id} requestId={requestId} index={index} photo={photo}
          title={`${templates.find(item => item.item_id === photo.template_item_id)?.name ?? `模板項目 #${photo.template_item_id}`} · 第 ${index + 1} 張`}
          editable={review.status === 'pending'} locked={busy || !!error} changeCrop={box => crop(index, box)} />)}
      </section>}
      {(review.status === 'pending' || review.status === 'approving') && <div className="staff-op-actions">
        <button type="button" className="staff-primary-btn" disabled={busy || !!error} onClick={() => decide('approve')}>
          {review.status === 'approving' ? '確認原核准結果' : hasWebPhotos ? '核准整張申請並發布照片' : '核准整張申請'}
        </button>
        {review.status === 'pending' && <button type="button" className="staff-secondary-btn" disabled={busy || !!error}
          onClick={() => decide('reject')}>退回整張申請</button>}
      </div>}
    </>}
    {error && <><p role="alert">{error}</p><button type="button" onClick={() => setReload(count => count + 1)}>重新讀取</button></>}
  </section>;
}
