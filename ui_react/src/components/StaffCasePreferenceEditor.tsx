import React, { useEffect, useMemo, useState } from 'react';

import { staffCasePreferenceSummaryClient } from '../api/staff_case_preference_summary/staff_case_preference_summary_client';
import type {
  StaffCasePreferencePreview,
  StaffCasePreferenceSnapshot,
  StaffCasePreferenceSummary,
  StaffCasePreferenceTopic,
} from '../api/staff_case_preference_summary/staff_case_preference_summary_schemas';

type TopicKey = keyof StaffCasePreferenceSnapshot;
type Phase = 'loading' | 'ready' | 'editing' | 'previewing' | 'preview_ready' | 'applying' | 'observed' | 'error';

interface Props {
  staffId: number;
  onObserved?: () => void;
}

const TOPICS: ReadonlyArray<{
  key: TopicKey;
  label: string;
  options: readonly string[];
  allowOther: boolean;
}> = [
  { key: 'service_regions', label: '希望服務地區', options: ['北區', '東區', '香山區', '新竹縣', '苗栗縣'], allowOther: true },
  { key: 'service_periods', label: '服務時段', options: ['4小時(上午8:30-12:30)', '4小時(下午13:00-17:00)', '8小時', '24小時'], allowOther: true },
  { key: 'rest_schedule', label: '如何排休', options: ['連續服務', '週休1日', '週休2日'], allowOther: true },
  { key: 'baby_counts', label: '通常接幾胞胎', options: ['單胞胎', '雙胞胎'], allowOther: true },
  { key: 'holiday_availability', label: '特殊節日可接案', options: ['年節農曆過年初一', '年節農曆過年初二', '年節農曆過年初三', '端午節', '中秋節', '國定假日必休'], allowOther: true },
  { key: 'transportation', label: '交通方式', options: ['機車', '轎車'], allowOther: false },
];

function snapshotFromSummary(summary: StaffCasePreferenceSummary): StaffCasePreferenceSnapshot {
  return {
    service_regions: { values: [...summary.service_regions.values], other_detail: summary.service_regions.other_detail },
    service_periods: { values: [...summary.service_periods.values], other_detail: summary.service_periods.other_detail },
    rest_schedule: { values: [...summary.rest_schedule.values], other_detail: summary.rest_schedule.other_detail },
    baby_counts: { values: [...summary.baby_counts.values], other_detail: summary.baby_counts.other_detail },
    holiday_availability: { values: [...summary.holiday_availability.values], other_detail: summary.holiday_availability.other_detail },
    transportation: { values: [...summary.transportation.values], other_detail: null },
  };
}

function topicText(topic: StaffCasePreferenceTopic): string {
  const valuesText = topic.values.length > 0 ? topic.values.join('、') : '尚未登錄';
  if (topic.other_detail_status === 'ready' && topic.other_detail) {
    return `${valuesText} · 其它：${topic.other_detail}`;
  }
  if (topic.other_detail_status === 'source_not_ready') {
    return `${valuesText} · 其它來源尚未就緒`;
  }
  return valuesText;
}

