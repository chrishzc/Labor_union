/**
 * File: StaffCasePreferenceSummary.tsx
 * Description: 呈現 roster case-preference summary；card 使用 compact，Drawer 顯示完整 fallback。
 */
import React from 'react';
import type { StaffCasePreferenceSummaryViewModel } from '../../adapters/staff/case_preference_summary_adapter';

export interface StaffCasePreferenceSummaryProps {
  summary: StaffCasePreferenceSummaryViewModel;
  compact?: boolean;
}

export const StaffCasePreferenceSummary: React.FC<StaffCasePreferenceSummaryProps> = ({ summary, compact = false }) => {
  if (compact) {
    return (
      <div data-surface-id="staff.case-preference.card">
        {summary.topics.map((topic) => (
          <div key={topic.key}>{`${topic.label}：${topic.valuesText}`}</div>
        ))}
      </div>
    );
  }
  return (
    <div className="staff-qual-grid" data-surface-id="staff.case-preference.drawer">
      {summary.topics.map((topic) => (
        <div key={topic.key} className="staff-qual-card" role="group" aria-label={topic.label}>
          <h4>{topic.label}</h4>
          <p style={{ margin: 0 }}>{topic.valuesText}</p>
          {topic.otherDetailText && <small>{topic.otherDetailText}</small>}
        </div>
      ))}
    </div>
  );
};
