import React, { useEffect, useState } from 'react';
import { orderIntakeCompletionClient } from '../api/orders/order_intake_completion_client';

export const OrderTermsUnavailableNote: React.FC<{ caseNo: string; code: string | null }> = ({ caseNo, code }) => {
  const [message, setMessage] = useState('正在確認缺少的服務資料…');
  useEffect(() => {
    const controller = new AbortController();
    if (code === 'client_finance_bootstrap_required') {
      setMessage('尚未建立客戶帳務資料。');
    } else if (code === 'order_terms_start_date_required' || code === 'order_terms_service_days_required') {
      setMessage('正在確認缺少的服務資料…');
      void orderIntakeCompletionClient.previewCompletion(caseNo, { signal: controller.signal })
        .then((preview) => {
          if (controller.signal.aborted) return;
          const labels = { client_name: '姓名', start_date: '約定服務開始日', service_days: '服務天數' };
          setMessage(preview.missing_fields.length
            ? `缺少欄位：${preview.missing_fields.map((field) => labels[field]).join('、')}。`
            : '服務欄位已齊全，請重新整理以確認目前服務條件。');
        })
        .catch(() => { if (!controller.signal.aborted) setMessage('無法確認缺少哪些欄位，請重新整理。'); });
    } else {
      setMessage(code === 'order_terms_floor_fee_required' ? '缺少欄位：樓層加給。' : '服務條件暫時無法讀取，請重新整理。');
    }
    return () => controller.abort();
  }, [caseNo, code]);
  return <><p role="status">{message}</p>{code && <details><summary>技術資訊</summary><code>{code}</code></details>}</>;
};
