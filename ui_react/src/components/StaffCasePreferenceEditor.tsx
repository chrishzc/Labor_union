/**
 * File: StaffCasePreferenceEditor.tsx
 * Description: 直接以六個 Staff-owned topic 完成接案偏好編輯、預覽、儲存與回讀。
 */
import React, { useEffect, useState } from 'react';
import { staffCasePreferenceSummaryClient } from '../api/staff_case_preference_summary/staff_case_preference_summary_client';
import { staffCasePreferenceCommandClient } from '../api/staff_case_preference_summary/staff_case_preference_summary_command_client';
import type {
  StaffCasePreferencePreview,
  StaffCasePreferenceSnapshotInput,
} from '../api/staff_case_preference_summary/staff_case_preference_summary_command_schemas';
import type {
  StaffCasePreferenceSummary,
  StaffCasePreferenceTopic,
} from '../api/staff_case_preference_summary/staff_case_preference_summary_schemas';

export type StaffCasePreferenceTopicKey =
  | 'service_regions'
  | 'service_periods'
  | 'rest_schedule'
  | 'baby_counts'
  | 'holiday_availability'
  | 'transportation';

interface StaffCasePreferenceEditorProps {
  staffId: number | null;
  onSaved?: (summary: StaffCasePreferenceSummary) => void;
}

interface TopicDraft {
  values: string;
  otherDetail: string;
}

type DraftState = Record<StaffCasePreferenceTopicKey, TopicDraft>;

const TOPICS: ReadonlyArray<{
  key: StaffCasePreferenceTopicKey;
  label: string;
  allowOther: boolean;
}> = [
  { key: 'service_regions', label: '希望服務地區', allowOther: true },
  { key: 'service_periods', label: '服務時段', allowOther: true },
  { key: 'rest_schedule', label: '如何排休', allowOther: true },
  { key: 'baby_counts', label: '通常接幾胞胎', allowOther: true },
  { key: 'holiday_availability', label: '特殊節日可接案', allowOther: true },
  { key: 'transportation', label: '交通方式', allowOther: false },
];

const EMPTY_DRAFT: DraftState = {
  service_regions: { values: '', otherDetail: '' },
  service_periods: { values: '', otherDetail: '' },
  rest_schedule: { values: '', otherDetail: '' },
  baby_counts: { values: '', otherDetail: '' },
  holiday_availability: { values: '', otherDetail: '' },
  transportation: { values: '', otherDetail: '' },
};

function topicValuesText(topic: StaffCasePreferenceTopic): string {
  return topic.values.length > 0 ? topic.values.join('、') : '尚未登錄';
}

function draftFromSummary(summary: StaffCasePreferenceSummary): DraftState {
  return Object.fromEntries(TOPICS.map(({ key }) => [
    key,
    {
      values: summary[key].values.join('、'),
      otherDetail: summary[key].other_detail ?? '',
    },
  ])) as DraftState;
}

function parseValues(value: string): string[] {
  return Array.from(new Set(
    value
      .split(/[、,，\n]/)
      .map((item) => item.trim())
      .filter(Boolean),
  ));
}

function snapshotFromDraft(draft: DraftState): StaffCasePreferenceSnapshotInput {
  return Object.fromEntries(TOPICS.map(({ key, allowOther }) => [
    key,
    {
      values: parseValues(draft[key].values),
      other_detail: allowOther && draft[key].otherDetail.trim()
        ? draft[key].otherDetail.trim()
        : null,
    },
  ])) as StaffCasePreferenceSnapshotInput;
}

function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function changedTopicLabels(keys: string[]): string[] {
  return keys.map((key) => TOPICS.find((topic) => topic.key === key)?.label ?? key);
}

