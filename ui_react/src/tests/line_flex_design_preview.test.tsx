/**
 * File: line_flex_design_preview.test.tsx
 * Description: 驗證 4 個 Flex 設計預覽皆去敏、零寫入，並明示缺少 owner fact 的業務 blocker。
 */
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LINE_FLEX_DESIGN_SOURCES } from '../adapters/line_flex_design/line_flex_design_adapter';
import type {
  LineIdentityRuntimeConfig,
  LineIdentityRuntimeConfigClient,
} from '../api/line_identity/line_identity_runtime_config_client';
import { LineFlexDesignPreview } from '../components/LineFlexDesignPreview';
import { LiffCardStudio } from '../pages/line_management/LiffCardStudio';

describe('LINE Flex design preview', () => {
  it('4 個既有 Flex 資產都顯示去敏設計與 owner fact blocker', () => {
    const runtimeConfigClient: LineIdentityRuntimeConfigClient = {
      get: vi.fn(() => new Promise<LineIdentityRuntimeConfig>(() => undefined)),
    };
    render(React.createElement(LiffCardStudio, { runtimeConfigClient }));

    fireEvent.click(screen.getByRole('button', { name: 'Flex 卡片 (4)' }));
    const expected = [
      ['派案通知卡設計稿', '案件編號：【寄送前依正式案件資料帶入】'],
      ['服務日順延確認卡設計稿', '正式請假日期與順延後結束日會在寄送前核對。'],
      ['重大異常通報卡設計稿', '案件與告警摘要會以去敏方式提供'],
      ['媒合條件溝通卡設計稿', '由正式候選聯繫結果彙整可調整條件，不以樣本原因或時間造假。'],
    ] as const;

    for (const [title, safeText] of expected) {
      fireEvent.click(screen.getByRole('button', { name: new RegExp(title) }));
      expect(screen.getByText(safeText)).toBeInTheDocument();
      expect(screen.getByRole('status', { name: '正式資料狀態' })).toHaveTextContent('尚未載入');
    }

    expect(screen.queryByText(/demo[-_ ]?token|client[_ -]?id|line[_ -]?user[_ -]?id/i)).not.toBeInTheDocument();
    expect(runtimeConfigClient.get).toHaveBeenCalledTimes(1);
  });

  it('拒絕額外 provider 欄位且不把來源內容穿透畫面', () => {
    const forbiddenValue = 'demo-token-must-not-render';
    render(React.createElement(LineFlexDesignPreview, {
      source: {
        ...LINE_FLEX_DESIGN_SOURCES.flex_dispatch,
        raw_provider_payload: forbiddenValue,
      },
    }));

    expect(screen.getByRole('alert', { name: 'Flex 設計預覽錯誤' })).toHaveTextContent('已停止顯示');
    expect(screen.queryByText(forbiddenValue)).not.toBeInTheDocument();
    expect(screen.queryByText('案件編號：【寄送前依正式案件資料帶入】')).not.toBeInTheDocument();
  });
});