export const StaffCasePreferenceEditor: React.FC<Props> = ({ staffId, onObserved }) => {
  const [summary, setSummary] = useState<StaffCasePreferenceSummary | null>(null);
  const [draft, setDraft] = useState<StaffCasePreferenceSnapshot | null>(null);
  const [preview, setPreview] = useState<StaffCasePreferencePreview | null>(null);
  const [phase, setPhase] = useState<Phase>('loading');
  const [message, setMessage] = useState<string | null>(null);

  const locked = ['loading', 'previewing', 'applying'].includes(phase);

  const load = async () => {
    setPhase('loading');
    setMessage(null);
    try {
      const next = await staffCasePreferenceSummaryClient.query(staffId);
      setSummary(next);
      setDraft(snapshotFromSummary(next));
      setPreview(null);
      setPhase('ready');
    } catch (error) {
      setPhase('error');
      setMessage(error instanceof Error ? error.message : '接案偏好載入失敗。');
    }
  };

  useEffect(() => {
    void load();
  }, [staffId]);

  const optionsByTopic = useMemo(() => Object.fromEntries(TOPICS.map((spec) => {
    const existing = draft?.[spec.key].values ?? [];
    return [spec.key, [...spec.options, ...existing.filter((value) => !spec.options.includes(value))]];
  })) as Record<TopicKey, string[]>, [draft]);

  const beginEdit = () => {
    if (!summary) return;
    setDraft(snapshotFromSummary(summary));
    setPreview(null);
    setMessage(null);
    setPhase('editing');
  };

  const toggleValue = (key: TopicKey, value: string) => {
    if (!draft) return;
    const current = draft[key];
    const selected = current.values.includes(value);
    setDraft({
      ...draft,
      [key]: {
        ...current,
        values: selected ? current.values.filter((item) => item !== value) : [...current.values, value],
      },
    });
    setPreview(null);
    setPhase('editing');
  };

  const updateOther = (key: TopicKey, value: string) => {
    if (!draft) return;
    setDraft({ ...draft, [key]: { ...draft[key], other_detail: value || null } });
    setPreview(null);
    setPhase('editing');
  };

  const previewChange = async () => {
    if (!draft) return;
    setPhase('previewing');
    setMessage(null);
    try {
      const next = await staffCasePreferenceSummaryClient.preview(staffId, draft);
      setPreview(next);
      setPhase('preview_ready');
    } catch (error) {
      setPhase('error');
      setMessage(error instanceof Error ? error.message : '接案偏好預覽失敗。');
    }
  };

  const applyChange = async () => {
    if (!draft || !preview) return;
    setPhase('applying');
    setMessage(null);
    try {
      await staffCasePreferenceSummaryClient.apply(staffId, {
        snapshot: draft,
        preview_fingerprint: preview.preview_fingerprint,
      });
      const observed = await staffCasePreferenceSummaryClient.query(staffId);
      setSummary(observed);
      setDraft(snapshotFromSummary(observed));
      setPreview(null);
      setPhase('observed');
      setMessage('已儲存並重新讀取最新六項接案偏好。');
      onObserved?.();
    } catch (error) {
      setPhase('error');
      setMessage(error instanceof Error ? error.message : '接案偏好儲存失敗；請重新載入後再預覽。');
    }
  };

  if (phase === 'loading') return <p role="status">正在載入接案偏好…</p>;
  if (!summary || !draft) {
    return <div role="alert"><p>{message ?? '接案偏好目前無法讀取。'}</p><button type="button" className="staff-next-btn" onClick={() => void load()}>重新載入</button></div>;
  }

  const editing = phase === 'editing' || phase === 'previewing' || phase === 'preview_ready' || phase === 'applying';

  return (
    <div data-surface-id="staff.drawer.case-preference-summary">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
        <div>
          <h3 style={{ margin: 0 }}>📌 接案偏好設定</h3>
          <p className="staff-form-hint" style={{ margin: '6px 0 0' }}>直接維護六項 Staff 正式偏好；儲存前會先預覽，完成後重新查詢確認。</p>
        </div>
        {!editing && <button type="button" className="staff-next-btn" disabled={locked} onClick={beginEdit}>編輯六項偏好</button>}
        {phase === 'editing' && <button type="button" data-control-id="staff.case-preference.preview" className="staff-next-btn" onClick={() => void previewChange()}>預覽變更</button>}
        {phase === 'preview_ready' && <button type="button" data-control-id="staff.case-preference.apply" className="staff-next-btn" onClick={() => void applyChange()}>確認儲存</button>}
      </div>

      <div className="staff-qual-grid">
        {TOPICS.map((spec) => {
          const topic = draft[spec.key];
          return (
            <div key={spec.key} className="staff-qual-card" role="group" aria-label={spec.label}>
              <h4>{spec.label}</h4>
              {!editing ? (
                <p style={{ margin: 0 }}>{topicText(summary[spec.key])}</p>
              ) : (
                <div>
                  {optionsByTopic[spec.key].map((option) => (
                    <label key={option} style={{ display: 'block', margin: '4px 0' }}>
                      <input
                        type="checkbox"
                        checked={topic.values.includes(option)}
                        disabled={locked}
                        onChange={() => toggleValue(spec.key, option)}
                      />{' '}{option}
                    </label>
                  ))}
                  {spec.allowOther && (
                    <label style={{ display: 'block', marginTop: '8px' }}>
                      其他
                      <input
                        type="text"
                        aria-label={`${spec.label}其他`}
                        value={topic.other_detail ?? ''}
                        disabled={locked}
                        onChange={(event) => updateOther(spec.key, event.target.value)}
                      />
                    </label>
                  )}
                  {!spec.allowOther && <small>交通方式的「其他」來源尚未就緒，本頁不提供推測式寫入。</small>}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {preview && phase === 'preview_ready' && <div className="staff-action-status">預覽已完成；確認後才會寫回這六項正式偏好。</div>}
      {message && <div className={`staff-action-status ${phase === 'error' ? 'error' : ''}`} role="status">{message}</div>}
      {phase === 'error' && <button type="button" className="staff-next-btn" onClick={() => void load()}>重新載入後再編輯</button>}
    </div>
  );
};

export default StaffCasePreferenceEditor;