export const StaffCasePreferenceEditor: React.FC<StaffCasePreferenceEditorProps> = ({ staffId, onSaved }) => {
  const [summary, setSummary] = useState<StaffCasePreferenceSummary | null>(null);
  const [draft, setDraft] = useState<DraftState>(EMPTY_DRAFT);
  const [editing, setEditing] = useState(false);
  const [preview, setPreview] = useState<StaffCasePreferencePreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloadGeneration, setReloadGeneration] = useState(0);

  useEffect(() => {
    setSummary(null);
    setDraft(EMPTY_DRAFT);
    setEditing(false);
    setPreview(null);
    setMessage(null);
    setError(null);
    if (staffId === null) return undefined;

    const controller = new AbortController();
    setLoading(true);
    void staffCasePreferenceSummaryClient.query(staffId, { signal: controller.signal })
      .then((value) => {
        if (controller.signal.aborted) return;
        setSummary(value);
        setDraft(draftFromSummary(value));
      })
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(errorMessage(reason, '接案偏好摘要載入失敗。'));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [staffId, reloadGeneration]);

  const updateDraft = (
    key: StaffCasePreferenceTopicKey,
    field: keyof TopicDraft,
    value: string,
  ) => {
    setDraft((current) => ({
      ...current,
      [key]: { ...current[key], [field]: value },
    }));
    setPreview(null);
    setMessage(null);
    setError(null);
  };

  const startEditing = () => {
    if (summary === null) return;
    setDraft(draftFromSummary(summary));
    setEditing(true);
    setPreview(null);
    setMessage(null);
    setError(null);
  };

  const cancelEditing = () => {
    if (summary !== null) setDraft(draftFromSummary(summary));
    setEditing(false);
    setPreview(null);
    setMessage(null);
    setError(null);
  };

  const previewChanges = async () => {
    if (staffId === null) return;
    setPreviewing(true);
    setMessage(null);
    setError(null);
    try {
      const result = await staffCasePreferenceCommandClient.preview(
        staffId,
        { snapshot: snapshotFromDraft(draft) },
      );
      setPreview(result);
      const labels = changedTopicLabels(result.changed_topics);
      setMessage(
        labels.length === 0
          ? '目前六項偏好沒有變更。'
          : `預覽完成：將變更 ${labels.join('、')}。`,
      );
    } catch (reason) {
      setPreview(null);
      setError(errorMessage(reason, '接案偏好預覽失敗。'));
    } finally {
      setPreviewing(false);
    }
  };

  const applyChanges = async () => {
    if (staffId === null || preview === null) return;
    setApplying(true);
    setMessage(null);
    setError(null);
    try {
      await staffCasePreferenceCommandClient.apply(staffId, {
        snapshot: preview.snapshot,
        expected_fingerprint: preview.expected_fingerprint,
        preview_fingerprint: preview.preview_fingerprint,
      });
      const observed = await staffCasePreferenceSummaryClient.query(staffId);
      setSummary(observed);
      setDraft(draftFromSummary(observed));
      setEditing(false);
      setPreview(null);
      setMessage('已儲存並重新讀取最新六項接案偏好。');
      onSaved?.(observed);
    } catch (reason) {
      setError(errorMessage(reason, '接案偏好儲存或重新讀取失敗。'));
    } finally {
      setApplying(false);
    }
  };

  if (staffId === null) {
    return <div className="staff-directory-message">請先選擇服務人員。</div>;
  }

  if (loading) {
    return <div className="staff-directory-message" role="status">正在載入六項接案偏好…</div>;
  }

  if (summary === null) {
    return (
      <div className="staff-directory-message error" role="alert">
        {error ?? '接案偏好摘要目前無法讀取。'}
        <button type="button" className="staff-next-btn" onClick={() => setReloadGeneration((value) => value + 1)}>
          重試接案偏好
        </button>
      </div>
    );
  }

  return (
    <div data-surface-id="staff.case-preference-editor">
      <div className="staff-section-header" style={{ marginBottom: '12px' }}>
        <div>
          <h3 style={{ margin: 0 }}>📌 六項接案偏好</h3>
          <p>直接維護 Staff 正式 relation facts；預覽確認後才儲存。</p>
        </div>
        {!editing && (
          <button
            type="button"
            className="staff-next-btn"
            data-control-id="staff.case-preference.edit"
            onClick={startEditing}
          >
            編輯六項
          </button>
        )}
      </div>

      <div className="staff-qual-grid">
        {TOPICS.map(({ key, label, allowOther }) => {
          const topic = summary[key];
          return (
            <div key={key} className="staff-qual-card" role="group" aria-label={label}>
              <h4>{label}</h4>
              {editing ? (
                <>
                  <label>
                    選項（以頓號或逗號分隔）
                    <input
                      aria-label={`${label}選項`}
                      value={draft[key].values}
                      disabled={previewing || applying}
                      onChange={(event) => updateDraft(key, 'values', event.target.value)}
                    />
                  </label>
                  {allowOther ? (
                    <label>
                      其它
                      <input
                        aria-label={`${label}其它`}
                        value={draft[key].otherDetail}
                        disabled={previewing || applying}
                        onChange={(event) => updateDraft(key, 'otherDetail', event.target.value)}
                      />
                    </label>
                  ) : (
                    <small>其它來源尚未就緒；目前只可編輯正式交通方式選項。</small>
                  )}
                </>
              ) : (
                <>
                  <p style={{ margin: 0 }}>{topicValuesText(topic)}</p>
                  {topic.other_detail_status === 'ready' && topic.other_detail && (
                    <small>其它：{topic.other_detail}</small>
                  )}
                  {topic.other_detail_status === 'source_not_ready' && (
                    <small>其它來源尚未就緒</small>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>

      {editing && (
        <div className="staff-action-pair" style={{ marginTop: '12px' }}>
          {preview === null ? (
            <button
              type="button"
              className="staff-next-btn"
              data-control-id="staff.case-preference.preview"
              disabled={previewing || applying}
              onClick={() => void previewChanges()}
            >
              {previewing ? '預覽中…' : '預覽變更'}
            </button>
          ) : (
            <button
              type="button"
              className="staff-next-btn"
              data-control-id="staff.case-preference.apply"
              disabled={applying}
              onClick={() => void applyChanges()}
            >
              {applying ? '儲存並回讀中…' : '確認儲存'}
            </button>
          )}
          <button
            type="button"
            className="staff-next-btn"
            disabled={previewing || applying}
            onClick={preview === null ? cancelEditing : () => { setPreview(null); setMessage(null); setError(null); }}
          >
            {preview === null ? '取消' : '返回編輯'}
          </button>
        </div>
      )}

      {preview !== null && (
        <div className="staff-action-status" role="status">
          {preview.changed_topics.length === 0
            ? '預覽完成：六項內容與目前資料相同。'
            : `預覽完成：${changedTopicLabels(preview.changed_topics).join('、')}。`}
        </div>
      )}
      {message && <div className="staff-action-status" role="status">{message}</div>}
      {error && <div className="staff-action-status error" role="alert">{error}</div>}
    </div>
  );
};
