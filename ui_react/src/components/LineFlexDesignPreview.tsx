/**
 * File: LineFlexDesignPreview.tsx
 * Description: 顯示去敏 Flex 設計稿與 owner fact blocker，不產生 provider payload 或任何 mutation。
 */
import React from 'react';
import {
  adaptLineFlexDesignPreview,
  type LineFlexDesignActionTone,
} from '../adapters/line_flex_design/line_flex_design_adapter';

export interface LineFlexDesignPreviewProps {
  source: unknown;
}

function actionClassName(tone: LineFlexDesignActionTone): string {
  if (tone === 'agree') return 'flex-btn-agree';
  if (tone === 'secondary') return 'flex-btn-disagree';
  if (tone === 'alert') return 'flex-action-btn alert-btn';
  return 'flex-action-btn';
}

export const LineFlexDesignPreview: React.FC<LineFlexDesignPreviewProps> = ({ source }) => {
  let preview;
  try {
    preview = adaptLineFlexDesignPreview(source);
  } catch {
    return (
      <div className="line-error" role="alert" aria-label="Flex 設計預覽錯誤">
        Flex 設計資料格式不符，已停止顯示；請聯絡系統管理人員檢查設計來源。
      </div>
    );
  }

  return (
    <div className="mock-flex-content">
      <div className="mock-flex-bubble">
        <div className={`flex-card-inner${preview.alertStyle ? ' alert-style' : ''}`}>
          <div className={`flex-header${preview.alertStyle ? ' alert-header' : ''}`}>{preview.header}</div>
          <div className="flex-body">
            {preview.emphasis && <strong>{preview.emphasis}</strong>}
            {preview.bodyLines.map((line) => <p key={line}>{line}</p>)}
          </div>
          <div className={preview.actions.length > 1 ? 'flex-btn-row' : undefined}>
            {preview.actions.map((action) => (
              <button
                key={`${preview.id}:${action.label}`}
                type="button"
                className={actionClassName(action.tone)}
                disabled
              >
                {action.label}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="line-warning" role="status" aria-label="正式資料狀態">
        正式資料尚未載入：{preview.ownerFactBlocker} 本機只顯示去敏設計，不建立發送工作。
      </div>
    </div>
  );
};
